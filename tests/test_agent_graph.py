import unittest
from types import SimpleNamespace

from langgraph.checkpoint.memory import InMemorySaver

from agent.graph import build_agent_loop_graph
from agent.state import create_initial_agent_state
from characters.presets import CHARACTERS
from world.state import WORLD_STATE


def tool_call(name: str, arguments: str, call_id: str):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=arguments,
        call_id=call_id,
    )


class AgentGraphTest(unittest.TestCase):
    def setUp(self):
        self.original_locations = {
            name: character.location for name, character in CHARACTERS.items()
        }
        self.original_memories = {
            name: character.memory.recent_entries() for name, character in CHARACTERS.items()
        }
        self.original_events = WORLD_STATE["events"].copy()

    def tearDown(self):
        for name, character in CHARACTERS.items():
            character.location = self.original_locations[name]
            character.memory.entries[:] = self.original_memories[name]
        WORLD_STATE["events"][:] = self.original_events

    def test_tool_result_returns_to_model_before_final_answer(self):
        responses = iter([
            SimpleNamespace(
                output=[tool_call(
                    "move_character",
                    '{"character":"林默","location":"晚风客栈"}',
                    "call-1",
                )],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="我已抵达客栈。"),
        ])
        requests = []

        def fake_request_model(conversation, allow_tools):
            requests.append((list(conversation), allow_tools))
            return next(responses)

        graph = build_agent_loop_graph(fake_request_model)
        result = graph.invoke(create_initial_agent_state(CHARACTERS["林默"]))

        self.assertEqual(CHARACTERS["林默"].location, "晚风客栈")
        self.assertEqual(WORLD_STATE["events"][-1]["type"], "move")
        self.assertEqual(result["final_answer"], "我已抵达客栈。")
        self.assertEqual(result["step"], 1)
        self.assertEqual([allowed for _, allowed in requests], [True, True])
        self.assertEqual(requests[1][0][-2]["type"], "function_call")
        self.assertEqual(requests[1][0][-1]["type"], "function_call_output")
        self.assertEqual(requests[1][0][-1]["call_id"], "call-1")
        self.assertIn("移动到", requests[1][0][-1]["output"])

    def test_text_answer_finishes_without_executing_tool(self):
        event_count = len(WORLD_STATE["events"])
        response = SimpleNamespace(output=[], output_text="先整理卷宗。")
        graph = build_agent_loop_graph(lambda conversation, allow_tools: response)

        result = graph.invoke(create_initial_agent_state(CHARACTERS["林默"]))

        self.assertEqual(result["final_answer"], "先整理卷宗。")
        self.assertEqual(result["step"], 0)
        self.assertEqual(result["tool_results"], [])
        self.assertEqual(len(WORLD_STATE["events"]), event_count)

    def test_tool_is_disabled_at_round_limit(self):
        responses = iter([
            SimpleNamespace(
                output=[tool_call("get_world_time", "{}", "call-2")],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="现在结束本轮行动。"),
        ])
        allowed_tools = []

        def fake_request_model(conversation, allow_tools):
            allowed_tools.append(allow_tools)
            return next(responses)

        graph = build_agent_loop_graph(fake_request_model, max_tool_rounds=1)
        result = graph.invoke(create_initial_agent_state(CHARACTERS["林默"]))

        self.assertEqual(allowed_tools, [True, False])
        self.assertEqual(result["step"], 1)
        self.assertEqual(len(result["tool_results"]), 1)
        self.assertEqual(result["final_answer"], "现在结束本轮行动。")

    def test_actor_rule_rejects_moving_another_character(self):
        responses = iter([
            SimpleNamespace(
                output=[tool_call(
                    "move_character",
                    '{"character":"苏晚","location":"县衙"}',
                    "call-3",
                )],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="这次行动不合法。"),
        ])
        graph = build_agent_loop_graph(
            lambda conversation, allow_tools: next(responses)
        )

        result = graph.invoke(create_initial_agent_state(CHARACTERS["林默"]))

        self.assertEqual(CHARACTERS["苏晚"].location, self.original_locations["苏晚"])
        self.assertEqual(WORLD_STATE["events"], self.original_events)
        self.assertIn("工具错误", result["observations"][0])
        self.assertEqual(result["tool_results"][0]["call_id"], "call-3")

    def test_missing_item_returns_explicit_observation_to_model(self):
        responses = iter([
            SimpleNamespace(
                output=[tool_call(
                    "give_item",
                    '{"giver":"苏晚","receiver":"林默","item":"不存在的钥匙"}',
                    "call-item",
                )],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="物品不存在，无法交付。"),
        ])
        requests = []

        def fake_request_model(conversation, allow_tools):
            requests.append(list(conversation))
            return next(responses)

        graph = build_agent_loop_graph(fake_request_model)
        result = graph.invoke(create_initial_agent_state(CHARACTERS["苏晚"]))

        self.assertEqual(WORLD_STATE["events"], self.original_events)
        self.assertEqual(
            result["observations"], ["工具错误：物品不存在：不存在的钥匙"],
        )
        self.assertEqual(requests[1][-1]["output"], result["observations"][0])

    def test_other_characters_facts_cannot_be_read_through_tool_call(self):
        responses = iter([
            SimpleNamespace(
                output=[tool_call(
                    "get_character", '{"character":"苏晚"}', "call-fact"
                )],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="我无法读取苏晚的私人信息。"),
        ])
        requests = []

        def fake_request_model(conversation, allow_tools):
            requests.append(list(conversation))
            return next(responses)

        graph = build_agent_loop_graph(fake_request_model)
        result = graph.invoke(create_initial_agent_state(CHARACTERS["林默"]))

        self.assertNotIn(CHARACTERS["苏晚"].secrets[0], requests[0][0]["content"])
        self.assertEqual(
            result["observations"],
            ["工具错误：林默不能通过get_character替其他角色行动"],
        )
        self.assertEqual(requests[1][-1]["output"], result["observations"][0])
        self.assertNotIn(CHARACTERS["苏晚"].secrets[0], str(requests[1]))
        self.assertEqual(WORLD_STATE["events"], self.original_events)

    def test_invalid_destination_returns_observation_without_moving(self):
        responses = iter([
            SimpleNamespace(
                output=[tool_call(
                    "move_character",
                    '{"character":"林默","location":"皇宫"}',
                    "call-location",
                )],
                output_text="",
            ),
            SimpleNamespace(output=[], output_text="皇宫不是可前往的地点。"),
        ])
        requests = []

        def fake_request_model(conversation, allow_tools):
            requests.append(list(conversation))
            return next(responses)

        graph = build_agent_loop_graph(fake_request_model)
        result = graph.invoke(create_initial_agent_state(CHARACTERS["林默"]))

        self.assertEqual(CHARACTERS["林默"].location, self.original_locations["林默"])
        self.assertEqual(WORLD_STATE["events"], self.original_events)
        self.assertEqual(result["observations"], ["工具错误：地点不存在：皇宫"])
        self.assertEqual(requests[1][-1]["output"], result["observations"][0])

    def test_initial_prompt_uses_state_snapshot_without_other_secrets(self):
        state = create_initial_agent_state(
            CHARACTERS["林默"], goal="找到失踪者的下落"
        )
        state["memories"] = ["本轮开始前整理了案卷"]
        state["observations"] = ["工具返回：案卷缺少一页"]
        CHARACTERS["林默"].memory.add("本轮启动后才写入的记忆")
        captured_prompts = []

        def fake_request_model(conversation, allow_tools):
            captured_prompts.append(conversation[0]["content"])
            return SimpleNamespace(output=[], output_text="继续调查。")

        graph = build_agent_loop_graph(fake_request_model)
        graph.invoke(state)

        prompt = captured_prompts[0]
        self.assertIn("当前目标：找到失踪者的下落", prompt)
        self.assertIn("本轮开始前整理了案卷", prompt)
        self.assertIn("工具返回：案卷缺少一页", prompt)
        self.assertNotIn("本轮启动后才写入的记忆", prompt)
        self.assertNotIn(CHARACTERS["苏晚"].secrets[0], prompt)

    def test_in_memory_checkpoint_keeps_each_thread_state_separate(self):
        response = SimpleNamespace(output=[], output_text="本轮结束。")
        graph = build_agent_loop_graph(
            lambda conversation, allow_tools: response,
            checkpointer=InMemorySaver(),
        )
        lin_mo_config = {"configurable": {"thread_id": "lin-mo-test"}}
        su_wan_config = {"configurable": {"thread_id": "su-wan-test"}}
        original_event_count = len(WORLD_STATE["events"])

        graph.invoke(
            create_initial_agent_state(CHARACTERS["林默"]),
            config=lin_mo_config,
        )
        graph.invoke(
            create_initial_agent_state(CHARACTERS["苏晚"]),
            config=su_wan_config,
        )

        lin_mo_state = graph.get_state(lin_mo_config).values
        su_wan_state = graph.get_state(su_wan_config).values
        self.assertEqual(lin_mo_state["npc_id"], "林默")
        self.assertEqual(su_wan_state["npc_id"], "苏晚")
        self.assertEqual(lin_mo_state["final_answer"], "本轮结束。")
        self.assertEqual(su_wan_state["final_answer"], "本轮结束。")
        self.assertEqual(len(WORLD_STATE["events"]), original_event_count)


if __name__ == "__main__":
    unittest.main()
