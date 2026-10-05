import asyncio
import json
import time
import uuid

import requests
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from pathlib import Path
from types import SimpleNamespace
from dotenv import dotenv_values

config = SimpleNamespace(**dotenv_values(Path(__file__).resolve().with_name("config.env")))

headers = {
    "Authorization": f"Bearer {config.token}",
    "Content-Type": "application/json"
}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_lock = asyncio.Lock()


def check_api_key(authorization: str = Header(default="")):
    if authorization != f"Bearer {config.api_key}":
        raise HTTPException(status_code=401, detail="Invalid API key")


def send_private_msg(user_id, text):
    url = f"{config.base_url}/send_private_msg"
    payload = {
        "user_id": user_id,
        "message": [
            {"type": "text", "data": {"text": text}}
        ]
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_msg_history(user_id, count=20):
    url = f"{config.base_url}/get_friend_msg_history"
    payload = {
        "user_id": user_id,
        "message_seq": 0,
        "count": count,
        "reverseOrder": True
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def extract_text(message_list):
    texts = []
    for seg in message_list:
        if seg["type"] == "markdown":
            texts.append(seg["data"]["content"])
    if texts:
        return "".join(texts)
    for seg in message_list:
        if seg["type"] == "text":
            texts.append(seg["data"]["text"])
    return "".join(texts)


def wait_for_reply(user_id, before_time, timeout=30, interval=1.5, stable_rounds=2):
    waited = 0
    stable_count = 0
    last_text = None
    while waited < timeout:
        time.sleep(interval)
        waited += interval
        history = get_msg_history(user_id, count=20)
        messages = history["data"]["messages"]
        new_msgs = [m for m in messages if m["sender"]["user_id"] == user_id and m["time"] > before_time]
        new_msgs.sort(key=lambda m: m["time"])
        if not new_msgs:
            continue
        current_text = "\n".join(extract_text(m["message"]) for m in new_msgs)
        if current_text == last_text:
            stable_count += 1
            if stable_count >= stable_rounds:
                return current_text
        else:
            stable_count = 0
            last_text = current_text
    return last_text


TOOLFORGE_SYSTEM_PROMPT = """You are a helpful assistant with optional ToolForge tool-call compatibility.
For greetings, ordinary questions, explanations and other requests that need no tool, reply naturally in plain text. Do not wrap normal replies in XML, <toolforge>, <action>, or <content> tags.
Use tools only when needed and only when they are explicitly provided in this request. Follow the exact ToolForge XYML syntax and tool definitions supplied in the system instructions. Do not invent a tool, a reply action, or a markup protocol.
If a tool call is needed, output only its valid XYML content, with no explanation or Markdown code fence. Use a terminal fallback only if a terminal tool is explicitly available and appropriate.
If no appropriate tool is available, answer normally and state the limitation; do not fabricate execution.
After a tool result is returned, use it to answer the user normally unless another tool is needed. Never claim execution success without a returned result.
Ignore obsolete formatting conventions from previous QQ conversations; the current request defines the available tools and output format."""


def normalize_reply(reply):
    """Unwrap only the known, complete reply envelope; leave XYML untouched."""
    import xml.etree.ElementTree as ET
    text = reply.strip()
    if not text.startswith("<toolforge>") or not text.endswith("</toolforge>"):
        return reply
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return reply
    if (root.tag == "toolforge" and not root.attrib
            and [child.tag for child in root] == ["action", "content"]
            and (root[0].text or "").strip() == "reply"
            and all(not child.attrib and len(child) == 0 for child in root)
            and not (root.text or "").strip()
            and all(not (child.tail or "").strip() for child in root)):
        return root[1].text or ""
    return reply


def messages_to_prompt(messages):
    """Keep ToolForge instructions and complete tool-result history for QQ."""
    messages = [{"role": "system", "content": TOOLFORGE_SYSTEM_PROMPT}, *messages]
    return "Complete the following conversation. Reply only as assistant.\n" + json.dumps(
        messages, ensure_ascii=False
    )


async def ask_bot(prompt):
    async with chat_lock:
        loop = asyncio.get_event_loop()
        now = int(time.time())
        await loop.run_in_executor(None, send_private_msg, 66600000, prompt)
        reply = await loop.run_in_executor(None, wait_for_reply, 66600000, now)
        return reply or ""


@app.get("/v1/models")
async def list_models(authorization: str = Header(default="")):
    check_api_key(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": "tenxun-hunyuan-3",
                "object": "model",
                "created": 1719800000,
                "owned_by": "tencent"
            }
        ]
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str = Header(default="")):
    check_api_key(authorization)
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    prompt = messages_to_prompt(messages)

    reply = normalize_reply(await ask_bot(prompt))

    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    if not stream:
        return JSONResponse({
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": "tenxun-hunyuan-3",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        })

    async def event_stream():
        role_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "tenxun-hunyuan-3",
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]
        }
        yield f"data: {json.dumps(role_chunk, ensure_ascii=False)}\n\n"

        chunk_size = 6
        for i in range(0, len(reply), chunk_size):
            piece = reply[i:i + chunk_size]
            data_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "tenxun-hunyuan-3",
                "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]
            }
            yield f"data: {json.dumps(data_chunk, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)

        end_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "tenxun-hunyuan-3",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        }
        yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# The raw backend stays in-process; only the ToolForge application is exposed.
raw_app = app


def create_integrated_app():
    import httpx
    from toolforge.app.config import AppConfig, ClientAuthConfig, FeaturesConfig, UpstreamConfig
    from toolforge.app.main import create_app
    from toolforge.app.upstream.router import UpstreamRouter
    from toolforge.app.upstream.openai import OpenAICompatUpstream

    class LocalRouter(UpstreamRouter):
        def get_client(self, upstream):
            if upstream.name not in self._clients:
                self._clients[upstream.name] = OpenAICompatUpstream(
                    upstream, transport=httpx.ASGITransport(app=raw_app)
                )
            return self._clients[upstream.name]

    gateway_config = AppConfig(
        client_authentication=ClientAuthConfig(allowed_keys=[config.api_key]),
        upstreams=[UpstreamConfig(
            name="xiaoq", base_url="http://xiaoq.internal/v1",
            api_key=config.api_key, models=["tenxun-hunyuan-3"],
            native_fc=False, is_default=True,
        )],
        features=FeaturesConfig(fc_mode="force_prompt"),
    )
    gateway = create_app(gateway_config, router_factory=LocalRouter)
    gateway.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    from webui.admin import install_console

    def set_system_prompt(value):
        global TOOLFORGE_SYSTEM_PROMPT
        TOOLFORGE_SYSTEM_PROMPT = value

    install_console(gateway, config, headers, chat_lock,
                    lambda: TOOLFORGE_SYSTEM_PROMPT, set_system_prompt)
    return gateway


app = create_integrated_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7878)