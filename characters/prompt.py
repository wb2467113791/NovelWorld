"""把角色可见信息整理成 Prompt。"""

from characters.model import Character, is_npc
from agent.runtime import MODEL_COGNITION_FIELDS
from world.state import WORLD_STATE


def _build_character_context(
    character: Character,
    memories: list[str],
) -> str:
    """组装当前 NPC 的独立角色视角。"""
    if not is_npc(character):
        raise ValueError("Player 不使用 NPC Prompt")
    goals = "；".join(character.goals)
    secrets = "；".join(character.secrets) or "暂无"
    known_facts = "；".join(character.known_facts) or "暂无"
    from world.objects import inventory
    items = "；".join(inventory(character)) or "暂无"
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
    from world.objects import visible_objects
    local_objects = "；".join(f"{item['name']}（object_id={item['id']}，state={item['state']}，portable={item['portable']}，affordances={item['affordances']}）"
                              for item in visible_objects(character)) or "暂无"
    active_goal_text = f"当前目标：{active_goal}\n"
    from skills.router import skill_for
    current_skill = skill_for(character, active_goal)
    skill_section = f"【当前行动策略】\n{current_skill}\n" if current_skill else ""
    observation_text = "\n".join(f"- {item}" for item in observations) or "- 暂无"
    observation_section = f"【本轮观察】\n{observation_text}\n"
    import json
    runtime = runtime_context or character.runtime_state.to_dict()
    cognition = json.dumps({key: value for key, value in runtime.items() if key in MODEL_COGNITION_FIELDS}, ensure_ascii=False)
    scheduling = json.dumps({
        "agenda": [{"intention": entry["intention"], "due_tick": entry["due_tick"]}
                   for entry in runtime.get("agenda", []) if entry["status"] == "pending"],
        "busy_until": runtime.get("busy_until"),
    }, ensure_ascii=False)
    from agent.conversation import context_for
    current_conversation = context_for(character.name)
    conversation_section = ("【当前交流（只读，仅本人会话）】\n"
                            + json.dumps(current_conversation, ensure_ascii=False) + "\n"
                            if current_conversation else "")

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
【系统调度状态（只读）】
{scheduling}
{conversation_section}
交流消息必须通过 talk 工具真实提交；普通回复文字不会发送给对方。
可以输出 {{"continue_conversation": false, "answer": "结束交流的原因"}} 表达结束意愿，程序维护生命周期。
不能在 cognition 或其他模型文本中创建或修改 ConversationSession、participants、消息、轮次和状态。
会话轮次不调用 talk（包括等待）会结束本次交流；外部事件反应没有回复则可保留会话。
每次结合最新观察重新考虑目标、意图与计划。Plan 只是一段粗粒度方向，可保留、修订或清空；
不能是 Tool 步骤列表，不能据此声称行动已经完成。Skill 建议只是决策上下文。
需要更新认知时，在本次回复文字中输出 JSON 对象：
{{"cognition": {{"active_goal": "本人目标之一", "current_intention": "此刻想达成什么", "current_plan": "根据新信息可调整的方向"}}, "answer": "本轮回复及原因"}}
cognition 仅允许 active_goal、current_intention、current_plan；省略字段保持原值，意图和计划可用 null 清空。
不得在 cognition 中写入或清空 agenda、busy_until，也不得自行生成 Agenda ID、修改时间或声明 completed/cancelled。
Agenda 的 ID、状态、调度时间和 busy_until 由程序维护，完成与忙碌必须依据真实执行结果，不能因模型文字成立。
想安排什么活动、希望何时做，可在 current_intention/current_plan 中表达愿望；文字不直接建立 Agenda 或指定调度时间。
程序在行动机会结束后按固定冷却规则维护未来提醒，不从你的时间愿望解析精确 Tick。
Agenda 到期只提供一次重新思考的机会，提醒意图可结合最新观察重新考虑；不指定必须调用的工具。
Agenda 的 completed 只表示行动机会已消费，不表示目标或 Plan 已完成。busy_until 仅限制 Agenda 唤醒，事件反应保持原语义。
不能在 cognition 中写位置、体力、已知事实或替他人更新状态。工具调用仍使用现有工具；普通文字回复也可保持原认知。
【本次任务】
{active_goal_text}根据你的目标、当前状态、已知事实和记忆，决定此刻最合理的一步行动。旧记忆可能已过时，以当前状态和最新调查结果为准。
需要改变世界或获取信息时，请调用一个合适的工具。如果此刻没有合理行动，可以直接回复“等待”，不调用工具；等待不产生世界事件。
不要等待用户提问，不要替其他角色行动，也不要使用上面没有提供的信息。
只有工具结果才能代表真实的状态变化，不要声称位置、体力或关系发生了未经工具执行的改变。
他人说“请过目”只是一句对话；若要声称自己已查看某个对象，先用 inspect 工具指定可见 object_id，并以成功结果为依据。不要虚构工具结果未提供的细节。
每个 Tick 最多成功执行一个行动。完成后根据工具结果结束本轮，不要重复调查没有变化的内容。
最终回复请另起一行写“原因：……”，用一句简短的话说明你为何采取这一步；只依据你已知的信息和工具结果。
"""
