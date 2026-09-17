import os

from dotenv import load_dotenv
from openai import OpenAI


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


def chat(prompt: str) -> str:
    """
    调用 Qwen Responses API
    """
    response = client.responses.create(
        model="qwen3.8-max",  # 换成你实际使用的模型 ID
        input=prompt
    )
    return response.output_text

if __name__ == "__main__":
    result = chat("你好，请用一句话介绍你自己。")
    print(result)