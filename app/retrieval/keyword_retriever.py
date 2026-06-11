from app.index.keyword_store import KeywordStore
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk


class KeywordRetriever:
    def __init__(self, keyword_store: KeywordStore) -> None:
        self.keyword_store = keyword_store

    def retrieve(
        self,
        query: str,
        options: RetrievalOptions | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        retrieval_options = options or RetrievalOptions()
        results = self.keyword_store.search(
            query=query,
            top_k=retrieval_options.top_k_sparse,
            filters=filters,
        )
        return [
            result.model_copy(update={"rank": rank})
            for rank, result in enumerate(results, start=1)
        ]

