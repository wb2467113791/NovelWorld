"""用本地替身验证向量索引，不请求百炼模型。"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import chromadb
from characters.model import Character
from retrieval.chroma_index import ChromaIndex
from retrieval.embedding import DashScopeEmbedder
from world.state import WORLD_STATE


class FakeEmbedder:
    model = "test-embedding"
    dimensions = 4

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [[float(len(text) % 7 + 1), 1.0, 2.0, 3.0] for text in texts]


class ChromaEmbeddingTest(unittest.TestCase):
    def test_sync_only_embeds_changes_and_retrieval_respects_owner_and_audience(self):
        character = Character("林默", "捕快", "", "", ["调查失踪案"], "客栈", 80)
        for index in range(6):
            character.memory.add(f"关于失踪案的第{index}条经历")
        previous_lore = WORLD_STATE["lore"]
        WORLD_STATE["lore"] = [
            {"id": "public", "text": "客栈有人失踪", "category": "地点", "audience": "public"},
            {"id": "private", "text": "林默收到密信", "category": "人物", "audience": "林默"},
            {"id": "hidden", "text": "苏晚的秘密", "category": "人物", "audience": "苏晚"},
        ]
        try:
            embedder = FakeEmbedder()
            index = ChromaIndex("test-world", Path("unused"), embedder, chromadb.EphemeralClient())
            self.assertEqual(index.path.name, "test-embedding-4")
            index.sync_world({character.name: character})
            self.assertEqual(len(embedder.calls), 2)
            index.sync_world({character.name: character})
            self.assertEqual(len(embedder.calls), 2)

            memories = index.retrieve_memory(character, "失踪案 客栈")
            lore = index.retrieve_lore(character.name, "失踪案 客栈")
            self.assertTrue(any("第0条经历" in item for item in memories))
            self.assertEqual(len(embedder.calls), 3)  # 同一查询在记忆和设定间复用向量。
            self.assertEqual(len(lore), 2)
            self.assertFalse(any("苏晚的秘密" in item for item in lore))
        finally:
            WORLD_STATE["lore"] = previous_lore

    def test_dashscope_adapter_batches_and_restores_response_order(self):
        calls = []

        def create(*, model, input, dimensions):
            calls.append((model, list(input), dimensions))
            data = [SimpleNamespace(index=index, embedding=[float(index)] * dimensions)
                    for index in reversed(range(len(input)))]
            return SimpleNamespace(data=data)

        fake_module = SimpleNamespace(client=SimpleNamespace(embeddings=SimpleNamespace(create=Mock(side_effect=create))))
        with patch.dict(sys.modules, {"llm_client": fake_module}):
            vectors = DashScopeEmbedder().embed([f"文本{index}" for index in range(21)])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], "qwen3.7-text-embedding")
        self.assertEqual(calls[0][2], 1024)
        self.assertEqual([len(call[1]) for call in calls], [20, 1])
        self.assertEqual([vector[0] for vector in vectors[:3]], [0.0, 1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
