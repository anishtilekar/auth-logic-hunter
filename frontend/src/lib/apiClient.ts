const BASE_URL = "/api";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export function runEventsUrl(runId: number): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${BASE_URL}/runs/${runId}/events`;
}

export type RunStatus = "pending" | "running" | "completed" | "failed";

export interface RunSummary {
  id: number;
  target_name: string;
  status: RunStatus;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Endpoint {
  path: string;
  method: string;
  operation_id: string | null;
  summary: string | null;
  path_params: string[];
  resource: string | null;
}

export interface StateTransition {
  resource: string;
  kind: "create" | "read" | "update" | "delete" | "action";
  endpoint_key: string;
}

export interface Resource {
  name: string;
  id_params: string[];
  endpoint_keys: string[];
  ownership_evidence: string[];
}

export interface ApplicationModel {
  title: string;
  base_url: string;
  resources: Record<string, Resource>;
  endpoints: Endpoint[];
  transitions: StateTransition[];
}

export interface SecurityInvariant {
  resource: string;
  endpoint_keys: string[];
  kind: "ownership" | "role_required" | "state_precondition";
  statement: string;
  rationale: string;
  confidence: number;
}

export interface RequestStep {
  step: number;
  actor: string;
  endpoint_key: string;
  description: string;
  captures: string | null;
  uses: Record<string, string>;
}

export interface Hypothesis {
  resource: string;
  target_invariant_statement: string;
  preconditions: string[];
  steps: RequestStep[];
  expected_violation: string;
  confidence: number;
}

export type Verdict = "sat" | "unsat" | "invalid" | "unsupported" | "unknown";

export interface InstanceWitness {
  id: string;
  resource: string;
  created_at_step: number;
  owner: string;
}

export interface Witness {
  actors: Record<string, number>;
  instances: InstanceWitness[];
  violating_steps: number[];
  narrative: string[];
}

export interface ProofResult {
  hypothesis_index: number;
  invariant_statement: string | null;
  verdict: Verdict;
  reason: string | null;
  unsat_core: string[];
  witness: Witness | null;
  smtlib: string | null;
  solve_time_ms: number;
}

export interface RunDetail extends RunSummary {
  application_model: ApplicationModel | null;
  invariants: SecurityInvariant[];
  hypotheses: Hypothesis[];
  findings: ProofResult[];
}

export const listRuns = () => apiGet<RunSummary[]>("/runs");
export const getRun = (id: number) => apiGet<RunDetail>(`/runs/${id}`);
export const createRun = (target_name: string) =>
  apiPost<RunSummary>("/runs", { target_name });
