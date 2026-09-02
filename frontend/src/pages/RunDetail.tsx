import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { getRun, type RunStatus } from "@/lib/apiClient";
import { useRunEvents } from "@/lib/useRunEvents";

const STATUS_VARIANT: Record<RunStatus, "default" | "secondary" | "destructive"> = {
  pending: "secondary",
  running: "secondary",
  completed: "default",
  failed: "destructive",
};

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

  useEffect(() => {
    const last = events.at(-1);
    if (last?.status === "completed" || last?.status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["run", runId] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    }
  }, [events, runId, queryClient]);

  if (!run) return <div className="p-8 text-muted-foreground">Loading…</div>;

  const model = run.application_model;

  return (
    <div className="mx-auto max-w-4xl p-8 space-y-4">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle>
            Run #{run.id} — {run.target_name}
          </CardTitle>
          <Badge variant={STATUS_VARIANT[run.status]}>{run.status}</Badge>
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
            </CardContent>
          </Card>

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
