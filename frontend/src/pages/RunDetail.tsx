import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { getRun, type ProofResult, type RunStatus, type Verdict } from "@/lib/apiClient";
import { useRunEvents } from "@/lib/useRunEvents";

const STATUS_VARIANT: Record<RunStatus, "default" | "secondary" | "destructive"> = {
  pending: "secondary",
  running: "secondary",
  completed: "default",
  failed: "destructive",
};

const VERDICT_VARIANT: Record<Verdict, "default" | "secondary" | "destructive" | "outline"> = {
  sat: "default",
  unsat: "secondary",
  invalid: "outline",
  unsupported: "outline",
  unknown: "destructive",
};

const VERDICT_LABEL: Record<Verdict, string> = {
  sat: "SAT · violation path proven",
  unsat: "UNSAT · refuted",
  invalid: "invalid hypothesis",
  unsupported: "unsupported invariant kind",
  unknown: "solver gave up",
};

const STAGE_LABEL: Record<string, string> = {
  invariants: "extracting invariants…",
  hypotheses: "generating attack hypotheses…",
  solving: "proving with Z3…",
  refining: "refining hypotheses from counterexamples…",
};

function ProofTrace({ finding }: { finding: ProofResult }) {
  return (
    <div className="mt-2 space-y-1 text-xs">
      <div className="flex items-center gap-2">
        <Badge variant={VERDICT_VARIANT[finding.verdict]}>{VERDICT_LABEL[finding.verdict]}</Badge>
        <span className="text-muted-foreground">{finding.solve_time_ms.toFixed(1)} ms</span>
      </div>
      {finding.witness?.narrative.map((line) => (
        <p key={line} className="font-mono">
          {line}
        </p>
      ))}
      {finding.witness && (
        <p className="text-muted-foreground">
          witness:{" "}
          {Object.entries(finding.witness.actors)
            .map(([name, id]) => `${name}=${id}`)
            .join(", ")}
          {finding.witness.instances.map(
            (i) => `; ${i.id} (${i.resource}) owned by ${i.owner}`,
          )}
        </p>
      )}
      {finding.reason && <p className="text-muted-foreground">{finding.reason}</p>}
      {finding.unsat_core.length > 0 && (
        <p className="text-muted-foreground font-mono">core: {finding.unsat_core.join(", ")}</p>
      )}
      {finding.smtlib && (
        <details>
          <summary className="text-muted-foreground cursor-pointer">SMT-LIB</summary>
          <pre className="bg-muted mt-1 max-h-64 overflow-auto rounded p-2 font-mono">
            {finding.smtlib}
          </pre>
        </details>
      )}
    </div>
  );
}

const KIND_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  create: "default",
  read: "outline",
  update: "secondary",
  delete: "destructive",
  action: "outline",
};

export default function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const runId = Number(id);
  const queryClient = useQueryClient();

  const { data: run } = useQuery({
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

  if (!run) return <div className="p-8 text-muted-foreground">Loading…</div>;

  const model = run.application_model;
  const findingByIndex = new Map(run.findings.map((f) => [f.hypothesis_index, f]));

  return (
    <div className="mx-auto max-w-4xl p-8 space-y-4">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>
            Run #{run.id} — {run.target_name}
          </CardTitle>
          <div className="flex items-center gap-2">
            {run.status === "running" && currentStage && (
              <span className="text-muted-foreground text-xs">
                {STAGE_LABEL[currentStage] ?? currentStage}
              </span>
            )}
            <Badge variant={STATUS_VARIANT[run.status]}>{run.status}</Badge>
          </div>
        </CardHeader>
        {run.error && (
          <CardContent>
            <p className="text-destructive text-sm">{run.error}</p>
          </CardContent>
        )}
      </Card>

      {model && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{model.title}</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground flex gap-6 text-sm">
              <span>{Object.keys(model.resources).length} resources</span>
              <span>{model.endpoints.length} endpoints</span>
              <span>{model.transitions.length} transitions</span>
              <span>{run.invariants.length} invariants</span>
              <span>{run.hypotheses.length} hypotheses</span>
              <span>{run.findings.filter((f) => f.verdict === "sat").length} proven</span>
            </CardContent>
          </Card>

          {run.hypotheses.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Hypotheses</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {run.hypotheses.map((hyp, index) => (
                  <div key={index} className="rounded-md border p-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{hyp.resource}</span>
                      <span className="text-muted-foreground ml-auto text-xs">
                        {Math.round(hyp.confidence * 100)}% confidence
                      </span>
                    </div>
                    <p className="text-muted-foreground mt-1 text-xs italic">
                      targets: {hyp.target_invariant_statement}
                    </p>
                    <div className="mt-2 space-y-1">
                      {hyp.steps.map((step) => (
                        <div key={step.step} className="flex items-start gap-2 text-xs">
                          <Badge variant="outline" className="shrink-0">
                            {step.step}. {step.actor}
                          </Badge>
                          {step.race_group !== null && (
                            <Badge variant="secondary" className="shrink-0">
                              race {step.race_group}
                            </Badge>
                          )}
                          <span className="font-mono">{step.endpoint_key}</span>
                          <span className="text-muted-foreground">{step.description}</span>
                        </div>
                      ))}
                    </div>
                    <p className="mt-2 text-sm">{hyp.expected_violation}</p>
                    {findingByIndex.get(index) && (
                      <ProofTrace finding={findingByIndex.get(index)!} />
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {run.invariants.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Invariants</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {run.invariants.map((inv) => (
                  <div key={`${inv.resource}-${inv.statement}`} className="rounded-md border p-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{inv.resource}</span>
                      <Badge variant="outline">{inv.kind}</Badge>
                      <span className="text-muted-foreground ml-auto text-xs">
                        {Math.round(inv.confidence * 100)}% confidence
                      </span>
                    </div>
                    <p className="mt-1 text-sm">{inv.statement}</p>
                    <p className="text-muted-foreground mt-1 text-xs">{inv.rationale}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Resources</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {Object.values(model.resources)
                .sort((a, b) => b.endpoint_keys.length - a.endpoint_keys.length)
                .map((resource) => (
                  <div key={resource.name} className="rounded-md border p-3">
                    <div className="flex items-center gap-2">
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
                    {resource.ownership_evidence.length > 0 && (
                      <div className="text-muted-foreground mt-2 space-y-0.5 font-mono text-xs">
                        {resource.ownership_evidence.map((line) => (
                          <div key={line} className="truncate">
                            {line}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Transitions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {model.transitions.map((t) => (
                <div
                  key={t.endpoint_key}
                  className="flex items-center gap-2 font-mono text-xs"
                >
                  <Badge variant={KIND_VARIANT[t.kind]} className="w-16 justify-center">
                    {t.kind}
                  </Badge>
                  <span className="text-muted-foreground w-24 truncate">{t.resource}</span>
                  <span>{t.endpoint_key}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
