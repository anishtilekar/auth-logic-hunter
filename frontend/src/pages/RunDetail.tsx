import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router";
import { EmptyState, ErrorState, Layout, Skeleton } from "@/components/Layout";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getRun,
  runReportUrl,
  type Hypothesis,
  type ProofResult,
  type ReplayOutcome,
  type ReplayResult,
  type RunStatus,
  type Verdict,
} from "@/lib/apiClient";
import { severityRank } from "@/lib/severity";
import { useRunEvents } from "@/lib/useRunEvents";

const STATUS_VARIANT: Record<RunStatus, "default" | "secondary" | "destructive"> = {
  pending: "secondary",
  running: "secondary",
  completed: "default",
  failed: "destructive",
};

const VERDICT_LABEL: Record<Verdict, string> = {
  sat: "Z3: violation path proven",
  unsat: "Z3: refuted — no execution violates the invariant",
  invalid: "invalid hypothesis",
  unsupported: "unsupported invariant kind",
  unknown: "solver gave up",
};

const REPLAY_LABEL: Record<ReplayOutcome, string> = {
  confirmed: "Confirmed against the live app",
  refuted: "App enforced the rule",
  inconclusive: "Inconclusive",
  error: "Replay error",
};

/** The pipeline's stages, in the order the backend publishes them. `refining` only
 * appears when the counterexample loop actually runs another round. */
const STAGES = [
  { key: "invariants", label: "Invariants" },
  { key: "hypotheses", label: "Hypotheses" },
  { key: "solving", label: "Proving" },
  { key: "replaying", label: "Replaying" },
] as const;

function StageProgress({ current, status }: { current?: string; status: RunStatus }) {
  const done = status === "completed";
  const activeIndex = STAGES.findIndex((s) => s.key === current);
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      {STAGES.map((stage, i) => {
        const state = done || (activeIndex > i && activeIndex !== -1) ? "done" : "pending";
        const active = !done && i === activeIndex;
        return (
          <span key={stage.key} className="flex items-center gap-2">
            {i > 0 && <span className="text-muted-foreground/40">›</span>}
            <span
              className={
                active
                  ? "font-medium"
                  : state === "done"
                    ? "text-muted-foreground"
                    : "text-muted-foreground/50"
              }
            >
              {active && (
                <span className="bg-foreground mr-1.5 inline-block size-1.5 animate-pulse rounded-full align-middle" />
              )}
              {stage.label}
            </span>
          </span>
        );
      })}
      {current === "refining" && (
        <span className="text-muted-foreground">· refining from counterexamples</span>
      )}
    </div>
  );
}

function ReplayTrace({ replay }: { replay: ReplayResult }) {
  return (
    <div className="mt-3 space-y-1.5 border-t pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium">{REPLAY_LABEL[replay.outcome]}</span>
        <span className="text-muted-foreground font-mono text-[11px]">{replay.base_url}</span>
      </div>
      <p className="text-muted-foreground text-xs">{replay.reason}</p>
      <div className="space-y-0.5 font-mono text-[11px]">
        {replay.steps.map((s) => {
          const succeeded = s.status !== null && s.status < 400;
          const violating = replay.violating_steps.includes(s.step);
          return (
            <div key={s.step} className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground w-4 shrink-0 text-right">{s.step}.</span>
              <span className="text-muted-foreground">{s.method}</span>
              <span className="min-w-0 truncate">{s.url}</span>
              <span
                className={
                  violating && succeeded
                    ? "text-destructive font-semibold"
                    : "text-muted-foreground"
                }
              >
                {s.error ?? s.status}
              </span>
              {s.started_offset_ms !== null && (
                <span className="text-muted-foreground" title="offset from the concurrent release">
                  +{s.started_offset_ms.toFixed(2)}ms
                </span>
              )}
            </div>
          );
        })}
      </div>
      {replay.enforced_endpoints.length > 0 && (
        <p className="text-muted-foreground text-xs">
          Enforced, fed back into later rounds: {replay.enforced_endpoints.join(", ")}
        </p>
      )}
    </div>
  );
}

