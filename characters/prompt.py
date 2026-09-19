"""把角色可见信息整理成 Prompt。"""

from characters.model import Character
from world.state import WORLD_STATE


def build_character_prompt(
    character: Character,
    user_input: str,
) -> str:
    """只把当前角色可见的信息放入 Prompt，不暴露他人的秘密。"""
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
你正在进行角色扮演。

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
