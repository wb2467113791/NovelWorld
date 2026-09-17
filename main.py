from llm_client import chat


character = """
你叫苏晚。

身份：
晚风客栈老板。

性格：
冷静、谨慎，不轻易相信陌生人。

背景：
你经营着一家叫“晚风客栈”的客栈。

秘密：
你的弟弟与最近发生的一起失踪案有关，
你正在尽力隐藏这件事情。

要求：
你必须始终以苏晚的身份回答。
不要告诉用户你是 AI 或语言模型。
回答自然、简短，符合人物性格。
"""


def build_prompt(user_input: str) -> str:
    return f"""
你正在进行角色扮演。

【角色设定】
{character}

【用户】
{user_input}

【要求】
请根据角色设定，以苏晚的身份回答用户。
"""


def main():
    print("=" * 40)
    print("NovelWorld")
    print("当前角色：苏晚")
    print("输入 exit 退出")
    print("=" * 40)

    while True:
        user_input = input("\nYou > ")

        if user_input.lower() == "exit":
            print("NovelWorld 已退出。")
            break

        try:
            prompt = build_prompt(user_input)

            response = chat(prompt)

            print(f"\n苏晚 > {response}")

        except Exception as e:
            print(f"\n调用 LLM 失败：{e}")


if __name__ == "__main__":
    main()