function Finding({ finding, hypothesis }: { finding: ProofResult; hypothesis?: Hypothesis }) {
  const violating = new Set(finding.witness?.violating_steps ?? []);
  return (
    <div className="rounded-lg border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <span className="font-medium">{hypothesis?.resource ?? "—"}</span>
        {finding.invariant_kind && <Badge variant="outline">{finding.invariant_kind}</Badge>}
        <span className="text-muted-foreground ml-auto text-xs tabular-nums">
          {finding.solve_time_ms.toFixed(1)} ms
        </span>
      </div>

      {finding.invariant_statement && (
        <p className="mt-2 text-sm">
          <span className="text-muted-foreground">Invariant: </span>
          {finding.invariant_statement}
        </p>
      )}

      {hypothesis && (
        <ol className="mt-3 space-y-1">
          {hypothesis.steps.map((step) => (
            <li key={step.step} className="flex flex-wrap items-center gap-2 text-xs">
              <Badge
                variant={violating.has(step.step) ? "destructive" : "outline"}
                className="shrink-0"
              >
                {step.step}. {step.actor}
              </Badge>
              {step.race_group !== null && (
                <Badge variant="secondary" className="shrink-0">
                  race {step.race_group}
                </Badge>
              )}
              <span className="font-mono break-all">{step.endpoint_key}</span>
              <span className="text-muted-foreground">{step.description}</span>
            </li>
          ))}
        </ol>
      )}

      <div className="mt-3 space-y-1 border-t pt-3">
        <p className="text-xs font-medium">{VERDICT_LABEL[finding.verdict]}</p>
        {finding.witness?.narrative.map((line) => (
          <p key={line} className="font-mono text-[11px]">
            {line}
          </p>
        ))}
        {/* The narrative already spells out a race's interleaving; only fall back
            to the raw event order when it doesn't. */}
        {finding.witness &&
          finding.witness.order.length > 0 &&
          !finding.witness.narrative.some((l) => l.toLowerCase().includes("interleaving")) && (
            <p className="text-muted-foreground font-mono text-[11px]">
              interleaving: {finding.witness.order.join(" < ")}
            </p>
          )}
        {finding.reason && <p className="text-muted-foreground text-xs">{finding.reason}</p>}
        {finding.unsat_core.length > 0 && (
          <p className="text-muted-foreground font-mono text-[11px]">
            unsat core: {finding.unsat_core.join(", ")}
          </p>
        )}
      </div>

      {finding.replay && <ReplayTrace replay={finding.replay} />}

      {finding.smtlib && (
        <details className="mt-3">
          <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-xs">
            SMT-LIB problem
          </summary>
          <pre className="bg-muted mt-2 max-h-72 overflow-auto rounded p-3 font-mono text-[11px]">
            {finding.smtlib}
          </pre>
        </details>
      )}
    </div>
  );
}

function Collapsible({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <Card>
      <details>
        <summary className="cursor-pointer list-none px-6 py-4">
          <span className="font-semibold">{title}</span>
          <span className="text-muted-foreground ml-2 text-sm tabular-nums">{count}</span>
        </summary>
        <CardContent>{children}</CardContent>
      </details>
    </Card>
  );
}

