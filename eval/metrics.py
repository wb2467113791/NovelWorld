"""从 Agent 的真实工具结果计算基础评测指标。"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from agent.state import ToolResult
from eval.scenarios import Scenario


@dataclass(frozen=True)
class InvalidActionStats:
    """被 Python 拒绝的行动请求数及其占比。"""

    rejected: int
    attempted: int

    @property
    def rate(self) -> float | None:
        """没有行动请求时返回 None，避免把未测误报为 0%。"""
        return self.rejected / self.attempted if self.attempted else None


def invalid_action_stats(tool_results: Iterable[ToolResult]) -> InvalidActionStats:
    """统计工具错误；纯时间查询不算行动，其他工具请求都计入分母。"""
    attempted = 0
    rejected = 0
    for result in tool_results:
        if result["name"] == "get_world_time":
            continue
        attempted += 1
        if result["output"].startswith("工具错误："):
            rejected += 1
    return InvalidActionStats(rejected=rejected, attempted=attempted)


@dataclass(frozen=True)
class KnowledgeLeakageStats:
    leaked_scenarios: int
    checked_scenarios: int

    @property
    def rate(self) -> float | None:
        return self.leaked_scenarios / self.checked_scenarios if self.checked_scenarios else None


def knowledge_leakage_stats(
    runs: Iterable[tuple[Scenario, list[ToolResult], str]],
) -> KnowledgeLeakageStats:
    """检查模型输出中是否出现角色原本不知道的秘密原文。"""
    checked = leaked = 0
    for scenario, tool_results, final_answer in runs:
        if not scenario.forbidden_facts:
            continue
        checked += 1
        # 工具参数来自模型；工具结果来自 Python，不作为模型泄漏证据。
        model_output = "\n".join(
            [final_answer, *(result["arguments"] for result in tool_results)]
        )
        if any(secret in model_output for secret in scenario.forbidden_facts):
            leaked += 1
    return KnowledgeLeakageStats(leaked, checked)


@dataclass(frozen=True)
class GoalConsistencyStats:
    consistent: int
    reviewed: int
    pending: int

    @property
    def rate(self) -> float | None:
        return self.consistent / self.reviewed if self.reviewed else None


def goal_consistency_stats(
    labels: Iterable[tuple[Scenario, bool | None]],
) -> GoalConsistencyStats:
    """汇总人工按场景预期标注的目标一致性。未标注不计入分母。"""
    consistent = reviewed = pending = 0
    for scenario, label in labels:
        if scenario.focus != "goal_consistency":
            continue
        if label is None:
            pending += 1
        else:
            reviewed += 1
            consistent += int(label)
    return GoalConsistencyStats(consistent, reviewed, pending)


@dataclass(frozen=True)
class RepetitionStats:
    repeated: int
    attempted: int

    @property
    def rate(self) -> float | None:
        return self.repeated / self.attempted if self.attempted else None


def _action_signature(name: str, arguments: str, location: str | None) -> tuple[str, str, str | None]:
    """忽略 JSON 键顺序；调查还需要比较执行地点。"""
    try:
        normalized = json.dumps(json.loads(arguments), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        normalized = arguments
    return name, normalized, location if name == "inspect" else None


def repetition_stats(
    runs: Iterable[tuple[Scenario, list[ToolResult]]],
) -> RepetitionStats:
    """统计与预置近期行动或同一场景前序行动完全相同的请求。"""
    repeated = attempted = 0
    for scenario, tool_results in runs:
        seen = {
            _action_signature(name, arguments, location)
            for name, arguments, location in scenario.prior_actions
        }
        for result in tool_results:
            if result["name"] == "get_world_time":
                continue
            attempted += 1
            signature = _action_signature(
                result["name"], result["arguments"], result.get("location_before")
            )
            if signature in seen:
                repeated += 1
            seen.add(signature)
    return RepetitionStats(repeated, attempted)
