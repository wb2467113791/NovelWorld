import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import main
from main import build_prompt, choose_character


class MainTest(unittest.TestCase):
    def test_choose_character_uses_su_wan_as_default(self):
        with patch("builtins.input", return_value=""):
            self.assertEqual(choose_character(), "苏晚")

    def test_choose_character_accepts_existing_character(self):
        with patch("builtins.input", return_value="林默"):
            self.assertEqual(choose_character(), "林默")

    def test_build_prompt_uses_selected_character(self):
        prompt = build_prompt("你是谁？", "赵无极")

        self.assertIn("姓名：赵无极", prompt)
        self.assertIn("身份：本地商会会长", prompt)

    def test_dialogue_only_offers_npc_action_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("builtins.input", side_effect=["林默", "请与苏晚交谈", "exit"]),
                patch("builtins.print"),
                patch("main.chat_with_tools", return_value="完成") as mock_chat,
                patch("main.DEFAULT_SAVE_PATH", Path(directory) / "world.json"),
                patch("main.ChromaIndex"),
            ):
                main.main()

        kwargs = mock_chat.call_args.kwargs
        tool_names = {schema["name"] for schema in kwargs["tool_schemas"]}
        self.assertEqual(kwargs["acting_character"], "林默")
        self.assertIn("talk", tool_names)
        self.assertNotIn("get_character", tool_names)


if __name__ == "__main__":
    unittest.main()