export default function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const runId = Number(id);
  const queryClient = useQueryClient();

  const {
    data: run,
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
    refetchInterval: (query) =>
      query.state.data?.status === "pending" || query.state.data?.status === "running"
        ? 1000
        : false,
  });

  const events = useRunEvents(runId);
  const currentStage = [...events].reverse().find((e) => e.type === "stage")?.stage;

  useEffect(() => {
    const last = events.at(-1);
    if (last?.status === "completed" || last?.status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["run", runId] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    }
  }, [events, runId, queryClient]);

  if (error) {
    return (
      <Layout>
        <ErrorState error={error} onRetry={() => void refetch()} />
      </Layout>
    );
  }

  if (isPending || !run) {
    return (
      <Layout>
        <div className="space-y-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-64" />
        </div>
      </Layout>
    );
  }

  const model = run.application_model;
  const running = run.status === "pending" || run.status === "running";
  const findings = [...run.findings].sort(
    (a, b) => severityRank(a.severity) - severityRank(b.severity),
  );
  const confirmed = findings.filter((f) => f.replay?.outcome === "confirmed").length;

  return (
    <Layout>
      <div className="space-y-4">
        <Card>
          <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <CardTitle className="truncate">
                Run #{run.id} — {run.target_name}
              </CardTitle>
              {running ? (
                <div className="mt-2">
                  <StageProgress current={currentStage} status={run.status} />
                </div>
              ) : (
                model && (
                  <p className="text-muted-foreground mt-1 text-sm">
                    {Object.keys(model.resources).length} resources · {model.endpoints.length}{" "}
                    endpoints · {run.invariants.length} invariants · {run.hypotheses.length}{" "}
                    hypotheses
                  </p>
                )
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {run.status === "completed" && (
                <Button asChild size="sm" variant="outline">
                  <a href={runReportUrl(run.id)} target="_blank" rel="noreferrer">
                    Report
                  </a>
                </Button>
              )}
              <Badge variant={STATUS_VARIANT[run.status]}>{run.status}</Badge>
            </div>
          </CardHeader>
          {run.error && (
            <CardContent>
              <p className="text-destructive text-sm break-words">{run.error}</p>
            </CardContent>
          )}
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Findings</CardTitle>
            {findings.length > 0 && (
              <span className="text-muted-foreground text-xs">
                {confirmed} confirmed against the live app
              </span>
            )}
          </CardHeader>
          <CardContent className="space-y-3">
            {findings.length === 0 ? (
              running ? (
                <div className="space-y-2">
                  <Skeleton className="h-20" />
                  <Skeleton className="h-20" />
                </div>
              ) : (
                <EmptyState
                  title="No findings"
                  hint="Nothing in this run produced a decidable proof. The hypotheses and invariants below show what was considered."
                />
              )
            ) : (
              findings.map((finding) => (
                <Finding
                  key={finding.hypothesis_index}
                  finding={finding}
                  hypothesis={run.hypotheses[finding.hypothesis_index]}
                />
              ))
            )}
          </CardContent>
        </Card>

        {run.invariants.length > 0 && (
          <Collapsible title="Invariants" count={run.invariants.length}>
            <div className="space-y-3">
              {run.invariants.map((inv) => (
                <div key={`${inv.resource}-${inv.statement}`} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{inv.resource}</span>
                    <Badge variant="outline">{inv.kind}</Badge>
                    {inv.kind === "single_use" && (
                      <Badge variant="secondary">limit {inv.limit}</Badge>
                    )}
                    <span className="text-muted-foreground ml-auto text-xs">
                      {Math.round(inv.confidence * 100)}% confidence
                    </span>
                  </div>
                  <p className="mt-1 text-sm">{inv.statement}</p>
                  <p className="text-muted-foreground mt-1 text-xs">{inv.rationale}</p>
                </div>
              ))}
            </div>
          </Collapsible>
        )}

        {model && (
          <Collapsible title="Application model" count={Object.keys(model.resources).length}>
            <div className="space-y-3">
              {Object.values(model.resources)
                .sort((a, b) => b.endpoint_keys.length - a.endpoint_keys.length)
                .map((resource) => (
                  <div key={resource.name} className="rounded-md border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{resource.name}</span>
                      {resource.id_params.map((p) => (
                        <Badge key={p} variant="outline">
                          {p}
                        </Badge>
                      ))}
                      <span className="text-muted-foreground ml-auto text-xs">
                        {resource.endpoint_keys.length} endpoint
                        {resource.endpoint_keys.length === 1 ? "" : "s"}
                      </span>
                    </div>
                    {resource.race_evidence.length > 0 && (
                      <div className="mt-2 space-y-0.5 font-mono text-[11px]">
                        <span className="text-muted-foreground">check-then-act evidence</span>
                        {resource.race_evidence.map((line) => (
                          <div key={line} className="break-all">
                            {line}
                          </div>
                        ))}
                      </div>
                    )}
                    {resource.ownership_evidence.length > 0 && (
                      <div className="text-muted-foreground mt-2 space-y-0.5 font-mono text-[11px]">
                        {resource.ownership_evidence.slice(0, 4).map((line) => (
                          <div key={line} className="truncate">
                            {line}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
            </div>
          </Collapsible>
        )}
      </div>
    </Layout>
  );
}
