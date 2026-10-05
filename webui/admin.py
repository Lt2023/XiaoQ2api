"""Local administration API and static console for the XiaoQ gateway."""
from collections import deque
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


class AccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    base_url: str = Field(max_length=500)
    token: str = Field(default="", max_length=4096)


class KeyInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class KeyStatus(BaseModel):
    enabled: bool


class SettingsInput(BaseModel):
    fc_mode: str
    enable_fc_error_retry: bool


class ThemeInput(BaseModel):
    theme: str


class ConsoleStore:
    def __init__(self, path, config, system_prompt):
        self.path = Path(path)
        self.started = time.monotonic()
        self.events = deque(maxlen=100)
        self.total = 0
        self.errors = 0
        self.durations = 0.0
        self.minute_counts = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {
                "accounts": [],
                "active_account": None,
                "keys": [{"id": "default", "name": "原有 API Key", "digest": fingerprint(config.api_key),
                    "preview": "•••• " + config.api_key[-4:], "enabled": True, "created_at": timestamp()}],
                "settings": {"fc_mode": "force_prompt", "enable_fc_error_retry": True},
            }
        changed = False
        accounts = self.data.setdefault("accounts", [])
        # Remove the auto-generated placeholder from older console state while
        # preserving accounts that were explicitly added by the user.
        legacy_default = any(item.get("id") == "default" and item.get("name") == "默认 NapCat 账号"
            for item in accounts)
        if legacy_default:
            accounts[:] = [item for item in accounts
                if not (item.get("id") == "default" and item.get("name") == "默认 NapCat 账号")]
            if self.data.get("active_account") == "default":
                self.data["active_account"] = accounts[0]["id"] if accounts else None
            changed = True
        account_ids = {item.get("id") for item in accounts}
        active_account = self.data.get("active_account")
        if active_account is not None and active_account not in account_ids:
            self.data["active_account"] = accounts[0]["id"] if accounts else None
            changed = True
        settings = self.data.setdefault("settings", {})
        # Older console versions exposed this internal value; migrate it out of
        # persistent settings so it is no longer returned by the admin API.
        changed = (settings.pop("system_prompt", None) is not None) or changed
        settings.setdefault("fc_mode", "force_prompt")
        settings.setdefault("enable_fc_error_retry", True)
        if changed:
            self.save()
        self.audit_events = deque(self.data.get("audit_events", []), maxlen=100)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    def valid_key(self, key):
        digest = fingerprint(key or "")
        return any(k["enabled"] and hmac.compare_digest(k["digest"], digest) for k in self.data["keys"])

    def account(self, account_id):
        item = next((a for a in self.data["accounts"] if a["id"] == account_id), None)
        if not item:
            raise HTTPException(404, "账号不存在")
        return item


