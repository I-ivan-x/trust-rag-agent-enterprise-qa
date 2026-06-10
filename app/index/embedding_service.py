import hashlib


class MockEmbeddingService:
    """Deterministic smoke-test embeddings; never use for formal evaluation metrics."""

    def __init__(self, dimension: int = 16) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        values: list[float] = []
        for index in range(self.dimension):
            digest = hashlib.sha256(f"{index}:{text}".encode()).digest()
            integer = int.from_bytes(digest[:8], byteorder="big", signed=False)
            values.append((integer / ((1 << 64) - 1)) * 2 - 1)
        return values
