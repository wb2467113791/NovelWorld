"""把角色可见信息整理成 Prompt。"""

from characters.model import Character
from memory.retrieval import recent_memory_texts, retrieve_character_memory
from lore.catalog import retrieve_lore
from typing import Any
from world.state import WORLD_STATE


def _build_character_context(
    character: Character,
    memories: list[str] | None = None,
) -> str:
    """组装对话模式和自主行动模式共用的角色可见信息。"""
    goals = "；".join(character.goals)
    secrets = "；".join(character.secrets) or "暂无"
    known_facts = "；".join(character.known_facts) or "暂无"
    items = "；".join(character.items) or "暂无"
    relationship_text = "；".join(
        f"对{target}的关系值为{value}"
        for target, value in character.relationships.items()
    ) or "暂无"
    visible_memories = recent_memory_texts(character) if memories is None else memories
    memory_text = "\n".join(f"- {memory}" for memory in visible_memories) or "- 暂无"

    return f"""
【角色设定】
姓名：{character.name}
身份：{character.role}
背景：{character.background}
性格：{character.personality}
目标：{goals}
自己的秘密：{secrets}
已知事实：{known_facts}
持有物品：{items}
当前关系：{relationship_text}

【近期记忆】
{memory_text}
""".strip()


def build_character_prompt(
    character: Character,
    user_input: str,
    index: Any | None = None,
) -> str:
    """对话模式：NPC 根据角色信息回答【用户】输入。"""
    character_context = _build_character_context(character)
    retrieved_context = (index.retrieve_memory(character, user_input) if index else retrieve_character_memory(character, user_input))
    lore_context = (index.retrieve_lore(character.name, user_input) if index else retrieve_lore(character.name, user_input))
    retrieved_text = "\n".join(f"- {item}" for item in retrieved_context) or "- 暂无"
    lore_text = "\n".join(f"- {item}" for item in lore_context) or "- 暂无"

    return f"""
你正在进行角色扮演。

{character_context}

【检索到的旧记忆与调查事实】
{retrieved_text}

【世界设定】
{lore_text}

【用户】
{user_input}

【要求】
请根据角色设定，以{character.name}的身份回答用户。
角色知道自己的秘密，但不能主动轻易泄露。
只能使用上面提供的信息，不要猜测或声称知道其他角色的秘密。
要与其他角色真正交谈时，请调用 talk 工具；只有工具成功执行才算交谈发生。
不要声称位置、关系或事件发生了未经工具执行的变化。
不要告诉用户你是 AI 或语言模型。
回答自然、简短，符合人物性格。
"""


def build_prompt_for_character(character_name: str, user_input: str, index: Any | None = None) -> str:
    """从世界状态读取唯一的角色对象，构建独立视角 Prompt。"""
    character = WORLD_STATE["characters"].get(character_name)
    if character is None:
        raise ValueError(f"角色不存在：{character_name}")

    return build_character_prompt(character, user_input, index=index)


def build_action_prompt(
    character: Character,
    *,
    active_goal: str | None = None,
    memories: list[str] | None = None,
    retrieved_context: list[str] | None = None,
    lore_context: list[str] | None = None,
    observations: list[str] | None = None,
) -> str:
    """自主行动模式：NPC 没有用户输入，根据自身上下文决定下一步。"""
    character_context = _build_character_context(character, memories)
    active_goal = active_goal or character.goals[0]
    if retrieved_context is None:
        retrieved_context = retrieve_character_memory(
            character, f"{active_goal} {character.location}"
        )
    retrieved_text = "\n".join(f"- {item}" for item in retrieved_context) or "- 暂无"
    if lore_context is None:
        lore_context = retrieve_lore(character.name, f"{active_goal} {character.location}")
    lore_text = "\n".join(f"- {item}" for item in lore_context) or "- 暂无"
    local_objects = "、".join(WORLD_STATE["inspectable_objects"].get(character.location, {})) or "暂无"
    active_goal_text = f"当前目标：{active_goal}\n"
    observation_text = "\n".join(f"- {item}" for item in observations or []) or "- 暂无"
    observation_section = (
        f"【本轮观察】\n{observation_text}\n"
        if observations is not None else ""
    )

    return f"""
你是正在 NovelWorld 中自主行动的角色。

{character_context}

【检索到的旧记忆与调查事实】
{retrieved_text}

【世界设定】
{lore_text}

【当前状态】
世界时间：{WORLD_STATE["time"]}
所在地点：{character.location}
体力：{character.energy}
所在地点可调查对象：{local_objects}

{observation_section}
【本次任务】
{active_goal_text}根据你的目标、当前状态、已知事实和记忆，决定此刻最合理的一步行动。旧记忆可能已过时，以当前状态和最新调查结果为准。
需要改变世界或获取信息时，请调用一个合适的工具。
不要等待用户提问，不要替其他角色行动，也不要使用上面没有提供的信息。
只有工具结果才能代表真实的状态变化，不要声称位置、体力或关系发生了未经工具执行的改变。
他人说“请过目”只是一句对话；若要声称自己已查看某个对象，先用 inspect 工具指定 object_name，并以成功结果为依据。不要虚构工具结果未提供的细节。
每个 Tick 最多成功执行一个行动。完成后根据工具结果结束本轮，不要重复调查没有变化的内容。
最终回复请另起一行写“原因：……”，用一句简短的话说明你为何采取这一步；只依据你已知的信息和工具结果。
"""


def build_action_prompt_for_character(character_name: str) -> str:
    """从世界状态读取角色，为一次自主行动构建 Prompt。"""
    character = WORLD_STATE["characters"].get(character_name)
    if character is None:
        raise ValueError(f"角色不存在：{character_name}")

    return build_action_prompt(character)
