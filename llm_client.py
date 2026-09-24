import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from tools.world_tools import NPC_ACTION_TOOL_SCHEMAS


# 读取 .env
load_dotenv()

api_key = os.getenv("DASHSCOPE_API_KEY")

if not api_key:
    raise ValueError("没有找到 DASHSCOPE_API_KEY，请检查 .env 文件")


# 创建客户端
client = OpenAI(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

MODEL = "qwen3.8-max"
MAX_TOOL_ROUNDS = 5


def chat(prompt: str) -> str:
    """
    调用 Qwen Responses API
    """
    response = client.responses.create(
        model=MODEL,
        input=prompt
    )
    return response.output_text


def request_npc_graph_response(
    conversation: list[dict[str, Any]],
    allow_tools: bool,
):
    """为单 NPC Graph 调用现有 Qwen Responses 客户端。"""
    request: dict[str, Any] = {
        "model": MODEL,
        "input": conversation,
    }
    if allow_tools:
        request["tools"] = NPC_ACTION_TOOL_SCHEMAS
    return client.responses.create(**request)
