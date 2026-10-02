"""Scripted decisions + production Python scheduler + real Java rules/H2 persistence.

Run Java tests first, then: python -m eval.long_run --ticks 1000 --boundaries
No model, embeddings, live world, or production database is accessed.
"""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import time
import sys

from agent.conversation import for_participant, sessions
from agent.tick import WorldTickScheduler
from characters.model import PlayerActor, is_npc
from characters.prompt import build_action_prompt
from eval.java_bridge import EvalWorld, JavaBridge
from memory.belief import MAX_BELIEFS
from tools.remote_world import active_backend, use_backend
from tools.world_tools import execute_tool
from world.objects import inventory, validate
from world.persistence import restore_snapshot, snapshot_world
from world.play import state_view
from world.state import WORLD_STATE


def new_world(bridge, seed, identifier):
    opening = deepcopy(seed)
    opening["world_id"] = identifier
    for actor in opening["characters"].values():
        actor["location"] = "晚风客栈"
    opening["characters"]["玩家"] = asdict(PlayerActor("玩家", "晚风客栈"))
    restore_snapshot(opening)
    scheduler = WorldTickScheduler(director=None)
    backend = EvalWorld(identifier, bridge)
    backend.open(snapshot_world(scheduler_state=scheduler.snapshot()))
    restore_snapshot(backend.load())
    use_backend(backend)
    return backend, scheduler


def assert_world():
    validate(WORLD_STATE["objects"], WORLD_STATE["characters"], WORLD_STATE["locations"])
    for actor in WORLD_STATE["characters"].values():
        assert actor.items == inventory(actor), "derived inventory drift"
        assert all(-100 <= value <= 100 for value in actor.relationships.values()), "relationship range"


