import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_client import chat_with_tools
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


if __name__ == "__main__":
    unittest.main()
