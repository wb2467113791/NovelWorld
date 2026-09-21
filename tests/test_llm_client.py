import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_client import MODEL, chat_with_tools, request_npc_graph_response
from world.state import WORLD_STATE


def function_call(name, arguments, call_id):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=arguments,
        call_id=call_id,
    )


def text_response(text):
    return SimpleNamespace(output=[], output_text=text)


class FakeResponses:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.inputs = []
        self.requests = []

    def create(self, **kwargs):
        self.inputs.append(kwargs["input"])
        self.requests.append(kwargs)
        return next(self.responses)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


class LlmClientTest(unittest.TestCase):
    def test_graph_adapter_uses_npc_tools_and_disables_them_at_limit(self):
        fake_client = FakeClient([
            text_response("第一轮结果"),
            text_response("最终结果"),
        ])
        conversation = [{"role": "user", "content": "林默下一步做什么？"}]

        with patch("llm_client.client", fake_client):
            first = request_npc_graph_response(conversation, allow_tools=True)
            final = request_npc_graph_response(conversation, allow_tools=False)

        first_request, final_request = fake_client.responses.requests
        self.assertEqual(first.output_text, "第一轮结果")
        self.assertEqual(final.output_text, "最终结果")
        self.assertEqual(first_request["model"], MODEL)
        self.assertIs(first_request["input"], conversation)
        tool_names = {tool["name"] for tool in first_request["tools"]}
        self.assertIn("move_character", tool_names)
        self.assertNotIn("get_character", tool_names)
        self.assertEqual(final_request["model"], MODEL)
        self.assertNotIn("tools", final_request)

    def test_chat_with_tools_continues_until_model_returns_text(self):
        original_location = WORLD_STATE["characters"]["苏晚"].location
        fake_client = FakeClient(
            [
                SimpleNamespace(
                    output=[
                        function_call("get_world_time", "{}", "call-1")
                    ],
                    output_text="",
                ),
                SimpleNamespace(
                    output=[
                        function_call(
                            "move_character",
                            '{"character":"苏晚","location":"县衙"}',
                            "call-2",
                        )
                    ],
                    output_text="",
                ),
                text_response("事情已经办妥。"),
            ]
        )

        try:
            with patch("llm_client.client", fake_client):
                result = chat_with_tools("先查时间，再让苏晚去县衙。")
        finally:
            WORLD_STATE["characters"]["苏晚"].location = original_location

        self.assertEqual(result, "事情已经办妥。")
        self.assertEqual(len(fake_client.responses.inputs), 3)
        self.assertEqual(
            fake_client.responses.inputs[2][-1]["type"],
            "function_call_output",
        )

    def test_chat_with_tools_forces_text_response_at_round_limit(self):
        fake_client = FakeClient(
            [
                SimpleNamespace(
                    output=[
                        function_call("get_world_time", "{}", "call-1")
                    ],
                    output_text="",
                ),
                SimpleNamespace(
                    output=[
                        function_call("get_world_time", "{}", "call-2")
                    ],
                    output_text="",
                ),
                text_response("已根据现有观察结束本轮行动。"),
            ]
        )

        with patch("llm_client.client", fake_client):
            result = chat_with_tools("一直调用工具", max_tool_rounds=2)

        self.assertEqual(result, "已根据现有观察结束本轮行动。")
        self.assertEqual(len(fake_client.responses.requests), 3)
        self.assertNotIn("tools", fake_client.responses.requests[-1])

    def test_invalid_query_is_returned_to_model_before_valid_talk(self):
        lin_mo = WORLD_STATE["characters"]["林默"]
        original_location = lin_mo.location
        original_events = WORLD_STATE["events"].copy()
        original_memories = {
            name: character.memory.recent_entries()
            for name, character in WORLD_STATE["characters"].items()
        }
        fake_client = FakeClient([
            SimpleNamespace(
                output=[function_call(
                    "get_character", '{"character":"苏晚"}', "call-invalid"
                )],
                output_text="",
            ),
            SimpleNamespace(
                output=[function_call(
                    "talk",
                    '{"speaker":"林默","listener":"苏晚","message":"我想查失踪案"}',
                    "call-talk",
                )],
                output_text="",
            ),
            text_response("已经交谈。"),
        ])

        try:
            lin_mo.location = "晚风客栈"
            with patch("llm_client.client", fake_client), patch("builtins.print"):
                result = chat_with_tools("请与苏晚交谈", acting_character="林默")

            self.assertEqual(result, "已经交谈。")
            self.assertTrue(
                any(
                    "工具错误：林默不能通过get_character替其他角色行动"
                    in item.get("output", "")
                    for item in fake_client.responses.inputs[1]
                ),
            )
            self.assertEqual(WORLD_STATE["events"][-1]["type"], "talk")
            self.assertIn(
                "林默对我说",
                WORLD_STATE["characters"]["苏晚"].memory.recent()[-1],
            )
        finally:
            lin_mo.location = original_location
            WORLD_STATE["events"][:] = original_events
            for name, entries in original_memories.items():
                WORLD_STATE["characters"][name].memory.entries[:] = entries


if __name__ == "__main__":
    unittest.main()
