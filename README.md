# Tenxun-XiaoQ 2api

因为 QQ 默认给用户分配了一个 Bot 叫小Q，拥有 DeepSeek 和腾讯 Hunyuan 大模型能力，本项目通过 napcat 反代出来的 HTTP API，把和小Q的私聊对话中转成 OpenAI 格式的 Chat Completions API，方便接入各类支持 OpenAI 接口的客户端或应用

## 功能

- 兼容 `POST /v1/chat/completions`，支持流式（`stream: true`）和非流式两种模式
- 兼容 `GET /v1/models`，返回模型 `tenxun-hunyuan-3`
- 支持跨域请求（CORS）
- 请求需携带 API Key 鉴权
- 并发请求会自动排队，避免多个用户的问题和小Q的回复串在一起


## 文件说明

- `config.py` —— 配置文件，填写 napcat 的地址、访问 token，以及本服务对外的 API Key
- `xaio_q.py` —— 主服务，启动后监听本地端口，提供 OpenAI 兼容接口
- `api_inv.py` —— 简单的调用示例，测试接口是否正常工作

## 安装

```bash
pip install -r requirements.txt
```

## 配置

编辑 `config.py`：

```python
base_url = "http://napcat:port"
token = "napcat的token"
api_key = "自己服务的key"
```

## 运行

```bash
python xaio_q.py
```

默认监听 `0.0.0.0:7878`

## 调用示例

```python
from openai import OpenAI

client = OpenAI(
    api_key="api_key",
    base_url="http://127.0.0.1:7878/v1"
)

response = client.chat.completions.create(
    model="tenxun-hunyuan-3",
    messages=[
        {"role": "user", "content": "你好"}
    ]
)

print(response.choices[0].message.content)
```
## 免责声明

本项目仅用于个人学习和技术研究，用于了解 API 中转、OpenAI 兼容接口封装等相关技术实现。

- 本项目依赖第三方工具 napcat 及腾讯 QQ 官方机器人小Q，其接口行为、可用性可能随时变化，不作任何稳定性保证。
- 请遵守腾讯 QQ 用户协议及相关服务条款，不要用于高频请求、商业用途或其他可能违反平台规则的场景。
- 使用本项目产生的任何后果由使用者自行承担，与项目编写者无关。
- 请勿将本项目用于任何侵犯他人权益、破坏平台正常服务或违反当地法律法规的行为。