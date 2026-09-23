"""无需模型下载的中文字符片段检索基线。"""

from hashlib import blake2b
from math import sqrt


VECTOR_DIMS = 384


def bigrams(text: str) -> set[str]:
    normalized = "".join(char.lower() for char in text if char.isalnum())
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index:index + 2] for index in range(len(normalized) - 1)}


def text_vector(text: str) -> list[float]:
    """将字符片段稳定映射到固定维度；同义词能力有限。"""
    normalized = "".join(char.lower() for char in text if char.isalnum())
    pieces = [(normalized[index:index + 2], 1.0) for index in range(len(normalized) - 1)]
    pieces += [(char, 0.25) for char in normalized]
    vector = [0.0] * VECTOR_DIMS
    for piece, weight in pieces:
        position = int.from_bytes(blake2b(piece.encode("utf-8"), digest_size=8).digest(), "big") % VECTOR_DIMS
        vector[position] += weight
    length = sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else vector
