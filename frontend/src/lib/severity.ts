/** Severity is derived server-side (backend/src/app/pipeline/severity.py); this
 * mirrors only its presentation. Keep the order and the vocabulary in step with
 * that module — it is the single source of truth for what a finding *means*. */

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

/** Chart/legend colours. Chosen to stay distinguishable in greyscale print, since
 * the HTML report is meant to be printable. */
export const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "#b3261e",
  high: "#c05621",
  medium: "#8a6d1f",
  low: "#4a5568",
  info: "#64748b",
};

export const SEVERITY_HINT: Record<Severity, string> = {
  critical: "Confirmed against the live app — a single-use effect really did run twice",
  high: "Confirmed against the live app — a user really did reach what they should not",
  medium: "Proven satisfiable by Z3, but not yet confirmed against a running app",
  low: "Low impact",
  info: "Refuted — the solver or the live app showed the rule holds",
};

export function severityRank(severity: string): number {
  const index = SEVERITY_ORDER.indexOf(severity as Severity);
  return index === -1 ? SEVERITY_ORDER.length : index;
}

export function isSeverity(value: string): value is Severity {
  return (SEVERITY_ORDER as string[]).includes(value);
}
