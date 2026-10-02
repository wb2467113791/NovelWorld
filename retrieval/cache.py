"""Redis 缓存向量，不缓存模型决策。服务不可用时短路并继续直连向量接口。"""

import hashlib
import json
import os
import time


class EmbeddingCache:
    def __init__(self):
        self.client = None
        self.retry_at = 0
        self.hits = 0
        self.misses = 0
        self.warning = None

    def _client(self):
        if time.monotonic() < self.retry_at:
            return None
        if self.client is None:
            try:
                import redis
                self.client = redis.Redis.from_url(os.getenv("NOVELWORLD_REDIS_URL", "redis://127.0.0.1:6380/0"),
                                                   socket_connect_timeout=0.2, socket_timeout=0.2, decode_responses=True)
            except ImportError:
                self.warning = "Redis客户端未安装，向量缓存暂未启用"
                self.retry_at = time.monotonic() + 60
        return self.client

    @staticmethod
    def key(model, dimensions, text):
        digest = hashlib.sha256(f"{model}\0{dimensions}\0{text}".encode()).hexdigest()
        return "novelworld:embedding:" + digest

    def get(self, key, dimensions):
        client = self._client()
        if client is not None:
            try:
                value = client.get(key)
                vector = json.loads(value) if value else None
                if isinstance(vector, list) and len(vector) == dimensions and all(type(x) in (int, float) for x in vector):
                    from math import isfinite
                    if all(isfinite(x) for x in vector):
                        self.hits += 1; self.warning = None
                        return vector
            except Exception:
                self.warning = "Redis暂不可用，使用原向量接口"
                self.retry_at = time.monotonic() + 60
        self.misses += 1
        return None

    def put(self, key, vector):
        client = self._client()
        if client is not None:
            try:
                client.setex(key, 7 * 86400, json.dumps(vector, allow_nan=False))
                self.warning = None
            except Exception:
                self.warning = "Redis暂不可用，使用原向量接口"
                self.retry_at = time.monotonic() + 60
