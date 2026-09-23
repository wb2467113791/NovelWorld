"""离线 V1.5 对照：近期窗口与 Chroma 长期召回。"""

import json
import tempfile
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from agent.state import create_initial_agent_state
from characters.prompt import build_action_prompt
from retrieval.chroma_index import ChromaIndex
from world.state import WORLD_STATE


def run_evaluation() -> dict:
    original = deepcopy(WORLD_STATE)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            WORLD_STATE["world_id"] = "eval-v15"
            actor = WORLD_STATE["characters"]["林默"]
            clue = "晚风客栈后门有一枚铜扣线索"
            actor.memory.add(clue, importance=5)
            for number in range(30):
                actor.memory.add(f"第{number}次普通巡查没有新发现")
            index = ChromaIndex(WORLD_STATE["world_id"], Path(directory))
            query = "晚风客栈后门铜扣"
            started = perf_counter()
            baseline = actor.memory.recent()
            baseline_ms = round((perf_counter() - started) * 1000, 3)
            started = perf_counter()
            retrieved = index.retrieve_memory(actor, query)
            retrieval_ms = round((perf_counter() - started) * 1000, 3)
            state = create_initial_agent_state(actor, goal=query, index=index)
            prompt = build_action_prompt(actor, active_goal=query,
                                         memories=state["memories"],
                                         retrieved_context=state["retrieved_context"],
                                         lore_context=state["lore_context"])
            other = WORLD_STATE["characters"]["苏晚"]
            other_result = index.retrieve_memory(other, query)
            result = {
                "recent_only_recalls_old_clue": any(clue in item for item in baseline),
                "chroma_recalls_old_clue": any(clue in item for item in retrieved),
                "other_npc_sees_old_clue": any(clue in item for item in other_result),
                "retrieved_items": len(retrieved),
                "retrieved_chars": sum(map(len, retrieved)),
                "prompt_chars": len(prompt),
                "recent_only_ms": baseline_ms,
                "chroma_first_query_ms": retrieval_ms,
                "model_api_calls": 0,
            }
            assert not result["recent_only_recalls_old_clue"]
            assert result["chroma_recalls_old_clue"]
            assert not result["other_npc_sees_old_clue"]
            assert result["retrieved_items"] <= 3 and result["retrieved_chars"] <= 600
            return result
    finally:
        WORLD_STATE.clear()
        WORLD_STATE.update(original)


if __name__ == "__main__":
    print(json.dumps(run_evaluation(), ensure_ascii=False, indent=2))
