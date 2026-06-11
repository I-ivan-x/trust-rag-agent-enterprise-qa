from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TrustRAG Enterprise QA"
    app_version: str = "0.1.0"
    task_plan_version: str = "v0.3-q1-hard-demo-plan-freeze"
    environment: str = "dev"
    debug: bool = True
    mock_mode: bool = True

    data_dir: Path = Path("data")
    generated_dir: Path = Path("data/generated")
    sample_corpus_dir: Path = Path("data/sample_corpus")
    public_corpus_dir: Path = Path("data/public_corpus")
    hard_negative_corpus_dir: Path = Path("data/hard_negative_corpus")
    gold_eval_dir: Path = Path("data/gold_eval")
    trace_dir: Path = Path("data/traces")
    eval_runs_dir: Path = Path("data/eval_runs")
    whoosh_index_dir: Path = Path("data/indexes/whoosh")

    embedding_provider: str = "sentence_transformer"
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 32
    embedding_device: str = "cpu"
    reranker_provider: str = "bge"
    reranker_model_name: str = "BAAI/bge-reranker-base"
    llm_provider: str = "mock"
    llm_model_name: str = "mock-llm-v0"

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "trust_rag_enterprise_qa"

    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 80
    max_context_tokens: int = 5000
    max_rewrite_rounds: int = 1
    eval_mode: str = "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
