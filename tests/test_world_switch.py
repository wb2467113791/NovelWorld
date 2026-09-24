import unittest
from copy import deepcopy
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.remote_world import active_backend, use_backend
from web_api import WorldController
from lore.catalog import retrieve_lore
from world.persistence import restore_snapshot, snapshot_world
from world.state import WORLD_STATE


class WorldSwitchTest(unittest.TestCase):
    def setUp(self):
        # 保留预设角色对象的引用，避免影响其他测试对 CHARACTERS 的断言。
        self.original_world = WORLD_STATE.copy()
        self.original_backend = active_backend()

    def tearDown(self):
        WORLD_STATE.clear()
        WORLD_STATE.update(self.original_world)
        use_backend(self.original_backend)

    def test_switch_loads_independent_world_and_restores_old_on_failure(self):
        controller = WorldController()
        old_scheduler = Mock()
        old_scheduler.snapshot.return_value = {"next_index": 1, "tick_count": 4}
        old_session = SimpleNamespace(scheduler=old_scheduler, completed_ticks=4)
        controller.session = old_session
        old_backend = Mock()
        use_backend(old_backend)

        old_snapshot = deepcopy(snapshot_world(scheduler_state={"next_index": 1, "tick_count": 4}))
        new_world = deepcopy(old_snapshot)
        new_world["world_id"] = "another_world"
        new_world["scheduler"] = {"next_index": 0, "tick_count": 0}
        new_world["characters"]["林默"]["goals"] = ["寻找一封信"]
        new_world["lore"] = [{"id": "new-lore", "category": "地理",
                              "audience": "public", "text": "新的世界设定"}]
        new_backend = Mock()
        new_backend.load.return_value = new_world
        new_session = SimpleNamespace(scheduler=Mock(), completed_ticks=0)
        new_session.scheduler.snapshot.return_value = {"next_index": 0, "tick_count": 0}

        with patch("tools.remote_world.RemoteWorld", return_value=new_backend), \
                patch("web_api.save_world"), \
                patch.object(controller, "_new_session", return_value=new_session):
            result = controller.activate_world("another_world")
        self.assertEqual(result["world_id"], "another_world")
        self.assertEqual(WORLD_STATE["characters"]["林默"].goals, ["寻找一封信"])
        self.assertEqual(WORLD_STATE["lore"][0]["text"], "新的世界设定")
        self.assertIs(active_backend(), new_backend)
        old_backend.save_agent_state.assert_called_once_with({"next_index": 1, "tick_count": 4})

        old_remote = Mock()
        old_remote.load.return_value = old_snapshot
        with patch("tools.remote_world.RemoteWorld", return_value=old_remote), \
                patch("web_api.save_world"), \
                patch.object(controller, "_new_session", side_effect=ValueError("索引初始化失败")):
            with self.assertRaisesRegex(ValueError, "索引初始化失败"):
                controller.activate_world(self.original_world["world_id"])
        self.assertEqual(WORLD_STATE["world_id"], "another_world")
        self.assertIs(controller.session, new_session)
        self.assertIs(active_backend(), new_backend)

    def test_running_world_cannot_be_switched(self):
        controller = WorldController()
        controller.session = SimpleNamespace(completed_ticks=0)
        controller.worker = SimpleNamespace(is_alive=lambda: True)
        with self.assertRaisesRegex(RuntimeError, "暂停"):
            controller.activate_world("another_world")

    def test_status_remains_available_during_slow_tick(self):
        controller = WorldController()
        entered, release, completed = Event(), Event(), Event()
        def slow_tick():
            with controller.lock:
                entered.set()
                release.wait(2)
        worker = Thread(target=slow_tick)
        worker.start()
        self.assertTrue(entered.wait(1))
        result = {}
        def read_status():
            result.update(controller.status())
            completed.set()
        reader = Thread(target=read_status)
        reader.start()
        try:
            self.assertTrue(completed.wait(.5), "状态查询不应被 Tick 锁阻塞")
            self.assertIn("world_id", result)
        finally:
            release.set()
            worker.join(2)
            reader.join(2)

    def test_custom_opening_uses_only_its_own_lore(self):
        opening = deepcopy(snapshot_world())
        opening["world_id"] = "isolated_lore_world"
        opening["lore"] = [{"id": "new-place", "category": "地理",
                            "audience": "public", "text": "南港有一座灯塔"}]
        restore_snapshot(opening)
        self.assertTrue(retrieve_lore("林默", "南港灯塔"))
        self.assertFalse(retrieve_lore("林默", "县衙卷宗"))


if __name__ == "__main__":
    unittest.main()
