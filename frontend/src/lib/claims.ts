export type ClaimStatus =
  | "demonstrated_in_frozen_scope"
  | "falsified_in_current_scope"
  | "not_evaluated"
  | "mixed_scoped_results"
  | "scoped_negative_complete";

type Metric = {
  value: number;
  numerator: number;
  denominator: number;
  unit: string;
};

export const statusLabel = (status: string): string => {
  const labels: Record<string, string> = {
    demonstrated_in_frozen_scope: "Demonstrated · frozen scope",
    falsified_in_current_scope: "Falsified · current scope",
    not_evaluated: "Not evaluated",
    mixed_scoped_results: "Mixed scoped results",
    scoped_negative_complete: "Scoped negative · complete",
    falsified_and_not_evaluated: "Falsified here · open-world not evaluated",
  };
  return labels[status] ?? status;
};

export const statusTone = (status: string): string => {
  if (status === "demonstrated_in_frozen_scope") return "status-pass";
  if (status === "falsified_in_current_scope" || status === "scoped_negative_complete") {
    return "status-reject";
  }
  if (status === "mixed_scoped_results") return "status-warn";
  return "status-neutral";
};

export const metricValue = (metric: Metric, digits = 2): string => {
  if (metric.unit === "boolean_rate") return metric.value === 1 ? "True" : "False";
  return metric.value.toFixed(digits);
};

export const fraction = (metric: Metric): string => {
  const fmt = (value: number) => (Number.isInteger(value) ? String(value) : String(value));
  return `${fmt(metric.numerator)}/${fmt(metric.denominator)}`;
};
