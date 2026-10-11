"""隔离端到端验收；先启动 NativeToolsTest.main 的临时H2服务。--live最多两次现有模型调用。"""
import argparse
import hashlib
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.remote_world import RemoteWorld, ACTIONS, RUNTIME_FIELDS
from agent.graph import build_graph
from agent.tick import WorldSession
from memory.stream import observe as observe_memories
from llm_client import request_decision, MODEL
from openai.types.chat import ChatCompletionMessage
from retrieval.chroma_index import ChromaIndex
import web_api
import httpx
import uvicorn
from contextlib import asynccontextmanager


class LocalEmbedder:
    model = "native-demo-local"
    dimensions = 16
    def embed(self, texts):
        return [[(byte - 128) / 128 for byte in hashlib.sha256(text.encode()).digest()[:16]] for text in texts]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--fault-only", action="store_true")
    args = parser.parse_args()
    backend = RemoteWorld(url="http://127.0.0.1:18080/mcp"); backend.initialize()
    schemas = backend.model_tools()
    assert {tool["function"]["name"] for tool in schemas} == ACTIONS
    for tool in schemas:
        assert not RUNTIME_FIELDS & tool["function"]["parameters"]["properties"].keys()
    invitation_schema = backend.discover_tools()["respond_invitation"].inputSchema
    assert invitation_schema["properties"]["accept"]["type"] == "boolean"
    evidence = {"model": MODEL if args.live else "SDK mock", "discovered_business_tools": sorted(ACTIONS),
                "native_calls": [], "ticks": [], "world_storage": "isolated H2", "embeddings": "local deterministic"}
    # 从实际MCP入口制造回执写失败，证明注册的工具也处于Spring事务中。
    before = backend.load()
    mind, memories, _ = observe_memories(before, "苏晚")
    mind.update(goal="验收", intention="查看现场", last_decision=before["minute"], next_decision=before["minute"] + 5)
    try:
        backend.commit("苏晚", "fail-storage", {"action": "inspect", "arguments": {"object_id": "bookshelf"},
                                                "reason": "事务验收", "mind": mind, "memories": memories})
    except RuntimeError:
        pass
    else:
        raise AssertionError("临时H2必须配置回执失败约束")
    assert backend.load() == before
    evidence["mcp_world_and_receipt_rollback"] = True
    if args.fault_only:
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return
    calls = 0
    def model(prompt, tools, feedback):
        nonlocal calls
        calls += 1
        if args.live:
            assert calls <= 2
            selected = request_decision(prompt, tools, feedback)
        else:
            # 仅用于确定性验收，决策结果仍经SDK tool_calls解析；不能作为真实模型能力证明。
            context = json.loads(prompt.split("当前本人视角：\n")[1].split("\n上次提议未执行：")[0])
            name = context["本人"]["name"]
            if context["本人邀请"] and any(i["to"] == name for i in context["本人邀请"]):
                action = "respond_invitation"; business = {"invitation_id": next(i["id"] for i in context["本人邀请"] if i["to"] == name), "accept": True}
            elif context["本人会话"]:
                action = "say"; business = {"message": "今天想聊聊各自的安排。"}
            elif name == "苏晚" and not context["近期经历"]:
                action = "invite"; business = {"target": "许宁", "message": "愿意聊一会吗？"}
            elif context["本人"]["location"] != "晚风茶馆":
                action = "move"; business = {"location": "晚风茶馆"}
            else:
                action = "inspect"; business = {"object_id": "bookshelf"}
            cognition = {"goal": "日常生活", "intention": "交流或看看现场", "plan": [], "reflection": None,
                         "relationship_notes": {}, "next_review_minutes": 5}
            if context["本轮是否需要反思"]:
                cognition["reflection"] = {"content": "交流需要尊重对方的安排。", "source_event_ids": context["近期经历"][-1]["source_event_ids"]}
            message = ChatCompletionMessage(role="assistant", tool_calls=[{"id": f"demo-call-{calls}", "type": "function",
                "function": {"name": action, "arguments": json.dumps({**business, "reason": "根据当前安排行动", "cognition": cognition}, ensure_ascii=False)}}])
            with patch("llm_client.get_client") as client:
                client.return_value.chat.completions.create.return_value = NS(choices=[NS(message=message)])
                selected = request_decision(prompt, tools, feedback)
        evidence["native_calls"].append({"call_id": selected["call_id"], "name": selected["proposal"]["action"],
                                         "api_tool_call_type": selected["message"]["tool_calls"][0]["type"]})
        return selected
    import chromadb
    index = ChromaIndex(backend.world_id, embedder=LocalEmbedder(), client=chromadb.EphemeralClient())
    graph = build_graph(backend, index, model)
    session = WorldSession(backend, graph)
    if args.live:
        backend.advance()
        result = graph.invoke({"name": "苏晚"}, {"recursion_limit": 10})["result"]
        assert result["status"] == "committed"
        evidence["ticks"].append({"minute": backend.snapshot["minute"], "successes": 1})
    else:
        for _ in range(3):
            before = backend.snapshot["minute"]
            results = session.next_tick()
            assert backend.snapshot["minute"] == before + 5 and len(results) <= 2
            assert len({r["actor"] for r in results}) == len(results)
            evidence["ticks"].append({"minute": backend.snapshot["minute"], "successes": len(results)})
        assert any(e["type"] == "conversation_started" for e in backend.snapshot["events"])
        conversation = backend.snapshot["conversations"][0]
        assert len(conversation["messages"]) == 2
        assert conversation["messages"][0]["speaker"] != conversation["messages"][1]["speaker"]
        evidence["conversation_messages"] = len(conversation["messages"])
    assert "decisions" not in backend.snapshot
    # 实际Chroma检索索引：构造离线记忆候选，验证owner/audience隔离，不修改权威世界。
    person = backend.snapshot["characters"]["苏晚"]
    memories = [{"id": f"archive-{i}", "content": f"本人的经历{i}", "minute": 480, "importance": 2, "kind": "observation", "source_event_ids": ["demo"]} for i in range(12)]
    recalled, lore = index.recall(backend.snapshot, "苏晚", memories, "本人的经历")
    assert recalled and lore
    assert all(m["owner"] == "苏晚" for m in index.memories.get(include=["metadatas"])["metadatas"])
    evidence["chroma_owner_filter"] = True
    web_api.controller.session = session; web_api.controller.refresh_status()
    @asynccontextmanager
    async def lifespan(_): yield
    web_api.app.router.lifespan_context = lifespan
    server = uvicorn.Server(uvicorn.Config(web_api.app, host="127.0.0.1", port=18001, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    for _ in range(100):
        if server.started: break
        time.sleep(.05)
    assert server.started
    try:
        observe = httpx.get("http://127.0.0.1:18080/api/world", timeout=10).raise_for_status().json()
        assert observe["world_id"] == backend.world_id
        assert observe["decisions"] and any(e.get("action_trace") for e in observe["events"])
        assert person["memories"] and person["mind"]["goal"]
        with httpx.stream("GET", "http://127.0.0.1:18080/api/events?mode=observe", timeout=10) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("data:"):
                    state = json.loads(line[5:]); assert state["revision"] == backend.snapshot["revision"]
                    evidence["sse_state"] = True; break
        backend.join("旅人", "青石街"); web_api.controller.refresh_status()
        play = httpx.get("http://127.0.0.1:18080/api/world?mode=play", timeout=10).raise_for_status().json()
        assert play["decisions"] == [] and all("secrets" not in p for p in play["characters"].values())
        assert all("action_trace" not in e for e in play["events"])
        response = httpx.post("http://127.0.0.1:18080/api/play/action", json={"world_id": backend.world_id, "action": "inspect", "arguments": {"object_id": "street-board"}}, timeout=10)
        response.raise_for_status(); assert response.json()["queued"]
        for _ in range(100):
            if not web_api.controller.player_pending: break
            time.sleep(.05)
        assert not web_api.controller.player_error
        backend.load(); assert backend.snapshot["events"][-1]["actor"] == "旅人"
        evidence["player_queue_and_visibility"] = True
    finally:
        server.should_exit = True; thread.join(timeout=5)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
