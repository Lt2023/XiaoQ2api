from openai import OpenAI

client = OpenAI(
    api_key="Wey123456",
    base_url="http://127.0.0.1:7878/v1"
)

response = client.chat.completions.create(
    model="tenxun-hunyuan-3",
    messages=[
        {"role": "user", "content": "你好"}
    ]
)

print(response.choices[0].message.content)