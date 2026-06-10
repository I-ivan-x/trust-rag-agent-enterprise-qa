from enum import StrEnum


class AppErrorCode(StrEnum):
    invalid_request = "INVALID_REQUEST"
    document_not_found = "DOCUMENT_NOT_FOUND"
    trace_not_found = "TRACE_NOT_FOUND"
    index_not_ready = "INDEX_NOT_READY"
    llm_unavailable = "LLM_UNAVAILABLE"
    embedding_unavailable = "EMBEDDING_UNAVAILABLE"
    reranker_unavailable = "RERANKER_UNAVAILABLE"
    permission_denied = "PERMISSION_DENIED"
    eval_config_invalid = "EVAL_CONFIG_INVALID"
    internal_error = "INTERNAL_ERROR"


class AppException(Exception):
    def __init__(
        self,
        code: AppErrorCode,
        message: str,
        status_code: int = 500,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
