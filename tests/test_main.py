import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