def long_run(bridge, seed, ticks):
    backend, scheduler = new_world(bridge, seed, "eval-long-run")
    names = [name for name, actor in WORLD_STATE["characters"].items() if is_npc(actor)]
    opportunities = Counter({name: 0 for name in names})
    actions, sources, details = Counter(), Counter(), {name: Counter() for name in names}
    maxima = {"pending": len(names), "agenda_per_npc": 0, "active_conversations": 0,
              "conversation_messages": 0, "belief_entries": 0, "short_term_entries": 0,
              "unreflected_entries": 0}
    last_turn, gaps, repeat = {name: 0 for name in names}, Counter(), {}
    repeated_max, opened = Counter(), Counter()
    ended = Counter({reason: 0 for reason in ("limit", "no_talk", "timeout", "move", "unconscious", "explicit_end")})
    lengths, checkpoints = [], {}
    restart = None

    def decide(actor):
        if actor.energy < 4:
            return execute_tool("rest_character", {"character": actor.name}, actor.name)
        conversation = for_participant(actor.name)
        partner = (next(name for name in conversation.participants if name != actor.name) if conversation else
                   names[(names.index(actor.name) + 1) % len(names)])
        return execute_tool("talk", {"speaker": actor.name, "listener": partner,
                                     "message": f"第{scheduler.snapshot()['tick_count']}轮：交流当前近况。"}, actor.name)

    def summary():
        return {"ticks": scheduler.snapshot()["tick_count"], "opportunities": dict(opportunities),
                "npc_actions": dict(actions), "sources": dict(sources),
                "per_npc": {name: dict(value) for name, value in details.items()},
                "max_opportunity_gap": dict(gaps), "maxima": dict(maxima),
                "events": len(WORLD_STATE["events"])}

    for tick in range(1, ticks + 1):
        before_events = len(WORLD_STATE["events"])
        before_sessions = {s.id: s.to_dict() for s in sessions()}
        result = scheduler.run_tick(decide)
        sources[result["source"]] += 1
        name = result["character"]
        if name in opportunities:
            opportunities[name] += 1
            details[name][result["source"]] += 1
            gaps[name] = max(gaps[name], tick - last_turn[name])
            last_turn[name] = tick
        added = WORLD_STATE["events"][before_events:]
        assert len(added) <= 1, "more than one successful action per tick"
        if added:
            event = added[0]
            actions[event["actor"]] += 1
            signature = (event["type"], event["target"], event["payload"].get("object_id"))
            prior, count = repeat.get(name, (None, 0))
            count = count + 1 if prior == signature else 1
            repeat[name] = signature, count
            repeated_max[name] = max(repeated_max[name], count)
        after_sessions = {s.id: s.to_dict() for s in sessions()}
        for identifier, session in after_sessions.items():
            if identifier not in before_sessions:
                opened[" ↔ ".join(sorted(session["participants"]))] += 1
        for identifier, session in before_sessions.items():
            if identifier not in after_sessions:
                final_talk = bool(added and added[0]["type"] == "talk")
                length = len(session["messages"]) + int(final_talk)
                lengths.append(length)
                ended["limit" if length >= 12 else "no_talk"] += 1
        assert_world()
        state = scheduler.snapshot()
        assert not any(item["source"] == "skill" for item in state["pending"])
        maxima["pending"] = max(maxima["pending"], len(state["pending"]))
        maxima["active_conversations"] = max(maxima["active_conversations"], len(sessions()))
        for session in sessions():
            maxima["conversation_messages"] = max(maxima["conversation_messages"], len(session.messages))
        for actor in WORLD_STATE["characters"].values():
            if not is_npc(actor):
                continue
            maxima["agenda_per_npc"] = max(maxima["agenda_per_npc"], len(actor.runtime_state.agenda))
            maxima["belief_entries"] = max(maxima["belief_entries"], len(actor.belief_memory.entries))
            maxima["short_term_entries"] = max(maxima["short_term_entries"], len(actor.memory.entries))
            maxima["unreflected_entries"] = max(maxima["unreflected_entries"], len(actor.memory.all_entries()) - actor.memory.reflection_cursor)
            assert len(actor.runtime_state.agenda) <= 1 and len(actor.belief_memory.entries) <= MAX_BELIEFS
            assert len(actor.memory.entries) <= actor.memory.max_items
            assert 0 <= actor.memory.reflection_cursor <= len(actor.memory.all_entries())
            gaps[actor.name] = max(gaps[actor.name], tick - last_turn[actor.name])
        assert maxima["pending"] <= len(names) and len(sessions()) <= len(names) // 2
        if tick == max(1, ticks // 2):
            backend.save_agent_state(state)
            before = deepcopy(snapshot_world(scheduler_state=state))
            bridge.restart()  # actual Java process restart; reopen the same temporary H2 file
            saved = backend.load()
            restored = restore_snapshot(saved)
            scheduler = WorldTickScheduler(director=None)
            scheduler.restore(restored)
            assert before == snapshot_world(scheduler_state=scheduler.snapshot()), "restart state drift"
            restart = {"at_tick": tick, "java_process_restarted": True, "snapshot_equal": True}
        if tick in {60, 200, 1000, ticks}:
            checkpoints[str(tick)] = summary()
        if tick % 100 == 0:
            print(f"Eval {tick}/{ticks}: {dict(opportunities)}", flush=True)
    report = summary()
    report.update(director="OFF", player_interventions=0, fairness_window=60, restart=restart,
                  checkpoints=checkpoints, consecutive_repeated_action_max=dict(repeated_max),
                  sessions_opened_by_pair=dict(opened), session_end_reasons=dict(ended),
                  mean_completed_session_length=sum(lengths) / len(lengths) if lengths else 0,
                  episodic_archive_entries={name: len(WORLD_STATE["characters"][name].memory.archive.entries) for name in names},
                  violations=[f"{name}: opportunity gap {gaps[name]} exceeds 60 ticks"
                              for name in names if not opportunities[name] or gaps[name] > 60])
    return report


def boundaries(bridge, seed):
    backend, scheduler = new_world(bridge, seed, "eval-boundaries")
    def npc(name):
        return WORLD_STATE["characters"][name]
    def obj(name):
        return next(value for value in WORLD_STATE["objects"].values() if value["name"] == name)
    scheduler.run_player_action("talk", {"listener": "苏晚", "message": "钥匙在县衙"})
    assert obj("钥匙")["location"] == "晚风客栈"
    assert any(entry.content == "钥匙在县衙" for entry in npc("苏晚").belief_memory.entries)
    assert not any(entry.content == "钥匙在县衙" for entry in npc("林默").belief_memory.entries)
    assert not npc("苏晚").semantic_memory.current_facts()
    session = for_participant("苏晚")
    assert session.next_speaker == "苏晚" and not scheduler.snapshot()["pending"][0]["source"] == "event"
    key_id, chest_id = obj("钥匙")["id"], obj("木箱")["id"]
    execute_tool("inspect", {"character": "苏晚", "object_id": key_id}, "苏晚")
    assert npc("苏晚").semantic_memory.current_facts()
    prompt = build_action_prompt(npc("苏晚"), active_goal=npc("苏晚").goals[0], memories=[],
                                 retrieved_context=[], lore_context=[], observations=[])
    assert "【已验证事实" in prompt and "【未验证说法" in prompt and "钥匙在县衙" in prompt
    scheduler.run_player_action("take", {"object_id": key_id})
    scheduler.run_player_action("interact", {"object_id": chest_id, "action": "open"})
    scheduler.run_player_action("put", {"object_id": key_id, "container_id": chest_id})
    scheduler.run_player_action("interact", {"object_id": chest_id, "action": "close"})
    assert key_id not in {value["id"] for value in state_view(scheduler.snapshot()["tick_count"])["visible_objects"]}
    scheduler.run_player_action("interact", {"object_id": chest_id, "action": "open"})
    scheduler.run_player_action("take", {"object_id": key_id})
    prior = npc("苏晚").relationships.get("玩家", 0)
    count = len(WORLD_STATE["events"])
    scheduler.run_player_action("give", {"object_id": key_id, "receiver": "苏晚"})
    assert len(WORLD_STATE["events"]) == count + 1 and npc("苏晚").relationships["玩家"] == prior + 2
    assert WORLD_STATE["events"][-1]["payload"]["relationship_changes"][0]["delta"] == 2
    scheduler.run_player_action("attack", {"target": "苏晚"})
    assert npc("苏晚").relationships["玩家"] == prior - 13
    # 恢复点必须真的包含活动 Player 会话，不能仅检查已结束的状态。
    scheduler.run_player_action("talk", {"listener": "苏晚", "message": "继续交流"})
    assert for_participant("苏晚").next_speaker == "苏晚"
    assert_world()
    backend.save_agent_state(scheduler.snapshot())
    before = deepcopy(snapshot_world(scheduler_state=scheduler.snapshot()))
    bridge.restart()
    restore_snapshot(backend.load())
    assert snapshot_world(scheduler_state=scheduler.snapshot()) == before
    new_world(bridge, seed, "eval-other-world")
    assert obj("钥匙")["holder"] is None and not any(e.content == "钥匙在县衙" for e in npc("苏晚").belief_memory.entries)
    use_backend(backend)
    restore_snapshot(backend.load())
    assert obj("钥匙")["holder"] == "苏晚"
    return {"misinformation": "passed", "private_report": "passed", "verified_prompt_partition": "passed",
            "closed_container": "passed", "object_invariants": "passed", "player_social": "passed",
            "restart_with_active_player_conversation": "passed", "world_switch": "passed"}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument("--boundaries", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("eval/results/latest.json"))
    args = parser.parse_args()
    if args.ticks < 60:
        parser.error("至少运行 60 Tick")
    original, old_backend = deepcopy(WORLD_STATE), active_backend()
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="novelworld-eval-") as directory:
            bridge = JavaBridge(Path(directory))
            report = {}
            try:
                seed = deepcopy(snapshot_world())
                report = {"long_run": long_run(bridge, seed, args.ticks)}
                if args.boundaries:
                    report["boundaries"] = boundaries(bridge, seed)
                report["elapsed_seconds"] = round(time.monotonic() - start, 2)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False, indent=2))
                if report["long_run"]["violations"]:
                    raise SystemExit(1)
            except Exception as error:
                report.update(status="failed", violations=[f"{type(error).__name__}: {error}"])
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                raise
            finally:
                bridge.close()
    finally:
        WORLD_STATE.clear()
        WORLD_STATE.update(original)
        use_backend(old_backend)


if __name__ == "__main__":
    main()
