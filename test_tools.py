"""Live ToolForge round-trip test; executes only a local addition function."""
import argparse
import json
import sys
from pathlib import Path

from dotenv import dotenv_values
from openai import OpenAI


TOOLS = [{"type": "function", "function": {
    "name": "add_numbers", "description": "Add two integers and return their sum.",
    "parameters": {"type": "object", "properties": {
        "a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"], "additionalProperties": False}
}}]


def execute_tool(name, arguments):
    if name != "add_numbers":
        raise ValueError(f"Unexpected tool: {name}")
    args = json.loads(arguments)
    if not isinstance(args, dict) or set(args) != {"a", "b"}:
        raise ValueError("Expected exactly a and b")
    if any(type(args[k]) is not int for k in ("a", "b")):
        raise ValueError("a and b must be integers")
    return {"result": args["a"] + args["b"]}


def run(client, model):
    messages = [{"role": "user", "content":
        "请调用 add_numbers 工具计算 137 + 285，收到工具结果后再告诉我答案。"}]
    response = client.chat.completions.create(
        model=model, messages=messages, tools=TOOLS,
        tool_choice={"type": "function", "function": {"name": "add_numbers"}})
    message = response.choices[0].message
    if not message.tool_calls:
        raise RuntimeError(f"FAIL: no tool_calls returned; content={message.content!r}")
    messages.append(message.model_dump(exclude_none=True))
    if len(message.tool_calls) != 1:
        raise RuntimeError("FAIL: expected one tool call")
    call = message.tool_calls[0]
    print(f"TOOL_CALL: {call.function.name} {call.function.arguments}")
    result = execute_tool(call.function.name, call.function.arguments)
    if json.loads(call.function.arguments) != {"a": 137, "b": 285}:
        raise RuntimeError("FAIL: unexpected operands")
    print(f"EXECUTED: {json.dumps(result)}")
    messages.append({"role": "tool", "tool_call_id": call.id,
                     "content": json.dumps(result)})
    final = client.chat.completions.create(
        model=model, messages=messages, tools=TOOLS, tool_choice="none")
    reply = final.choices[0].message
    print(f"FINAL: {reply.content}")
    if reply.tool_calls or "422" not in (reply.content or ""):
        raise RuntimeError("FAIL: final response did not use the tool result")
    if any(tag in (reply.content or "") for tag in ("<toolforge>", "<|XYML|")):
        raise RuntimeError("FAIL: markup leaked into final response")
    print("PASS: tool call -> local execution -> result submission -> final answer")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:7878/v1")
    parser.add_argument("--model", default="tenxun-hunyuan-3")
    args = parser.parse_args()
    config = dotenv_values(Path(__file__).resolve().with_name("config.env"))
    if not config.get("api_key"):
        raise ValueError("config.env is missing api_key")
    with OpenAI(base_url=args.base_url, api_key=config["api_key"],
                timeout=180, max_retries=0) as client:
        run(client, args.model)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