class ConsoleMiddleware:
    """Observe response headers without buffering or interfering with SSE streams."""
    def __init__(self, app, store):
        self.app = app
        self.store = store

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        tracked = path.startswith(("/v1/", "/v1beta/", "/anthropic/")) or path in {
            "/chat/completions", "/responses", "/messages"
        }
        started = time.monotonic()
        recorded = False

        def record(status):
            nonlocal recorded
            if not tracked or recorded:
                return
            recorded = True
            elapsed = round((time.monotonic() - started) * 1000)
            self.store.total += 1
            self.store.errors += int(status >= 400)
            self.store.durations += elapsed
            minute = int(time.time() // 60)
            counts = self.store.minute_counts
            counts[minute] = counts.get(minute, 0) + 1
            self.store.minute_counts = {m: n for m, n in counts.items() if m >= minute - 59}
            self.store.events.appendleft({"time": timestamp(), "method": scope["method"],
                "path": path, "status": status, "duration_ms": elapsed})

        async def send_response(message):
            if message["type"] == "http.response.start":
                record(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                if path.startswith("/admin/"):
                    headers.append((b"cache-control", b"no-store"))
                if path == "/":
                    policy = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                        "img-src 'self' https://q.qlogo.cn; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
                    headers.append((b"content-security-policy", policy.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        except Exception:
            record(500)
            raise


def install_console(app, config, upstream_headers, chat_lock, get_prompt, set_prompt, state_path=None):
    app.title = "XiaoQ API Console"
    app.description = "XiaoQ API 管理控制台"
    store = ConsoleStore(state_path or ROOT / "data" / "console.json", config, get_prompt())
    app.state.console = store
    app.state.client_key_validator = store.valid_key

    fallback_base_url = config.base_url
    fallback_token = config.token

    def apply_runtime():
        active_id = store.data.get("active_account")
        account = next((item for item in store.data["accounts"] if item["id"] == active_id), None)
        config.base_url = account["base_url"] if account else fallback_base_url
        config.token = account["token"] if account else fallback_token
        upstream_headers["Authorization"] = f"Bearer {config.token}"
        settings = store.data["settings"]
        app.state.config.features.fc_mode = settings["fc_mode"]
        app.state.config.features.enable_fc_error_retry = settings["enable_fc_error_retry"]

    apply_runtime()

    def admin(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization.encode(), f"Bearer {config.api_key}".encode()):
            raise HTTPException(401, "请输入 config.env 中的管理员 API Key")

    def public_accounts():
        return [{k: v for k, v in item.items() if k != "token"} |
                {"qq_id": item.get("qq_id", ""), "nickname": item.get("nickname", ""),
                 "has_token": bool(item["token"]), "active": item["id"] == store.data["active_account"]}
                for item in store.data["accounts"]]

    def public_keys():
        return [{k: v for k, v in item.items() if k != "digest"} for item in store.data["keys"]]

    def log_activity(action, detail):
        store.audit_events.appendleft({"time": timestamp(), "action": action, "detail": detail})
        store.data["audit_events"] = list(store.audit_events)
        store.save()

    @app.get("/admin/api/overview", dependencies=[Depends(admin)])
    async def overview():
        minute = int(time.time() // 60)
        return {"total": store.total, "errors": store.errors,
                "average_ms": round(store.durations / store.total) if store.total else 0,
                "uptime_seconds": int(time.monotonic() - store.started),
                "accounts": public_accounts(), "keys": public_keys(), "events": list(store.events),
                "traffic": [store.minute_counts.get(m, 0) for m in range(minute - 23, minute + 1)],
                "settings": {"fc_mode": store.data["settings"]["fc_mode"],
                    "enable_fc_error_retry": store.data["settings"]["enable_fc_error_retry"]},
                "activity": list(store.audit_events)}

    def validate_account(body):
        url = urlsplit(body.base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise HTTPException(422, "NapCat 地址必须是有效的 HTTP(S) 地址，且不含凭据、查询参数或片段")
        return body.base_url.rstrip("/")

    @app.post("/admin/api/accounts", dependencies=[Depends(admin)])
    async def add_account(body: AccountInput):
        url = validate_account(body)
        item = {"id": secrets.token_hex(8), "name": body.name, "base_url": url,
                "token": body.token, "qq_id": "", "nickname": "", "created_at": timestamp()}
        async with chat_lock:
            store.data["accounts"].append(item)
            log_activity("account_added", f"添加连接账号「{body.name}」")
        return {"id": item["id"]}

    @app.put("/admin/api/accounts/{account_id}", dependencies=[Depends(admin)])
    async def edit_account(account_id: str, body: AccountInput):
        url = validate_account(body)
        async with chat_lock:
            item = store.account(account_id)
            profile_changed = url != item.get("base_url") or (body.token and body.token != item.get("token"))
            item.update(name=body.name, base_url=url)
            if body.token:
                item["token"] = body.token
            if profile_changed:
                item.update(qq_id="", nickname="")
            store.save()
            apply_runtime()
            log_activity("account_updated", f"更新连接账号「{body.name}」")
        return {"ok": True}

    @app.post("/admin/api/accounts/{account_id}/activate", dependencies=[Depends(admin)])
    async def activate_account(account_id: str):
        async with chat_lock:
            store.account(account_id)
            store.data["active_account"] = account_id
            store.save()
            apply_runtime()
            log_activity("account_activated", f"切换当前连接账号为「{store.account(account_id)['name']}」")
        return {"ok": True}

    @app.delete("/admin/api/accounts/{account_id}", dependencies=[Depends(admin)])
    async def delete_account(account_id: str):
        async with chat_lock:
            item = store.account(account_id)
            was_active = account_id == store.data.get("active_account")
            store.data["accounts"] = [a for a in store.data["accounts"] if a["id"] != account_id]
            if was_active:
                store.data["active_account"] = store.data["accounts"][0]["id"] if store.data["accounts"] else None
                apply_runtime()
            log_activity("account_deleted", f"删除连接账号「{item['name']}」")
        return {"ok": True}

    @app.post("/admin/api/accounts/{account_id}/test", dependencies=[Depends(admin)])
    async def test_account(account_id: str):
        item = dict(store.account(account_id))
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                response = await client.post(item["base_url"] + "/get_login_info",
                    headers={"Authorization": "Bearer " + item["token"]}, json={})
                response.raise_for_status()
                result = response.json()
            if result.get("retcode") != 0 or not isinstance(result.get("data"), dict):
                raise ValueError("NapCat rejected the request")
            profile = result["data"]
            raw_user_id = profile.get("user_id")
            user_id = str(raw_user_id).strip() if raw_user_id is not None else ""
            qq_id = user_id if re.fullmatch(r"[1-9]\d{4,11}", user_id) else ""
            raw_nickname = profile.get("nickname")
            nickname = raw_nickname.strip()[:60] if isinstance(raw_nickname, str) else ""
            if qq_id:
                async with chat_lock:
                    current = store.account(account_id)
                    if current.get("base_url") == item.get("base_url") and current.get("token") == item.get("token"):
                        current.update(qq_id=qq_id, nickname=nickname)
                        store.save()
            return {"ok": True, "nickname": nickname or None, "user_id": qq_id or None}
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "连接失败，请检查 NapCat 地址、Token 和服务状态")

    @app.post("/admin/api/keys", dependencies=[Depends(admin)])
    async def create_key(body: KeyInput):
        secret = "sk-xiaoq-" + secrets.token_urlsafe(30)
        item = {"id": secrets.token_hex(8), "name": body.name, "digest": fingerprint(secret),
                "preview": secret[:12] + "••••" + secret[-4:], "enabled": True, "created_at": timestamp()}
        store.data["keys"].append(item)
        log_activity("key_created", f"创建 API Key「{body.name}」")
        return {"secret": secret, "id": item["id"]}

    @app.patch("/admin/api/keys/{key_id}", dependencies=[Depends(admin)])
    async def update_key(key_id: str, body: KeyStatus):
        item = next((k for k in store.data["keys"] if k["id"] == key_id), None)
        if not item:
            raise HTTPException(404, "API Key 不存在")
        item["enabled"] = body.enabled
        log_activity("key_updated", f"将 API Key「{item['name']}」{'启用' if body.enabled else '停用'}")
        return {"ok": True}

    @app.delete("/admin/api/keys/{key_id}", dependencies=[Depends(admin)])
    async def delete_key(key_id: str):
        if not any(k["id"] == key_id for k in store.data["keys"]):
            raise HTTPException(404, "API Key 不存在")
        key_name = next(k["name"] for k in store.data["keys"] if k["id"] == key_id)
        store.data["keys"] = [k for k in store.data["keys"] if k["id"] != key_id]
        log_activity("key_deleted", f"删除 API Key「{key_name}」")
        return {"ok": True}

    @app.put("/admin/api/settings", dependencies=[Depends(admin)])
    async def save_settings(body: SettingsInput):
        if body.fc_mode not in {"auto", "force_prompt"}:
            raise HTTPException(422, "请选择 auto 或 force_prompt")
        async with chat_lock:
            store.data["settings"] = body.model_dump()
            store.save()
            apply_runtime()
            log_activity("settings_updated", "更新接口与工具兼容设置")
        return {"ok": True}

    @app.post("/admin/api/activity", dependencies=[Depends(admin)])
    async def record_activity(body: ThemeInput):
        if body.theme not in {"light", "dark"}:
            raise HTTPException(422, "主题值无效")
        log_activity("theme_changed", f"切换为{'深色' if body.theme == 'dark' else '浅色'}模式")
        return {"ok": True}

    @app.get("/", include_in_schema=False)
    async def console_page():
        return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/logo.png", include_in_schema=False)
    async def console_logo():
        return FileResponse(ROOT / "xaioq_logo.png", media_type="image/png")

    app.add_middleware(ConsoleMiddleware, store=store)

    # Mount only public assets: never expose Python files, configuration or tokens.
    app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="console-assets")
    return store
