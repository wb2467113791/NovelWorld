"""记忆候选按语义相关性、新近程度与重要性排序。"""


def rank(documents, metadatas, distances, now, max_items=4):
    rows = []
    for text, meta, distance in zip(documents, metadatas, distances):
        relevance = 1 / (1 + max(distance, 0))
        recency = 1 / (1 + max(0, now - meta["minute"]) / 120)
        score = 0.55 * relevance + 0.25 * meta["importance"] / 5 + 0.20 * recency
        rows.append((score, text))
    return [text for _, text in sorted(rows, key=lambda item: item[0], reverse=True)[:max_items]]
