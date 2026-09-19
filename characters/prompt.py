"""把角色可见信息整理成 Prompt。"""

from characters.model import Character
from world.state import WORLD_STATE


def _build_character_context(character: Character) -> str:
    """组装对话模式和自主行动模式共用的角色可见信息。"""
    goals = "；".join(character.goals)
    secrets = "；".join(character.secrets) or "暂无"
    known_facts = "；".join(character.known_facts) or "暂无"
    relationship_text = "；".join(
        f"对{target}的关系值为{value}"
        for target, value in character.relationships.items()
    ) or "暂无"
    memory_text = "\n".join(
        f"- {memory}" for memory in character.memory.recent()
    ) or "- 暂无"

    return f"""
【角色设定】
姓名：{character.name}
身份：{character.role}
背景：{character.background}
性格：{character.personality}
目标：{goals}
自己的秘密：{secrets}
已知事实：{known_facts}
当前关系：{relationship_text}

【近期记忆】
{memory_text}
""".strip()


def build_character_prompt(
    character: Character,
    user_input: str,
) -> str:
    """对话模式：NPC 根据角色信息回答【用户】输入。"""
    character_context = _build_character_context(character)

    return f"""
你正在进行角色扮演。

{character_context}

【用户】
{user_input}

【要求】
请根据角色设定，以{character.name}的身份回答用户。
角色知道自己的秘密，但不能主动轻易泄露。
只能使用上面提供的信息，不要猜测或声称知道其他角色的秘密。
不要告诉用户你是 AI 或语言模型。
回答自然、简短，符合人物性格。
"""


def build_prompt_for_character(character_name: str, user_input: str) -> str:
    """从世界状态读取唯一的角色对象，构建独立视角 Prompt。"""
    character = WORLD_STATE["characters"].get(character_name)
    if character is None:
        raise ValueError(f"角色不存在：{character_name}")

    return build_character_prompt(character, user_input)


def build_action_prompt(character: Character) -> str:
    """自主行动模式：NPC 没有用户输入，根据自身上下文决定下一步。"""
    character_context = _build_character_context(character)

    return f"""
你是正在 NovelWorld 中自主行动的角色。

{character_context}

【当前状态】
世界时间：{WORLD_STATE["time"]}
所在地点：{character.location}
体力：{character.energy}

【本次任务】
根据你的目标、当前状态、已知事实和近期记忆，决定此刻最合理的一步行动。
需要改变世界或获取信息时，请调用一个合适的工具。
不要等待用户提问，不要替其他角色行动，也不要使用上面没有提供的信息。
只有工具结果才能代表真实的状态变化，不要声称位置、体力或关系发生了未经工具执行的改变。
一次只推进一个清晰、具体的行动。
"""


def build_action_prompt_for_character(character_name: str) -> str:
    """从世界状态读取角色，为一次自主行动构建 Prompt。"""
    character = WORLD_STATE["characters"].get(character_name)
    if character is None:
        raise ValueError(f"角色不存在：{character_name}")

    return build_action_prompt(character)
