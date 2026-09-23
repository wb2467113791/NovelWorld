from llm_client import chat_with_tools
from characters.prompt import build_prompt_for_character
from characters.presets import CHARACTERS
from tools.world_tools import NPC_ACTION_TOOL_SCHEMAS
from world.persistence import DEFAULT_SAVE_PATH, load_world, save_world
from world.state import WORLD_STATE
from retrieval.chroma_index import ChromaIndex


DEFAULT_CHARACTER = "苏晚"


def choose_character() -> str:
    """让用户从现有角色中选择一个，直接回车默认选择苏晚。"""
    names = " / ".join(CHARACTERS)

    while True:
        choice = input(f"请选择角色（{names}，直接回车默认苏晚）：").strip()
        character_name = choice or DEFAULT_CHARACTER

        if character_name in CHARACTERS:
            return character_name

        print(f"角色不存在：{character_name}")


def build_prompt(user_input: str, character_name: str = DEFAULT_CHARACTER,
                 index: ChromaIndex | None = None) -> str:
    return build_prompt_for_character(character_name, user_input, index=index)


def main():
    scheduler_state = load_world(DEFAULT_SAVE_PATH) if DEFAULT_SAVE_PATH.exists() else None
    index = ChromaIndex(WORLD_STATE["world_id"])
    index.sync_world(WORLD_STATE["characters"])
    if not DEFAULT_SAVE_PATH.exists():
        save_world(DEFAULT_SAVE_PATH, scheduler_state=scheduler_state)
    character_name = choose_character()

    print("=" * 40)
    print("NovelWorld")
    print(f"当前角色：{character_name}")
    print("输入 exit 退出")
    print("=" * 40)

    while True:
        user_input = input("\nYou > ")

        if user_input.lower() == "exit":
            print("NovelWorld 已退出。")
            break

        try:
            prompt = build_prompt(user_input, character_name, index=index)

            response = chat_with_tools(
                prompt,
                tool_schemas=NPC_ACTION_TOOL_SCHEMAS,
                acting_character=character_name,
            )

            print(f"\n{character_name} > {response}")

        except Exception as e:
            print(f"\n调用 LLM 失败：{e}")
        finally:
            save_world(DEFAULT_SAVE_PATH, scheduler_state=scheduler_state)
            index.sync_world(WORLD_STATE["characters"])


if __name__ == "__main__":
    main()
