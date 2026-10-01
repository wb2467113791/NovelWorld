"""把角色可见信息整理成 Prompt。"""

from characters.model import Character
from world.state import WORLD_STATE


def _build_character_context(
    character: Character,
    memories: list[str],
) -> str:
    """组装当前 NPC 的独立角色视角。"""
    goals = "；".join(character.goals)
    secrets = "；".join(character.secrets) or "暂无"
    known_facts = "；".join(character.known_facts) or "暂无"
    items = "；".join(character.items) or "暂无"
    relationship_text = "；".join(
        f"对{target}的关系值为{value}"
        for target, value in character.relationships.items()
    ) or "暂无"
    memory_text = "\n".join(f"- {memory}" for memory in memories) or "- 暂无"

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


def build_action_prompt(
    character: Character,
    *,
    active_goal: str,
    memories: list[str],
    retrieved_context: list[str],
    lore_context: list[str],
    observations: list[str],
    runtime_context: dict | None = None,
) -> str:
    """自主行动模式：NPC 没有用户输入，根据自身上下文决定下一步。"""
    character_context = _build_character_context(character, memories)
    retrieved_text = "\n".join(f"- {item}" for item in retrieved_context) or "- 暂无"
    lore_text = "\n".join(f"- {item}" for item in lore_context) or "- 暂无"
    available_objects = WORLD_STATE["inspectable_objects"].get(character.location, {})
    local_objects = "、".join(available_objects) or "暂无"
    active_goal_text = f"当前目标：{active_goal}\n"
    from skills.router import skill_for
    current_skill = skill_for(character, active_goal)
    skill_section = f"【当前行动策略】\n{current_skill}\n" if current_skill else ""
    observation_text = "\n".join(f"- {item}" for item in observations) or "- 暂无"
    observation_section = f"【本轮观察】\n{observation_text}\n"
    import json
    cognition = json.dumps(runtime_context or character.runtime_state.to_dict(), ensure_ascii=False)

    return f"""
你是正在 NovelWorld 中自主行动的角色。

{character_context}

【检索到的旧记忆与调查事实】
{retrieved_text}

【世界设定】
{lore_text}

{skill_section}

【当前状态】
世界时间：{WORLD_STATE["time"]}
所在地点：{character.location}
体力：{character.energy}
生命值：{character.hp}
状态：{character.status}
所在地点可调查对象：{local_objects}

{observation_section}
【本人认知状态（意图，不是世界事实）】
{cognition}
每次结合最新观察重新考虑目标、意图与计划。Plan 只是一段粗粒度方向，可保留、修订或清空；
不能是 Tool 步骤列表，不能据此声称行动已经完成。Skill 建议只是决策上下文。
需要更新认知时，在本次回复文字中输出 JSON 对象：
{{"cognition": {{"active_goal": "本人目标之一", "current_intention": "此刻想达成什么", "current_plan": "根据新信息可调整的方向"}}, "answer": "本轮回复及原因"}}
cognition 仅允许 active_goal、current_intention、current_plan、agenda、busy_until；省略字段保持原值，意图和计划可用 null 清空。
agenda 为条目列表，每条含 id、character（本人）、due_tick（世界累计 Tick 序号）、intention、status（pending/completed/cancelled）。
busy_until 为累计 Tick 序号或 null。Agenda 和 busy_until 目前只保存，不会自动执行或阻塞行动。
不能在 cognition 中写位置、体力、已知事实或替他人更新状态。工具调用仍使用现有工具；普通文字回复也可保持原认知。
【本次任务】
{active_goal_text}根据你的目标、当前状态、已知事实和记忆，决定此刻最合理的一步行动。旧记忆可能已过时，以当前状态和最新调查结果为准。
需要改变世界或获取信息时，请调用一个合适的工具。如果此刻没有合理行动，可以直接回复“等待”，不调用工具；等待不产生世界事件。
不要等待用户提问，不要替其他角色行动，也不要使用上面没有提供的信息。
只有工具结果才能代表真实的状态变化，不要声称位置、体力或关系发生了未经工具执行的改变。
他人说“请过目”只是一句对话；若要声称自己已查看某个对象，先用 inspect 工具指定 object_name，并以成功结果为依据。不要虚构工具结果未提供的细节。
每个 Tick 最多成功执行一个行动。完成后根据工具结果结束本轮，不要重复调查没有变化的内容。
最终回复请另起一行写“原因：……”，用一句简短的话说明你为何采取这一步；只依据你已知的信息和工具结果。
"""
