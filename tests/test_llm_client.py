import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_client import chat_with_tools


class LlmClientTest(unittest.TestCase):
    @patch("llm_client.client.responses.create")
    def test_chat_with_tools_executes_function_call(self, mock_create):
        function_call = SimpleNamespace(
            type="function_call",
            name="get_world_time",
            arguments=json.dumps({}),
            call_id="call_123",
        )
        first_response = SimpleNamespace(
            output=[function_call],
            output_text="",
        )
        final_response = SimpleNamespace(
            output=[],
            output_text="现在是 08:00。",
        )
        mock_create.side_effect = [first_response, final_response]

        result = chat_with_tools("现在几点了？")

        self.assertEqual(result, "现在是 08:00。")
        self.assertEqual(mock_create.call_count, 2)

        first_request = mock_create.call_args_list[0].kwargs
        self.assertEqual(first_request["tools"][0]["name"], "get_world_time")

        second_input = mock_create.call_args_list[1].kwargs["input"]
        self.assertEqual(second_input[-2]["type"], "function_call")
        self.assertEqual(second_input[-1]["type"], "function_call_output")
        self.assertEqual(second_input[-1]["output"], "08:00")

    @patch("llm_client.client.responses.create")
    def test_chat_with_tools_returns_text_when_no_tool_is_needed(self, mock_create):
        mock_create.return_value = SimpleNamespace(
            output=[],
            output_text="我是苏晚。",
        )

        result = chat_with_tools("你是谁？")

        self.assertEqual(result, "我是苏晚。")
        self.assertEqual(mock_create.call_count, 1)


if __name__ == "__main__":
    unittest.main()
