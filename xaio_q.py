import asyncio
import json
import time
import uuid

import requests
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

import config

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


def messages_to_prompt(messages):
    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user = msg.get("content", "")
            break
    return last_user


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

    reply = await ask_bot(prompt)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7878)