from enum import StrEnum


class DocumentStatus(StrEnum):
    active = "active"
    draft = "draft"
    deprecated = "deprecated"
    archived = "archived"


class DocumentType(StrEnum):
    prd = "prd"
    api_spec = "api_spec"
    tech_design = "tech_design"
    meeting_notes = "meeting_notes"
    test_plan = "test_plan"
    deployment_guide = "deployment_guide"
    security_policy = "security_policy"
    data_governance = "data_governance"
    faq = "faq"
    changelog = "changelog"
    handbook = "handbook"
    public_doc = "public_doc"


class AccessLevel(StrEnum):
    public = "public"
    internal = "internal"
    confidential = "confidential"
    restricted = "restricted"


class CorpusSource(StrEnum):
    synthetic_fixture = "synthetic_fixture"
    public_external = "public_external"
    hard_negative = "hard_negative"
    redteam_injection = "redteam_injection"
    agent_residual = "agent_residual"


class SourceOrigin(StrEnum):
    generated = "generated"
    public_web = "public_web"
    public_repo = "public_repo"


class MetadataOrigin(StrEnum):
    native = "native"
    overlay = "overlay"


class QueryType(StrEnum):
    single_doc_fact = "single_doc_fact"
    multi_doc_synthesis = "multi_doc_synthesis"
    no_evidence = "no_evidence"
    permission_denied = "permission_denied"
    deprecated_doc = "deprecated_doc"
    conflict_doc = "conflict_doc"
    citation_required = "citation_required"
    hard_negative = "hard_negative"
    fact_lookup = "fact_lookup"
    section_lookup = "section_lookup"
    no_evidence_or_out_of_scope = "no_evidence_or_out_of_scope"
    unknown = "unknown"


class EvalSplit(StrEnum):
    fixture = "fixture"
    external = "external"
    hard_negative = "hard_negative"
    obfuscated = "obfuscated"
    redteam = "redteam"
    agent_residual = "agent_residual"


class QuerySource(StrEnum):
    real_user_question = "real_user_question"
    manifest_authored = "manifest_authored"
    manual_adversarial = "manual_adversarial"
    manual_adversarial_rewrite = "manual_adversarial_rewrite"


class QueryStyle(StrEnum):
    standard = "standard"
    obfuscated = "obfuscated"


class ExpectedBehavior(StrEnum):
    answer = "answer"
    refuse_no_evidence = "refuse_no_evidence"
    refuse_permission = "refuse_permission"
    warn_deprecated = "warn_deprecated"
    report_conflict = "report_conflict"
    system_error = "system_error"


class DecisionReason(StrEnum):
    none = "none"
    no_evidence = "no_evidence"
    permission_denied = "permission_denied"
    deprecated_only = "deprecated_only"
    conflict_detected = "conflict_detected"
    unverifiable_citation = "unverifiable_citation"
    system_error = "system_error"


class RetrievalSource(StrEnum):
    vector = "vector"
    keyword = "keyword"
    hybrid = "hybrid"
    rerank = "rerank"


class CitationSupportType(StrEnum):
    direct = "direct"
    partial = "partial"
    contextual = "contextual"


class CitationVerificationStatus(StrEnum):
    unchecked = "unchecked"
    supported = "supported"
    weak = "weak"
    unsupported = "unsupported"
    not_checked = "not_checked"
