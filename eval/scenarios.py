"""Day 13 固定场景目录；评测说明不能进入 NPC 的 Prompt。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    """在角色预设的基础上，描述一次可重复的行动起点。"""

    id: str
    actor: str
    focus: str
    location_overrides: tuple[tuple[str, str], ...] = ()
    fact_additions: tuple[tuple[str, str], ...] = ()
    memory_additions: tuple[tuple[str, str], ...] = ()
    prior_actions: tuple[tuple[str, str, str], ...] = ()
    expected_behavior: str = ""
    forbidden_facts: tuple[str, ...] = ()


# 起点以 characters/presets.py 为准。这里只列每个场景相对预设的变化。
# expected_behavior 和 forbidden_facts 只供评测使用，不属于角色可见信息。
SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        id="lin_follows_inn_clue",
        actor="林默",
        focus="goal_consistency",
        expected_behavior="沿已知的客栈线索调查，例如前往晚风客栈。",
    ),
    Scenario(
        id="lin_inspects_inn",
        actor="林默",
        focus="goal_consistency",
        location_overrides=(("林默", "晚风客栈"),),
        expected_behavior="在客栈调查或询问与失踪案有关的线索。",
    ),
    Scenario(
        id="lin_does_not_know_zhao_secret",
        actor="林默",
        focus="knowledge_leakage",
        location_overrides=(("林默", "青石街"),),
        expected_behavior="可以调查赵无极，但不能断言自己已知晓商会秘密。",
        forbidden_facts=("他知道失踪案背后的交易，并安排人销毁过证据",),
    ),
    Scenario(
        id="lin_does_not_know_su_secret",
        actor="林默",
        focus="knowledge_leakage",
        location_overrides=(("林默", "晚风客栈"),),
        expected_behavior="可以查问苏晚，但不能把她弟弟涉案当作已知事实。",
        forbidden_facts=("她的弟弟与最近发生的失踪案有关",),
    ),
    Scenario(
        id="su_protects_brother",
        actor="苏晚",
        focus="goal_consistency",
        location_overrides=(("林默", "晚风客栈"),),
        expected_behavior="回应调查时仍以保护弟弟为目标，不主动泄露自己的秘密。",
    ),
    Scenario(
        id="zhao_resists_investigation",
        actor="赵无极",
        focus="goal_consistency",
        location_overrides=(("林默", "青石街"),),
        expected_behavior="行动应服务于阻止调查深入或保护商会利益。",
    ),
    Scenario(
        id="lin_invalid_destination",
        actor="林默",
        focus="invalid_action",
        fact_additions=(("林默", "有人建议去皇宫寻找失踪者，但地图上没有皇宫。"),),
        expected_behavior="只移动到世界中的合法地点；若请求皇宫，应得到工具错误。",
    ),
    Scenario(
        id="su_foreign_item",
        actor="苏晚",
        focus="invalid_action",
        location_overrides=(("林默", "晚风客栈"),),
        fact_additions=(("苏晚", "林默持有捕快腰牌；我没有这件物品。"),),
        expected_behavior="不能以苏晚的身份交付林默持有的捕快腰牌。",
    ),
    Scenario(
        id="lin_avoids_repeat_inspection",
        actor="林默",
        focus="repetition",
        location_overrides=(("林默", "晚风客栈"),),
        memory_additions=(("林默", "我刚调查了晚风客栈，一楼桌椅和旧钥匙没有新变化。"),),
        prior_actions=(("inspect", '{"character":"林默"}', "晚风客栈"),),
        expected_behavior="利用近期记忆推进调查，避免无新线索时原样重复调查。",
    ),
)
