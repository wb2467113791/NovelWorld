"""可重建索引；先按角色owner过滤，再做向量检索。"""

from functools import lru_cache
from pathlib import Path
from memory.retrieval import rank
from retrieval.embedding import DashScopeEmbedder


class ChromaIndex:
    def __init__(self, world_id, root=None, embedder=None, client=None):
        if not world_id or any(c in world_id for c in "/\\."):
            raise ValueError("世界ID无效")
        import chromadb
        from chromadb.config import Settings
        self.embedder = embedder or DashScopeEmbedder()
        root = Path(root or Path(__file__).resolve().parents[1] / "data" / "chroma")
        self.client = client or chromadb.PersistentClient(
            path=str(root / world_id / f"social-{self.embedder.model}-{self.embedder.dimensions}"),
            settings=Settings(anonymized_telemetry=False))
        self.memories = self.client.get_or_create_collection("memories", embedding_function=None, metadata={"hnsw:space": "cosine"})
        self.lore = self.client.get_or_create_collection("lore", embedding_function=None, metadata={"hnsw:space": "cosine"})

    def _sync(self, collection, documents, where=None):
        old = collection.get(where=where, include=["documents", "metadatas"])
        present = {key: (text, meta) for key, text, meta in zip(old["ids"], old["documents"], old["metadatas"])}
        removed = set(present) - set(documents)
        if removed:
            collection.delete(ids=list(removed))
        changed = [key for key, value in documents.items() if present.get(key) != value]
        for start in range(0, len(changed), 20):
            ids = changed[start:start + 20]
            texts = [documents[key][0] for key in ids]
            collection.upsert(ids=ids, documents=texts, metadatas=[documents[key][1] for key in ids], embeddings=self.embedder.embed(texts))

    @lru_cache(maxsize=128)
    def vector(self, query):
        return self.embedder.embed([query])[0]

    def recall(self, world, name, memories, query):
        # 近期窗口直接进Prompt；长期候选才进入Chroma，避免同一经历重复占上下文。
        archive = memories[:-8]
        # 同一个事件可以被多人感知，collection中的ID也必须包含owner。
        docs = {f"{name}:{m['id']}": (m["content"], {"owner": name, "minute": m["minute"], "importance": m["importance"], "kind": m["kind"]}) for m in archive}
        self._sync(self.memories, docs, {"owner": name})
        lore_docs = {l["id"]: (l["text"], {"audience": l["audience"]}) for l in world["lore"]}
        self._sync(self.lore, lore_docs)
        recalled = []
        if docs:
            result = self.memories.query(query_embeddings=[self.vector(query)], n_results=min(len(docs), 16),
                                         where={"owner": name}, include=["documents", "metadatas", "distances"])
            recalled = rank(result["documents"][0], result["metadatas"][0], result["distances"][0], world["minute"])
        visible_count = sum(l["audience"] in ("public", name) for l in world["lore"])
        lore = []
        if visible_count:
            result = self.lore.query(query_embeddings=[self.vector(query)], n_results=min(visible_count, 3),
                                    where={"$or": [{"audience": "public"}, {"audience": name}]}, include=["documents"])
            lore = result["documents"][0]
        return recalled, lore
