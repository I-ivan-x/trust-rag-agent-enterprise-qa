import presentationCatalog from "../data/presentation-zh-cn.json";

export type ClaimStatus =
  | "demonstrated_in_frozen_scope"
  | "falsified_in_current_scope"
  | "not_evaluated"
  | "mixed_scoped_results"
  | "scoped_negative_complete";

export type Metric = {
  value: number;
  numerator: number;
  denominator: number;
  unit: string;
};

export type PublicClaim = {
  claim_id: string;
  status: string;
  headline_eligible: boolean;
  metrics: Record<string, Metric>;
  presentation: {
    locale: "zh-CN";
    label: string;
    status: string;
    claim_scope: string;
    frozen_scope: string;
    limitations: string[];
    summary: string;
    meaning: string;
    headline_eligible: boolean;
    canonical_status: string;
    metric_labels: Record<string, string>;
  };
};

const requiredLabel = (labels: Record<string, string>, key: string, kind: string): string => {
  const value = labels[key];
  if (!value) throw new Error(`未知${kind}：${key}`);
  return value;
};

export const questionLabel = (questionId: string, _fallback?: string): string =>
  requiredLabel(presentationCatalog.question_labels, questionId, "问题标识");

export const claimLabel = (claim: PublicClaim): string => claim.presentation.label;

export const claimScope = (claim: PublicClaim): string => claim.presentation.claim_scope;

export const frozenScope = (claim: PublicClaim): string => claim.presentation.frozen_scope;

export const limitations = (claim: PublicClaim): string[] => claim.presentation.limitations;

export const claimSummary = (claim: PublicClaim): string => claim.presentation.summary;

export const claimMeaning = (claim: PublicClaim): string => claim.presentation.meaning;

export const metricLabel = (name: string): string =>
  requiredLabel(presentationCatalog.metric_labels, name, "指标键");

export const evidenceModeLabel = (mode: string): string =>
  requiredLabel(presentationCatalog.evidence_mode_labels, mode, "证据模式");

export const derivationLabel = (derivation: string): string =>
  requiredLabel(presentationCatalog.derivation_labels, derivation, "指标推导方式");

export const booleanLabel = (value: boolean): string => (value ? "是" : "否");

export const statusLabel = (status: string): string =>
  requiredLabel(presentationCatalog.status_labels, status, "状态");

export const statusTone = (status: string): string => {
  if (status === "demonstrated_in_frozen_scope") return "status-pass";
  if (status === "falsified_in_current_scope" || status === "scoped_negative_complete") {
    return "status-reject";
  }
  if (status === "mixed_scoped_results") return "status-warn";
  return "status-neutral";
};

export const metricValue = (metric: Metric, digits = 2): string => {
  if (metric.unit === "boolean_rate") return metric.value === 1 ? "通过" : "未通过";
  return metric.value.toFixed(digits);
};

export const metricPercent = (metric: Metric, digits = 1): string =>
  `${(metric.value * 100).toFixed(digits)}%`;

export const fraction = (metric: Metric): string => {
  const format = (value: number) => (Number.isInteger(value) ? String(value) : String(value));
  return `${format(metric.numerator)}/${format(metric.denominator)}`;
};
