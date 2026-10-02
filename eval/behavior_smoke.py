"""Real LLM decisions + production Graph/RAG/Scheduler + isolated Java rules/H2.

python -m eval.behavior_smoke --scenario both --ticks 30
Uses the existing llm_client/embedding configuration and incurs API charges.
No scripted decisions, live world, production database, or fixed plot assertions.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import sys
from uuid import uuid4

from agent.session import WorldSession, make_graph_decide_action
from characters.model import is_npc
from eval.java_bridge import EvalWorld, JavaBridge
from retrieval.chroma_index import ChromaIndex
from tools.remote_world import active_backend, use_backend
from world.persistence import restore_snapshot, snapshot_world
from world.state import WORLD_STATE

CATEGORIES = ("inspect", "talk", "move", "activity", "object_interaction", "wait", "other")


def distribution(trace):
    total = Counter(dict.fromkeys(CATEGORIES, 0))
    per_npc = {}
    for turn in trace:
        if turn["character"] == "世界":
            continue
        counts = per_npc.setdefault(turn["character"], Counter(dict.fromkeys(CATEGORIES, 0)))
        # No committed event means a consumed opportunity without action, reported as wait.
        kinds = [event["type"] for event in turn["events"]] or ["wait"]
        for kind in kinds:
            category = "object_interaction" if kind in {"take", "put", "give", "use", "interact"} else kind
            if category not in CATEGORIES:
                category = "other"
            total[category] += 1; counts[category] += 1
    return {"total": dict(total), "per_npc": {name: dict(value) for name, value in per_npc.items()}}


def run_scenario(bridge, seed, scenario, args, directory):
    import llm_client
    # 单次请求禁用 SDK 自动重试，预算不因网络重试扩大；模型配置保持原值。
    llm_client.client = llm_client.client.with_options(max_retries=0, timeout=60)
    from llm_client import MODEL, request_npc_graph_response
    from retrieval.embedding import DashScopeEmbedder
    opening = deepcopy(seed)
    opening["world_id"] = "behavior-" + uuid4().hex
    if scenario == "investigation":
        # A custom goal/context, not a prescribed route or tool sequence.
        for person in opening["characters"].values():
            if person.get("actor_type", "npc") == "npc":
                person["goals"] = ["调查集市安排的不同说法，核实公告与登记记录是否一致，再考虑如何回应"]
                person["runtime_state"] = {}
        opening["lore"].append({"id": "investigation-theme", "category": "theme", "audience": "public",
            "text": "本世界主题是调查：集市公告与登记记录可能不一致，角色需要核实可见材料中的信息。调查结论未知，不规定行动顺序。"})
    restore_snapshot(opening)
    backend = EvalWorld(opening["world_id"], bridge)
    restore_snapshot(backend.open(snapshot_world()))
    use_backend(backend)
    index = ChromaIndex(opening["world_id"], root=directory / "chroma")
    trace, requests, tokens = [], 0, Counter()
    output = args.output / f"{scenario}.json"
    session = None

    def request_model(conversation, allow_tools):
        nonlocal requests
        if requests >= args.max_model_calls:
            raise RuntimeError("真实模型请求已达到本场景预算上限")
        requests += 1
        response = request_npc_graph_response(conversation, allow_tools)
        usage = getattr(response, "usage", None)
        if usage:
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                tokens[key] += getattr(usage, key, 0) or 0
        return response

    def save_report(error=None):
        report = {"scenario": scenario, "mode": "real_llm", "model": MODEL,
                  "embedding_model": DashScopeEmbedder.model, "director": "off",
                  "transport": "Java MCP handler via local eval bridge; temporary H2",
                  "requested_ticks": args.ticks, "completed_ticks": session.completed_ticks if session else 0,
                  "model_requests": requests, "tokens": dict(tokens), "error": error,
                  **distribution(trace), "trace": trace}
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    session = WorldSession(make_graph_decide_action(request_model, index),
                           save_path=args.output / f"{scenario}-world.json", index=index, director=None)
    try:
        index.sync_world(WORLD_STATE["characters"])
        for tick in range(1, args.ticks + 1):
            before = len(WORLD_STATE["events"])
            result = session.next_tick()
            trace.append({"tick": tick, **dict(result),
                          "events": deepcopy(WORLD_STATE["events"][before:]),
                          "cognition": {name: person.runtime_state.to_dict() for name, person in
                                        WORLD_STATE["characters"].items() if is_npc(person)}})
            save_report()
            print(f"{scenario} Tick {tick}/{args.ticks}: {result['character']} "
                  f"{[event['type'] for event in trace[-1]['events']] or ['wait']}", flush=True)
    except Exception as error:
        save_report(type(error).__name__)  # No API credentials or raw remote exception payloads in reports.
        raise
    finally:
        # 先关闭持久化客户端，释放 Windows HNSW 文件锁，再由 TemporaryDirectory 清理。
        index.client.close()
    report = save_report()
    print(json.dumps({key: value for key, value in report.items() if key != "trace"}, ensure_ascii=False), flush=True)
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("default", "investigation", "both"), default="both")
    parser.add_argument("--ticks", type=int, default=30)
    parser.add_argument("--max-model-calls", type=int, default=120)
    parser.add_argument("--output", type=Path, default=Path("eval/results/behavior-smoke"))
    args = parser.parse_args()
    if args.ticks < 30 or args.max_model_calls < 1:
        parser.error("验收需要至少 30 Tick，模型调用预算必须为正数")
    args.output.mkdir(parents=True, exist_ok=True)
    original, old_backend = deepcopy(WORLD_STATE), active_backend()
    seed = snapshot_world()
    scenarios = ("default", "investigation") if args.scenario == "both" else (args.scenario,)
    try:
        with tempfile.TemporaryDirectory(prefix="novelworld-behavior-") as path:
            directory = Path(path)
            bridge = JavaBridge(directory)
            try:
                for scenario in scenarios:
                    run_scenario(bridge, seed, scenario, args, directory)
            finally:
                bridge.close()
    finally:
        WORLD_STATE.clear(); WORLD_STATE.update(original)
        use_backend(old_backend)


if __name__ == "__main__":
    main()
