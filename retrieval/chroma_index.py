"""按世界隔离的本地 Chroma 检索索引；JSON 存档才是事实来源。"""

from pathlib import Path

from characters.model import Character
from lore.catalog import load_lore
from memory.retrieval import eligible_archived_entries
from retrieval.text import bigrams, text_vector


DEFAULT_INDEX_ROOT = Path(__file__).resolve().parents[1] / "data" / "chroma"


class ChromaIndex:
    def __init__(self, world_id: str, root: Path = DEFAULT_INDEX_ROOT) -> None:
        if not world_id or any(char in world_id for char in "/\\."):
            raise ValueError("世界 ID 无效")
        import chromadb
        from chromadb.config import Settings

        self.world_id = world_id
        self.path = Path(root) / world_id
        self.client = chromadb.PersistentClient(
            path=str(self.path), settings=Settings(anonymized_telemetry=False)
        )
        self.memories = self.client.get_or_create_collection(
            name="npc_memories", embedding_function=None
        )
        self.lore = self.client.get_or_create_collection(
            name="world_lore", embedding_function=None
        )

    @staticmethod
    def _sync_collection(collection, documents: dict[str, tuple[str, dict]], *, where: dict | None = None) -> None:
        existing = set(collection.get(where=where, include=[])["ids"])
        desired = set(documents)
        obsolete = existing - desired
        if obsolete:
            collection.delete(ids=sorted(obsolete))
        if documents:
            ids = list(documents)
            collection.upsert(
                ids=ids,
                documents=[documents[item][0] for item in ids],
                embeddings=[text_vector(documents[item][0]) for item in ids],
                metadatas=[documents[item][1] for item in ids],
            )

    def sync_character(self, character: Character) -> None:
        """从角色记忆重建其索引，并移除被新调查取代的旧内容。"""
        documents: dict[str, tuple[str, dict]] = {}
        order_by_event = {
            entry.source_event_id: index
            for index, entry in enumerate(character.memory.all_entries())
            if entry.source_event_id is not None
        }
        for order, entry in eligible_archived_entries(character):
            documents[entry.id] = (
                entry.content,
                {"owner": character.name, "kind": "episodic",
                 "importance": entry.importance, "order": order,
                 "source_event_id": entry.source_event_id or ""},
            )
        for fact in character.semantic_memory.current_facts():
            documents[fact.id] = (
                fact.content,
                {"owner": character.name, "kind": "semantic",
                 "importance": 3,
                 "order": order_by_event.get(fact.source_event_id, 0),
                 "source_event_id": fact.source_event_id},
            )
        self._sync_collection(self.memories, documents, where={"owner": character.name})

    def sync_lore(self) -> None:
        """世界设定只从人工维护的资料重建，不混入角色私有经历。"""
        documents = {
            entry.id: (entry.text, {"category": entry.category, "audience": entry.audience})
            for entry in load_lore()
        }
        self._sync_collection(self.lore, documents)

    def sync_world(self, characters: dict[str, Character]) -> None:
        for character in characters.values():
            self.sync_character(character)
        self.sync_lore()

    def retrieve_memory(
        self, character: Character, query: str, *, max_items: int = 3, max_chars: int = 600,
    ) -> list[str]:
        self.sync_character(character)
        count = len(self.memories.get(where={"owner": character.name}, include=[])["ids"])
        if not count or not query.strip():
            return []
        response = self.memories.query(
            query_embeddings=[text_vector(query)],
            n_results=min(count, max_items * 8),
            where={"owner": character.name},
            include=["documents", "metadatas", "distances"],
        )
        recent_sources = {
            entry.source_event_id for entry in character.memory.recent_entries()
        }
        total = max(len(character.memory.all_entries()), 1)
        ranked = []
        for document, metadata, distance in zip(
            response["documents"][0], response["metadatas"][0], response["distances"][0]
        ):
            if metadata["source_event_id"] in recent_sources:
                continue
            similarity = 1 / (1 + distance)
            score = (0.6 * similarity + 0.25 * metadata["importance"] / 5
                     + 0.15 * (metadata["order"] + 1) / total)
            label = "已核实调查" if metadata["kind"] == "semantic" else "历史经历"
            ranked.append((score, f"{label}：{document}"))
        ranked.sort(reverse=True)
        selected: list[str] = []
        for _, item in ranked:
            if len(selected) >= max_items:
                break
            if len(item) <= max_chars:
                selected.append(item)
                max_chars -= len(item)
        return selected

    def retrieve_lore(
        self, character_name: str, query: str, *, max_items: int = 2, max_chars: int = 350,
    ) -> list[str]:
        self.sync_lore()
        if not query.strip():
            return []
        response = self.lore.query(
            query_embeddings=[text_vector(query)],
            n_results=min(self.lore.count(), max_items * 8),
            where={"$or": [{"audience": "public"}, {"audience": character_name}]},
            include=["documents", "metadatas", "distances"],
        )
        selected: list[str] = []
        terms = bigrams(query)
        for document, metadata in zip(response["documents"][0], response["metadatas"][0]):
            if not terms & bigrams(document + metadata["category"]):
                continue
            item = f"世界设定（{metadata['category']}）：{document}"
            if len(item) <= max_chars:
                selected.append(item)
                max_chars -= len(item)
            if len(selected) >= max_items:
                break
        return selected
