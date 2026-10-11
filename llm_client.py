"""保留现有模型配置，客户端延迟创建；启动、静态检查不请求模型。"""

import json
import os
from math import isfinite
from functools import lru_cache

MODEL = "qwen3.8-flash"


@lru_cache(maxsize=1)
def get_client():
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv()
    key = os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY；请配置后再运行角色决策")
    try:
        timeout = float(os.getenv("NOVELWORLD_MODEL_TIMEOUT_SECONDS", "180"))
    except ValueError as error:
        raise RuntimeError("NOVELWORLD_MODEL_TIMEOUT_SECONDS 必须是正数秒数") from error
    if not isfinite(timeout) or timeout <= 0:
        raise RuntimeError("NOVELWORLD_MODEL_TIMEOUT_SECONDS 必须是有限的正数秒数")
    return OpenAI(api_key=key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", timeout=timeout, max_retries=0)


def request_decision(prompt, tools, feedback=()):
    """只接受API原生tool_calls；普通文本即使含JSON也不能成为行动。"""
    messages = [{"role": "user", "content": prompt}, *feedback]
    response = get_client().chat.completions.create(
        model=MODEL, messages=messages, tools=tools, tool_choice="auto", parallel_tool_calls=False)
    message = response.choices[0].message
    calls = message.tool_calls or []
    if len(calls) != 1 or calls[0].type != "function":
        raise ValueError("必须通过原生tool_calls选择且仅选择一个业务行动")
    call = calls[0]
    if call.function.name not in {tool["function"]["name"] for tool in tools}:
        raise ValueError("模型选择了未提供的工具")
    args = json.loads(call.function.arguments)
    if not isinstance(args, dict) or not isinstance(args.get("cognition"), dict):
        raise ValueError("工具必须包含结构化cognition")
    cognition = args.pop("cognition")
    if set(cognition) != {"goal", "intention", "plan", "reflection", "relationship_notes", "next_review_minutes"}:
        raise ValueError("工具认知字段无效")
    reason = args.pop("reason", None)
    return {"proposal": {"action": call.function.name, "arguments": args, "reason": reason, **cognition},
            "message": message.model_dump(include={"role", "content", "tool_calls"}, exclude_none=True),
            "call_id": call.id}
