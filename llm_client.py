import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from tools.world_tools import TOOL_SCHEMAS, execute_tool


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


def chat(prompt: str) -> str:
    """
    调用 Qwen Responses API
    """
    response = client.responses.create(
        model=MODEL,
        input=prompt
    )
    return response.output_text


def chat_with_tools(prompt: str) -> str:
    """允许模型调用一次或多个已注册工具，然后返回最终回答。"""
    conversation = [
        {
            "role": "user",
            "content": prompt,
        }
    ]

    # 第一次请求：让模型判断是否需要调用工具。
    response = client.responses.create(
        model=MODEL,
        input=conversation,
        tools=TOOL_SCHEMAS,
    )

    function_calls = [
        item for item in response.output if item.type == "function_call"
    ]

    # 模型认为不需要工具时，直接返回它的文字回答。
    if not function_calls:
        return response.output_text

    # Python 执行模型请求的工具，并把结果追加到对话中。
    for function_call in function_calls:
        arguments = json.loads(function_call.arguments)
        tool_result = execute_tool(function_call.name, arguments)

        conversation.append(
            {
                "type": "function_call",
                "name": function_call.name,
                "arguments": function_call.arguments,
                "call_id": function_call.call_id,
            }
        )
        conversation.append(
            {
                "type": "function_call_output",
                "call_id": function_call.call_id,
                "output": tool_result,
            }
        )

    # 第二次请求：让模型根据真实工具结果组织最终回答。
    final_response = client.responses.create(
        model=MODEL,
        input=conversation,
        tools=TOOL_SCHEMAS,
    )
    return final_response.output_text

if __name__ == "__main__":
    result = chat("你好，请用一句话介绍你自己。")
    print(result)
