"""V3 本机 Web 控制器；Java MCP 仍是世界业务的唯一执行方。"""

import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.director import Director
from run_world import WorldSession, make_graph_decide_action
from world.persistence import DEFAULT_SAVE_PATH, load_world, restore_snapshot, save_world, snapshot_world
from world.state import WORLD_STATE


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "web" / "dist"


class RunRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=100)
    delay_seconds: float = Field(default=1, ge=0, le=30)


class WorldController:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.pause_requested = threading.Event()
        self.worker: threading.Thread | None = None
        self.subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self.error: str | None = None
        self.session: WorldSession | None = None

    def initialize(self) -> None:
        from llm_client import request_npc_graph_response
        from retrieval.chroma_index import ChromaIndex
        from tools.remote_world import RemoteWorld, use_backend

        scheduler_state = load_world(DEFAULT_SAVE_PATH) if DEFAULT_SAVE_PATH.exists() else None
        if os.environ.get("NOVELWORLD_BACKEND", "mcp") == "mcp":
            backend = RemoteWorld(WORLD_STATE["world_id"])
            scheduler_state = restore_snapshot(backend.open(snapshot_world(scheduler_state=scheduler_state)))
            use_backend(backend)
        else:
            use_backend(None)
        index = ChromaIndex(WORLD_STATE["world_id"])
        index.sync_world(WORLD_STATE["characters"])
        if not DEFAULT_SAVE_PATH.exists():
            save_world(DEFAULT_SAVE_PATH, scheduler_state=scheduler_state)
        self.session = WorldSession(
            make_graph_decide_action(request_npc_graph_response, index),
            save_path=DEFAULT_SAVE_PATH, index=index, scheduler_state=scheduler_state,
            director=Director(),
        )

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "world_id": WORLD_STATE["world_id"],
                "time": WORLD_STATE["time"],
                "tick_count": self.session.completed_ticks if self.session else 0,
                "event_count": len(WORLD_STATE["events"]),
                "locations": WORLD_STATE["locations"],
                "characters": {
                    name: {
                        "name": character.name,
                        "role": character.role,
                        "location": character.location,
                        "energy": character.energy,
                        "goals": character.goals,
                        "items": character.items,
                        "relationships": character.relationships,
                    }
                    for name, character in WORLD_STATE["characters"].items()
                },
                "events": WORLD_STATE["events"][-80:],
                "running": self.worker is not None and self.worker.is_alive(),
                "error": self.error,
            }

    def character_view(self, name: str) -> dict:
        with self.lock:
            character = WORLD_STATE["characters"].get(name)
            if character is None:
                raise KeyError(name)
            return {
                "name": name,
                "role": character.role,
                "personality": character.personality,
                "goals": character.goals,
                "known_facts": character.known_facts,
                "recent_memories": [entry.content for entry in character.memory.recent_entries()],
                "archived_memories": [entry.content for entry in character.memory.archived_entries()[-20:]],
                "semantic_facts": [fact.observation for fact in character.semantic_memory.current_facts()],
            }

    def publish(self) -> None:
        payload = json.dumps(self.snapshot(), ensure_ascii=False)
        for loop, queue in tuple(self.subscribers):
            def enqueue(target=queue, value=payload):
                if target.full():
                    target.get_nowait()
                target.put_nowait(value)
            loop.call_soon_threadsafe(enqueue)

    def start(self, count: int, delay_seconds: float) -> None:
        if self.worker is not None and self.worker.is_alive():
            raise RuntimeError("世界已在运行")
        self.pause_requested.clear()
        self.error = None

        def work():
            try:
                for index in range(count):
                    if self.pause_requested.is_set():
                        break
                    with self.lock:
                        self.session.next_tick()
                    self.publish()
                    if index + 1 < count and self.pause_requested.wait(delay_seconds):
                        break
            except Exception as error:
                self.error = str(error)
            finally:
                self.publish()

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def pause(self) -> None:
        self.pause_requested.set()
        self.publish()


controller = WorldController()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(controller.initialize)
    yield
    controller.pause()
    if controller.worker is not None:
        controller.worker.join(timeout=5)


app = FastAPI(title="NovelWorld V3", lifespan=lifespan)


@app.get("/api/world")
def get_world():
    return controller.snapshot()


@app.get("/api/characters/{name}/view")
def get_character_view(name: str):
    try:
        return controller.character_view(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="角色不存在") from None


@app.post("/api/control/next", status_code=202)
def next_tick():
    try:
        controller.start(1, 0)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"accepted": True}


@app.post("/api/control/run", status_code=202)
def run_ticks(request: RunRequest):
    try:
        controller.start(request.count, request.delay_seconds)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"accepted": True}


@app.post("/api/control/pause")
def pause():
    controller.pause()
    return {"paused": True}


@app.get("/api/events")
async def stream_events():
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=20)
    subscriber = (asyncio.get_running_loop(), queue)
    controller.subscribers.add(subscriber)

    async def stream():
        try:
            yield "event: state\ndata: " + json.dumps(controller.snapshot(), ensure_ascii=False) + "\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: state\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            controller.subscribers.discard(subscriber)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/")
def home():
    index = DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="请先在 web 目录运行 npm run build")
    return FileResponse(index)
