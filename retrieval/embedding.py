"""现有百炼向量模型，增加按模型、维度和文本内容寻址的Redis缓存。"""

from math import isfinite
from retrieval.cache import EmbeddingCache

EMBEDDING_MODEL = "qwen3.7-text-embedding"
EMBEDDING_DIMENSIONS = 1024


class DashScopeEmbedder:
    model = EMBEDDING_MODEL
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self, cache=None):
        self.cache = cache or EmbeddingCache()

    def embed(self, texts):
        keys = [self.cache.key(self.model, self.dimensions, text) for text in texts]
        vectors = [self.cache.get(key, self.dimensions) for key in keys]
        missing = [i for i, vector in enumerate(vectors) if vector is None]
        if missing:
            from llm_client import get_client
            for start in range(0, len(missing), 20):
                positions = missing[start:start + 20]
                result = get_client().embeddings.create(model=self.model, input=[texts[i] for i in positions], dimensions=self.dimensions)
                ordered = sorted(result.data, key=lambda row: row.index)
                if [row.index for row in ordered] != list(range(len(positions))):
                    raise ValueError("向量返回序号不完整")
                for position, row in zip(positions, ordered):
                    if len(row.embedding) != self.dimensions or not all(isfinite(x) for x in row.embedding):
                        raise ValueError("向量维度或数值无效")
                    vectors[position] = row.embedding
                    self.cache.put(keys[position], row.embedding)
        return vectors
