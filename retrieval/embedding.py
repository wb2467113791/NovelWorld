"""使用独立的文本向量模型；NPC 和 Director 的生成模型保持不变。"""

from math import isfinite


EMBEDDING_MODEL = "qwen3.7-text-embedding"
EMBEDDING_DIMENSIONS = 1024
EMBEDDING_BATCH_SIZE = 20


class DashScopeEmbedder:
    model = EMBEDDING_MODEL
    dimensions = EMBEDDING_DIMENSIONS

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # 复用现有百炼客户端和密钥；导入延迟到实际请求，便于无密钥测试。
        from llm_client import client

        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start:start + EMBEDDING_BATCH_SIZE]
            response = client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(batch))):
                raise ValueError("向量模型返回的文本序号不完整")
            for item in ordered:
                vector = item.embedding
                if len(vector) != self.dimensions or not all(isfinite(value) for value in vector):
                    raise ValueError("向量模型返回了无效维度或数值")
                vectors.append(vector)
        return vectors
