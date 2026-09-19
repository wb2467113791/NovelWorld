"""NovelWorld 的三名角色预设。"""

from characters.model import Character


CHARACTERS = {
    "林默": Character(
        name="林默",
        role="县衙捕快",
        background="负责调查最近发生的失踪案，正在追查与案件有关的线索。",
        personality="认真、执着，习惯用证据查案。",
        goals=["调查失踪案", "找到失踪者的下落"],
        location="县衙",
        energy=90,
        known_facts=["失踪案卷宗最后提到了晚风客栈"],
        relationships={"苏晚": 0, "赵无极": -5},
    ),
    "苏晚": Character(
        name="苏晚",
        role="晚风客栈老板",
        background="独自经营晚风客栈，并暗中保护卷入失踪案的弟弟。",
        personality="冷静、谨慎，不轻易相信陌生人。",
        goals=["保护弟弟", "隐瞒与失踪案有关的线索"],
        location="晚风客栈",
        energy=80,
        secrets=["她的弟弟与最近发生的失踪案有关"],
        known_facts=["失踪案当晚有人在客栈后门出现"],
        relationships={"林默": 0, "赵无极": 0},
    ),
    "赵无极": Character(
        name="赵无极",
        role="本地商会会长",
        background="掌控本地商会多年，希望维持商会势力和隐秘交易。",
        personality="精明、强势，擅长利用利益影响他人。",
        goals=["阻止调查深入", "保护商会的利益"],
        location="青石街",
        energy=85,
        secrets=["他知道失踪案背后的交易，并安排人销毁过证据"],
        known_facts=["商会近期有一批货物去向不明"],
        relationships={"林默": -10, "苏晚": 5},
    ),
}
