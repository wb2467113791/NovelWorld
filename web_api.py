"""Spring Boot 背后的内部 Python Agent Runtime。"""

import asyncio
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.director import Director
from run_world import WorldSession, make_graph_decide_action
from world.persistence import DEFAULT_SAVE_PATH, load_world, restore_snapshot, save_world, snapshot_world
from world.state import WORLD_STATE


class RunRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=100)
    delay_seconds: float = Field(default=1, ge=0, le=30)


class ActivateRequest(BaseModel):
    world_id: str = Field(min_length=1)


class WorldController:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.pause_requested = threading.Event()
        self.worker: threading.Thread | None = None
        self.error: str | None = None
        self.session: WorldSession | None = None

    @staticmethod
    def _request_model(conversation, allow_tools):
        from llm_client import request_npc_graph_response
        return request_npc_graph_response(conversation, allow_tools)

    @staticmethod
    def _propose_director_event(category: str, location: str) -> str:
        from llm_client import chat
        recent = "\n".join(event["description"] for event in WORLD_STATE["events"][-6:]) or "暂无"
        goals = "；".join(f"{name}：{character.goals[0]}" for name, character in WORLD_STATE["characters"].items())
        return chat(
            "你是 NovelWorld 的 Director，只提出一条可在场景中调查的环境线索。"
            "不要替 NPC 决定行动、说话或结论；线索可以不可靠。"
            f"\n触发原因：{category}\n地点：{location}\n角色目标：{goals}"
            f"\n最近事件：\n{recent}\n只输出线索内容，不超过一百字。"
        )

    def _new_session(self, scheduler_state: dict) -> WorldSession:
        from retrieval.chroma_index import ChromaIndex

        index = ChromaIndex(WORLD_STATE["world_id"])
        index.sync_world(WORLD_STATE["characters"])
        return WorldSession(
            make_graph_decide_action(self._request_model, index),
            save_path=DEFAULT_SAVE_PATH, index=index, scheduler_state=scheduler_state,
            director=Director(propose_event=self._propose_director_event), event_driven=True,
        )

    def initialize(self) -> None:
        from tools.remote_world import RemoteWorld, use_backend

        scheduler_state = load_world(DEFAULT_SAVE_PATH) if DEFAULT_SAVE_PATH.exists() else None
        if os.environ.get("NOVELWORLD_BACKEND", "mcp") != "mcp":
            raise RuntimeError("Spring Boot Web 入口要求 NOVELWORLD_BACKEND=mcp")
        backend = RemoteWorld(WORLD_STATE["world_id"])
        scheduler_state = restore_snapshot(backend.open(snapshot_world(scheduler_state=scheduler_state)))
        from world.state import reconcile_event_memories
        if reconcile_event_memories():
            backend.save_agent_state(scheduler_state)
        use_backend(backend)
        if not DEFAULT_SAVE_PATH.exists():
            save_world(DEFAULT_SAVE_PATH, scheduler_state=scheduler_state)
        self.session = self._new_session(scheduler_state)

    def activate_world(self, world_id: str) -> dict:
        from tools.remote_world import RemoteWorld, active_backend, use_backend
        from world.state import reconcile_event_memories

        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise RuntimeError("请先暂停当前世界")
            if self.session is None:
                raise RuntimeError("世界尚未初始化")
            if world_id == WORLD_STATE["world_id"]:
                return self.status()

            new_backend = RemoteWorld(world_id)
            new_snapshot = new_backend.load()  # 目标必须已由 Java 创建。
            if new_snapshot.get("world_id") != world_id:
                raise ValueError("目标世界的存档 ID 不匹配")
            old_session = self.session
            old_backend = active_backend()
            old_scheduler = old_session.scheduler.snapshot()
            old_snapshot = snapshot_world(scheduler_state=old_scheduler)
            if old_backend is not None:
                old_backend.save_agent_state(old_scheduler)
            save_world(DEFAULT_SAVE_PATH, scheduler_state=old_scheduler)

            try:
                scheduler_state = restore_snapshot(new_snapshot)
                use_backend(new_backend)
                if reconcile_event_memories():
                    new_backend.save_agent_state(scheduler_state)
                new_session = self._new_session(scheduler_state)
                save_world(DEFAULT_SAVE_PATH, scheduler_state=scheduler_state)
                self.session = new_session
                self.error = None
                return self.status()
            except Exception:
                restore_snapshot(old_snapshot)
                use_backend(old_backend)
                self.session = old_session
                save_world(DEFAULT_SAVE_PATH, scheduler_state=old_scheduler)
                raise

    def status(self) -> dict:
        # Tick 可能在 MCP、检索或模型请求中运行较久。状态查询不等待调度锁，
        # 否则 Spring Boot 的 SSE / 页面查询会在读超时后误报 Runtime 不可用。
        return {
            "world_id": WORLD_STATE["world_id"],
            "tick_count": self.session.completed_ticks if self.session else 0,
            "running": self.worker is not None and self.worker.is_alive(),
            "error": self.error,
        }

    def start(self, count: int, delay_seconds: float) -> None:
        def work():
            try:
                for index in range(count):
                    if self.pause_requested.is_set():
                        break
                    with self.lock:
                        self.session.next_tick()
                    if index + 1 < count and self.pause_requested.wait(delay_seconds):
                        break
            except Exception as error:
                self.error = str(error)

        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise RuntimeError("世界已在运行")
            self.pause_requested.clear()
            self.error = None
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()

    def pause(self) -> None:
        self.pause_requested.set()


controller = WorldController()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(controller.initialize)
    yield
    controller.pause()
    if controller.worker is not None:
        controller.worker.join(timeout=5)


app = FastAPI(title="NovelWorld Internal Agent Runtime", lifespan=lifespan)


@app.get("/internal/status")
def get_status():
    return controller.status()


@app.post("/internal/control/next", status_code=202)
def next_tick():
    try:
        controller.start(1, 0)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"accepted": True}


@app.post("/internal/control/run", status_code=202)
def run_ticks(request: RunRequest):
    try:
        controller.start(request.count, request.delay_seconds)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"accepted": True}


@app.post("/internal/control/pause")
def pause():
    controller.pause()
    return {"paused": True}


@app.post("/internal/control/activate")
def activate(request: ActivateRequest):
    try:
        return controller.activate_world(request.world_id)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
