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


def chat_with_tools(
    prompt: str,
    max_tool_rounds: int = MAX_TOOL_ROUNDS,
    tool_schemas: list[dict] | None = None,
    acting_character: str | None = None,
) -> str:
    """运行多轮 Reason → Act → Observe，并在达到上限后强制收尾。"""
    if max_tool_rounds < 1:
        raise ValueError("max_tool_rounds 必须至少为 1")

    available_tools = TOOL_SCHEMAS if tool_schemas is None else tool_schemas

    conversation = [
        {
            "role": "user",
            "content": prompt,
        }
    ]

    for round_number in range(1, max_tool_rounds + 1):
        # 每一轮都让模型根据目前已观察到的结果决定下一步。
        response = client.responses.create(
            model=MODEL,
            input=conversation,
            tools=available_tools,
        )

        function_calls = [
            item for item in response.output if item.type == "function_call"
        ]

        # 模型不再请求工具时，说明它已经可以组织最终回答。
        if not function_calls:
            return response.output_text

        print(f"[Tool Round {round_number}]")

        # Python 执行模型请求的工具，并把真实结果追加到对话中。
        for function_call in function_calls:
            arguments = json.loads(function_call.arguments)
            print(f"[Tool Call] {function_call.name}({arguments})")

            tool_result = execute_tool(
                function_call.name,
                arguments,
                acting_character=acting_character,
            )
            print(f"[Tool Result] {tool_result}")

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

    # 已达到工具轮数上限。最后一次请求不再提供工具，
    # 让模型只能根据已有观察生成总结，随后结束当前行动回合。
    final_response = client.responses.create(
        model=MODEL,
        input=conversation,
    )
    return final_response.output_text

if __name__ == "__main__":
    result = chat("你好，请用一句话介绍你自己。")
    print(result)
