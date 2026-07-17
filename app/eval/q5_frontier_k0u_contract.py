"""K0U-B preregistered definition of a practical deterministic frontier."""

from __future__ import annotations

PRACTICAL_FRONTIER_RULES = {
    "runtime_input_only": True,
    "forbidden_inputs": [
        "identity",
        "renderer label",
        "sealed labels",
        "authored semantic representation",
        "evaluation grouping",
    ],
    "exact_policy_text_table_forbidden": True,
    "parser_frozen_before_data_commit": True,
    "posthoc_challenger_must_be_new_source_after_data_commit": True,
    "generalization_requirements": [
        "identifier-renaming invariance",
        "clause-order invariance for labeled clauses",
        "irrelevant-sentence tolerance",
        "unknown syntax abstains",
    ],
}
PRACTICAL_COMPLEXITY_BUDGET = {
    "source_nonblank_lines_max": 260,
    "regex_pattern_count_max": 12,
    "ast_branch_node_count_max": 45,
    "action_lexicon_entry_count_max": 24,
    "exact_policy_literal_length_max": 160,
    "exact_policy_literal_count_max": 0,
}
K0U_DATA_CONSTRAINTS = {
    "case_count_min": 96,
    "semantic_case_count_min": 64,
    "parser_covered_min": 32,
    "parser_uncovered_min": 32,
    "policy_fixed_pairs_per_slice_min": 8,
    "state_fixed_pairs_per_slice_min": 8,
    "family_count": 4,
    "semantic_phenomena_min": 6,
    "handwritten_policy_inventory_required": True,
    "batch_renderer_for_semantic_policies_forbidden": True,
}
K0U_CALL_PROTOCOL = {
    "llm_only_calls_scope": "all semantic cases",
    "hybrid_calls_scope": "preregistered parser abstentions only",
    "retry": 0,
    "fallback": "none",
}
K0U_POSTHOC_BOUNDARY_RULE = {
    "uncovered_coverage_min": 0.50,
    "conditional_accuracy_required": 1.0,
    "conditional_risk_required": 0.0,
    "all_conditions_required_for_boundary": True,
}
K0U_K1_GATES = {
    "oracle_resolvable_abstentions_min": 24,
    "hybrid_theoretical_call_avoidance_min": 0.40,
    "posthoc_boundary_triggered_must_be": False,
    "unsafe_terminal_max": 0,
}
