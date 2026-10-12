import json
import unittest
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import patch
from openai.types.chat import ChatCompletionMessage
from agent.graph import build_graph
from agent.tick import WorldSession
from llm_client import request_decision
from tools.remote_world import RemoteWorld, RuleRejected, ACTIONS, RUNTIME_FIELDS
from characters.prompt import build_prompt


def world():
    from pathlib import Path
    template = json.loads(Path("world-service/src/main/resources/default-world-template.json").read_text(encoding="utf-8"))
    template.update(version=3, world_id="unit", revision=0, minute=480, time="早晨", tick_count=0,
                    events=[], conversations=[], invitations=[])
    for name, p in template["characters"].items():
        p.update(name=name, actor_type="npc", activity=None, mind={}, memories=[])
    return template


def selection(action="wait"):
    cognition = {"goal": "生活", "intention": "休息", "plan": [], "reflection": None,
                 "relationship_notes": {}, "next_review_minutes": 5}
    args = {"reason": "休息一下", "cognition": cognition}
    message = ChatCompletionMessage(role="assistant", tool_calls=[{
        "id": "native-call", "type": "function", "function": {"name": action, "arguments": json.dumps(args)}}])
    return message


class Backend:
    def __init__(self, failures=0):
        self.snapshot = world(); self.failures = failures; self.submissions = 0; self.successes = 0
    def load(self): return deepcopy(self.snapshot)
    def model_tools(self): return [{"type": "function", "function": {"name": "wait"}}]
    def advance(self):
        self.snapshot["minute"] += 5; self.snapshot["tick_count"] += 1
    def commit(self, actor, request_id, turn):
        self.submissions += 1
        if self.failures:
            self.failures -= 1; raise RuleRejected("先选择合法行动")
        self.successes += 1
        self.snapshot["characters"][actor]["mind"] = turn["mind"]
        return {"world": self.load(), "execution": {"id": request_id, "actor": actor, "status": "committed"}}


class NativeToolsTests(unittest.TestCase):
    def test_sdk_native_contract_and_plain_json_rejection(self):
        tools = [{"type": "function", "function": {"name": "wait"}}]
        with patch("llm_client.get_client") as client:
            create = client.return_value.chat.completions.create
            create.return_value = NS(choices=[NS(message=selection())])
            result = request_decision("本人视角", tools)
            self.assertEqual(result["proposal"]["action"], "wait")
            self.assertEqual(result["call_id"], "native-call")
            self.assertFalse(create.call_args.kwargs["parallel_tool_calls"])
            self.assertEqual(create.call_args.kwargs["tools"], tools)
            create.return_value = NS(choices=[NS(message=ChatCompletionMessage(role="assistant", content='{"action":"wait"}'))])
            with self.assertRaises(ValueError): request_decision("p", tools)
            message = selection(); message.tool_calls.append(message.tool_calls[0])
            create.return_value = NS(choices=[NS(message=message)])
            with self.assertRaises(ValueError): request_decision("p", tools)

    def test_graph_bounded_retry_and_tick_two_opportunities(self):
        backend = Backend(failures=1)
        feedback_seen = []
        def model(prompt, tools, feedback):
            feedback_seen.append(feedback)
            with patch("llm_client.get_client") as client:
                client.return_value.chat.completions.create.return_value = NS(choices=[NS(message=selection())])
                return request_decision(prompt, tools, feedback)
        index = NS(recall=lambda *_: ([], []))
        graph = build_graph(backend, index, model)
        self.assertEqual(set(graph.nodes) - {"__start__"}, {"observe", "recall", "decide", "act"})
        results = WorldSession(backend, graph).next_tick()
        self.assertEqual(len(results), 2); self.assertEqual(backend.successes, 2)
        self.assertEqual(backend.submissions, 3); self.assertEqual(backend.snapshot["minute"], 485)
        self.assertEqual(feedback_seen[1][-1]["role"], "tool")
        self.assertEqual(feedback_seen[1][-1]["tool_call_id"], "native-call")
        failing = Backend(failures=2)
        with self.assertRaises(RuntimeError): build_graph(failing, index, model).invoke({"name": "苏晚"}, {"recursion_limit": 10})
        self.assertEqual(failing.submissions, 2); self.assertEqual(failing.successes, 0)

    def test_network_confirmation_never_selects_another_action(self):
        backend = RemoteWorld("unit"); backend.snapshot = world()
        backend._tools = {"wait": NS(inputSchema={"properties": {key: {} for key in RUNTIME_FIELDS | {"reason"}}})}
        turn = {"action": "wait", "arguments": {}, "reason": "休息", "mind": {}, "memories": []}
        with patch.object(backend, "_call", side_effect=[OSError("lost"), {"status": "committed", "id": "r"}, world()]) as call:
            result = backend.commit("苏晚", "r", turn)
            self.assertEqual(result["execution"]["id"], "r")
            self.assertEqual([args.args[0] for args in call.call_args_list], ["wait", "get_execution", "get_world"])
        with patch.object(backend, "_call", side_effect=[OSError("lost"), {"status": "not_committed"}]) as call:
            with self.assertRaises(RuntimeError): backend.commit("苏晚", "r", turn)
            self.assertEqual(call.call_count, 2)

    def test_schema_projection_and_character_privacy(self):
        backend = RemoteWorld("unit")
        backend._tools = {name: NS(description=name, inputSchema={"type": "object",
            "properties": {key: {"type": "string"} for key in RUNTIME_FIELDS | {"reason"}},
            "required": list(RUNTIME_FIELDS | {"reason"})}) for name in ACTIONS}
        tools = backend.model_tools()
        self.assertEqual(len(tools), 9)
        for tool in tools:
            self.assertFalse(RUNTIME_FIELDS & tool["function"]["parameters"]["properties"].keys())
            self.assertIn("cognition", tool["function"]["parameters"]["required"])
        w = world(); p = build_prompt(w, "苏晚", {"goal": "生活", "intention": "休息"}, [], [], [], False)
        for name, person in w["characters"].items():
            if name != "苏晚":
                for secret in person["secrets"]: self.assertNotIn(secret, p)
        self.assertNotIn("只输出一个完整JSON", p)

    def test_conversation_stage_hint_only_for_own_long_conversation(self):
        w = world()
        conversation = {"participants": ["苏晚", "许宁"], "messages": []}
        w["conversations"] = [conversation]
        mind = {"goal": "生活", "intention": "交流"}
        for count in (0, 8, 9, 10, 11):
            with self.subTest(count=count):
                conversation["messages"] = [{"speaker": "许宁", "message": "最近读了什么？"}] * count
                prompt = build_prompt(w, "苏晚", mind, [], [], [], False)
                if count <= 8:
                    self.assertNotIn("对话阶段提示：", prompt)
                elif count <= 10:
                    self.assertIn("自主决定是否收尾", prompt)
                    self.assertNotIn("下一条发言将达到12条", prompt)
                else:
                    self.assertIn("自然回应、总结未完成的话题或礼貌告别", prompt)
                    self.assertIn("下一条发言将达到12条安全上限", prompt)
                other = build_prompt(w, "陈禾", mind, [], [], [], False)
                self.assertNotIn("对话阶段提示：", other)


if __name__ == "__main__": unittest.main()
