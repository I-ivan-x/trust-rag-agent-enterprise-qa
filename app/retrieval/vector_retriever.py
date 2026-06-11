from app.index.embedding_service import BaseEmbeddingService
from app.index.vector_store import VectorStore
from app.schemas.retrieval import RetrievalOptions, RetrievedChunk


class VectorRetriever:
    def __init__(
        self,
        embedding_service: BaseEmbeddingService,
        vector_store: VectorStore,
    ) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def retrieve(
        self,
        query: str,
        options: RetrievalOptions | None = None,
        filters: dict | None = None,
    ) -> list[RetrievedChunk]:
        retrieval_options = options or RetrievalOptions()
        query_vector = self.embedding_service.embed_query(query)
        results = self.vector_store.search(
            query_vector=query_vector,
            top_k=retrieval_options.top_k_dense,
            filters=filters,
        )
        return [
            result.model_copy(update={"rank": rank})
            for rank, result in enumerate(results, start=1)
        ]

