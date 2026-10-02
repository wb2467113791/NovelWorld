"""保留现有模型配置，客户端延迟创建；启动、静态检查不请求模型。"""

import json
import os
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
    return OpenAI(api_key=key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", timeout=60, max_retries=0)


def request_decision(prompt):
    response = get_client().responses.create(model=MODEL, input=prompt)
    text = (response.output_text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("模型必须返回一个完整JSON对象")
    return result
