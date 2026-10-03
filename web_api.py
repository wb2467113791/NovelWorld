"""本机内部Agent控制服务；浏览器只访问Spring Boot。"""

import asyncio
import threading
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI
from pydantic import BaseModel, Field
from agent.graph import build_graph
from agent.tick import WorldSession
from tools.remote_world import RemoteWorld
from world.persistence import current_world_id, remember_world


class RunRequest(BaseModel):
    count: int = Field(default=12, ge=1, le=100)
    delay_seconds: float = Field(default=1, ge=0, le=30)


class ActivateRequest(BaseModel):
    world_id: str = Field(min_length=1, max_length=64)


class JoinRequest(ActivateRequest):
    name: str = Field(default="旅人", min_length=1, max_length=40)
    location: str = Field(min_length=1)


class ActionRequest(ActivateRequest):
    action: str
    arguments: dict = Field(default_factory=dict)


class WorldController:
    def __init__(self, request_model=None, index_factory=None):
        self.lock = threading.RLock()
        self.pause_requested = threading.Event()
        self.worker = None
        self.session = None
        self.error = None
        self.acting = None
        self.phase = "等待运行"
        self.player_pending = False
        self.player_error = None
        self.player_lock = threading.Lock()
        self._status = {"world_id": None, "tick_count": 0}
        self.request_model = request_model
        self.index_factory = index_factory

    def progress(self, name, phase):
        self.acting, self.phase = name, phase

    def _session(self, backend):
        from retrieval.chroma_index import ChromaIndex
        from llm_client import request_decision
        index = (self.index_factory or ChromaIndex)(backend.world_id)
        graph = build_graph(backend, index, self.request_model or request_decision, self.progress)
        return WorldSession(backend, graph)

    def refresh_status(self):
        world = self.session.backend.snapshot
        self._status = {"world_id": world["world_id"], "tick_count": world["tick_count"]}

    def initialize(self):
        world_id = current_world_id()
        backend = RemoteWorld(world_id)
        if world_id:
            backend.load()
        else:
            backend.initialize()
        self.session = self._session(backend)
        remember_world(backend.world_id)
        self.refresh_status()

    def activate(self, world_id):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("当前轮次正在执行，请先暂停并等待结束")
        try:
            if self.running or self.player_pending:
                raise RuntimeError("请先暂停当前世界")
            backend = RemoteWorld(world_id); backend.load()
            session = self._session(backend)
            remember_world(world_id)
            self.session = session
            self.error = None; self.acting = None; self.phase = "等待运行"
            self.refresh_status()
            return self.status()
        finally:
            self.lock.release()

    @property
    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def status(self):
        # 慢模型持锁时查询依然立即返回，SSE不会被模型请求拖住。
        return {**self._status, "running": self.running, "pausing": self.running and self.pause_requested.is_set(),
                "error": self.error, "acting": self.acting, "phase": self.phase,
                "player_pending": self.player_pending, "player_error": self.player_error}

    def start(self, count, delay):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("当前轮次正在执行")
        try:
            if self.running:
                raise RuntimeError("世界已经在运行")
            if self.session is None:
                raise RuntimeError("世界尚未初始化")
            self.pause_requested.clear(); self.error = None
            def work():
                try:
                    for turn in range(count):
                        if self.pause_requested.is_set():
                            break
                        with self.player_lock:
                            pass  # 已接收的玩家输入先结算，再开启下一轮NPC决策。
                        with self.lock:
                            try:
                                self.session.next_tick()
                                self.progress(None, "活动随时间推进")
                            finally:
                                self.refresh_status()
                        if turn + 1 < count and self.pause_requested.wait(delay):
                            break
                except Exception as error:
                    self.error = str(error)
                finally:
                    self.acting = None; self.phase = "运行中断" if self.error else "等待运行"
            self.worker = threading.Thread(target=work, name="world-agent", daemon=True)
            self.worker.start()
        finally:
            self.lock.release()
        return {"accepted": True}

    def play(self, request, join=False):
        if self.session is None:
            raise RuntimeError("世界尚未初始化")
        if not self.player_lock.acquire(blocking=False):
            raise RuntimeError("上一条玩家行动正在等待或执行")
        self.player_pending = True
        self.player_error = None
        # 玩家输入与NPC回合共享结算锁；不暂停世界，也不在慢模型调用中改写现场。
        # 当前轮次结束后优先处理等待的玩家输入。
        def apply():
            try:
                with self.lock:
                    self._apply_player(request, join)
            except Exception as error:
                self.player_error = str(error)
            finally:
                self.player_pending = False
                self.player_lock.release()
        threading.Thread(target=apply, name="world-player", daemon=True).start()
        return {"accepted": True, "queued": True}

    def _apply_player(self, request, join):
        backend = self.session.backend
        if request.world_id != backend.world_id:
            raise RuntimeError("世界已切换，请刷新页面")
        backend.load()
        if join:
            backend.join(request.name, request.location)
        else:
            player = next((name for name, p in backend.snapshot["characters"].items() if p["actor_type"] == "player"), None)
            if player is None:
                raise ValueError("请先加入世界")
            backend.commit(player, uuid4().hex, {"action": request.action, "arguments": request.arguments,
                                                 "reason": "玩家主动选择", "mind": {}, "memories": []})
        self.refresh_status()


controller = WorldController()


@asynccontextmanager
async def lifespan(_):
    await asyncio.to_thread(controller.initialize)
    yield
    controller.pause_requested.set()


app = FastAPI(title="NovelWorld Internal Agent Runtime", lifespan=lifespan)


@app.exception_handler(ValueError)
async def invalid(_, error):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={"detail": str(error)})


@app.exception_handler(RuntimeError)
async def conflict(_, error):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.get("/internal/status")
def status(): return controller.status()


@app.post("/internal/control/next", status_code=202)
def next_tick(): return controller.start(1, 0)


@app.post("/internal/control/run", status_code=202)
def run(request: RunRequest): return controller.start(request.count, request.delay_seconds)


@app.post("/internal/control/pause")
def pause():
    controller.pause_requested.set()
    return {"paused": True}


@app.post("/internal/control/activate")
def activate(request: ActivateRequest): return controller.activate(request.world_id)


@app.post("/internal/play/join")
def join(request: JoinRequest): return controller.play(request, join=True)


@app.post("/internal/play/action")
def action(request: ActionRequest): return controller.play(request)
