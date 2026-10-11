"""从8/9/11条已提交消息继续真实模型对话；最多16次API请求，无远程embedding。"""
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.graph import build_graph
from agent.tick import opportunities
from memory.stream import observe
from llm_client import MODEL, request_decision
from tools.remote_world import RemoteWorld
from types import SimpleNamespace

SEED_MESSAGES = [
    "你最近读了什么？我想给自己留一点读书时间。",
    "读了一篇游记，里面写到安静散步时观察街坊的日常。",
    "这倒适合我写随笔。我也想写邻居平常的生活，但不想打扰大家。",
    "可以先问问是否愿意分享，没答应就不追问私人事情。",
    "嗯，我可以只记公开的街景。你觉得从茶馆窗边观察合适吗？",
    "窗边可以坐着看街景，但别把客人的私事写进去。",
    "我会先写自己的见闻，写完再看看是否需要征求别人同意。",
    "这样挺好。我上午还要打理茶馆，你也可以留些安静写作的时间。",
    "谢谢你提醒。我准备写一小段街景，今天就先不采访其他人了。",
    "慢慢写就好。我也要回去照顾茶馆了，很高兴聊了这些。",
    "那我去窗边写一会，谢谢你的建议。",
]


def main():
    total_calls = 0
    samples = []
    for initial_count in (8, 9, 11):
        backend = RemoteWorld(url="http://127.0.0.1:18080/mcp")
        backend.initialize()
        def submit(actor, action, arguments):
            w = backend.load(); mind, memories, _ = observe(w, actor)
            mind.update(goal="安排今天的生活", intention="交流读书和写作", last_decision=w["minute"], next_decision=w["minute"] + 5)
            return backend.commit(actor, uuid4().hex, {"action": action, "arguments": arguments,
                "reason": "验收对话铺垫", "mind": mind, "memories": memories})
        submit("苏晚", "invite", {"target": "许宁", "message": "愿意聊聊最近读的书和写作吗？"})
        invitation = backend.snapshot["invitations"][0]["id"]
        submit("许宁", "respond_invitation", {"invitation_id": invitation, "accept": True})
        for message in SEED_MESSAGES[:initial_count]:
            submit(backend.snapshot["conversations"][0]["next_speaker"], "say", {"message": message})
        sample = {"initial_message_count": initial_count, "model_turns": []}
        def model(prompt, tools, feedback):
            nonlocal total_calls
            total_calls += 1
            if total_calls > 16: raise RuntimeError("真实模型调用达到验收上限")
            return request_decision(prompt, tools, feedback)
        # 隔离检索返回本人已有记忆与公开设定，避免付费embedding；正式RAG代码不改。
        index = SimpleNamespace(recall=lambda w, name, memories, query: ([], [l["text"] for l in w["lore"] if l["audience"] in ("public", name)]))
        graph = build_graph(backend, index, model)
        for turn in range(12 - initial_count):
            if not backend.snapshot["conversations"]: break
            session = backend.snapshot["conversations"][0]
            count = len(session["messages"]); speaker = session["next_speaker"]
            state = graph.invoke({"name": speaker}, {"recursion_limit": 10})
            proposal = state["proposal"]
            sample["model_turns"].append({"count_before": count, "actor": speaker,
                "action": proposal["action"], "message": proposal["arguments"].get("message"),
                "native_call_id": state["selection"]["call_id"]})
            print(json.dumps({"sample": initial_count, **sample["model_turns"][-1]}, ensure_ascii=True), flush=True)
            if backend.snapshot["conversations"] and turn % 2 == 1: backend.advance()
        assert not backend.snapshot["conversations"], "模型未在有限对话机会内结束，保留该失败结果"
        ended = next(e for e in reversed(backend.snapshot["events"]) if e["type"] == "conversation_ended")
        sample["ended_reason"] = ended["payload"]["reason"]
        # 结束结果仍能被双方观察；各自认知的正常冷却后继续参加候选调度。
        for name in ("苏晚", "许宁"):
            _, memories, _ = observe(backend.snapshot, name)
            assert any(ended["id"] in m["source_event_ids"] for m in memories)
        for _ in range(6): backend.advance()
        assert {"苏晚", "许宁"} <= set(opportunities(backend.snapshot))
        sample["both_reschedulable"] = True
        sample["both_observe_end"] = True
        samples.append(sample)
    evidence = {"model": MODEL, "api_calls": total_calls, "samples": samples}
    Path("world-service/target/conversation-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=True, indent=2))


if __name__ == "__main__": main()
