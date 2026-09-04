import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState, ErrorState, Layout, Skeleton } from "@/components/Layout";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listRuns, type RunStatus, type RunSummary } from "@/lib/apiClient";
import { SEVERITY_COLOR, SEVERITY_ORDER, type Severity } from "@/lib/severity";

const STATUS_VARIANT: Record<RunStatus, "default" | "secondary" | "destructive"> = {
  pending: "secondary",
  running: "secondary",
  completed: "default",
  failed: "destructive",
};

function totalsBySeverity(runs: RunSummary[]) {
  return SEVERITY_ORDER.map((severity) => ({
    severity,
    count: runs.reduce((sum, run) => sum + (run.severity_counts[severity] ?? 0), 0),
  }));
}

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-lg border px-4 py-3">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-muted-foreground text-xs">{label}</div>
      {hint && <div className="text-muted-foreground mt-0.5 text-[11px]">{hint}</div>}
    </div>
  );
}

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function Dashboard() {
  const {
    data: runs,
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ["runs"],
    queryFn: listRuns,
    // Keep the list live while a run is in flight, without hammering when idle.
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "pending" || r.status === "running") ? 2000 : false,
  });

  const totals = runs ? totalsBySeverity(runs) : [];
  const findings = totals.reduce((sum, t) => sum + t.count, 0);
  const confirmed = totals
    .filter((t) => t.severity === "critical" || t.severity === "high")
    .reduce((sum, t) => sum + t.count, 0);
  const charted = totals.filter((t) => t.count > 0);

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-lg font-semibold">Runs</h1>
          <p className="text-muted-foreground text-sm">
            Every finding here is decided by Z3, and confirmed or refuted against the live app.
          </p>
        </div>

        {error && <ErrorState error={error} onRetry={() => void refetch()} />}

        {isPending && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-[74px]" />
            ))}
          </div>
        )}

        {runs && runs.length > 0 && (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Runs" value={runs.length} />
              <Stat label="Findings" value={findings} />
              <Stat
                label="Confirmed exploitable"
                value={confirmed}
                hint="reproduced against the running target"
              />
              <Stat
                label="Refuted"
                value={totals.find((t) => t.severity === "info")?.count ?? 0}
                hint="checked and shown to hold"
              />
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Severity breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                {charted.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    No findings yet across these runs.
                  </p>
                ) : (
                  <div className="h-52 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={charted} margin={{ top: 4, right: 8, bottom: 4, left: -20 }}>
                        <XAxis
                          dataKey="severity"
                          tickLine={false}
                          axisLine={false}
                          fontSize={12}
                          stroke="currentColor"
                          className="text-muted-foreground"
                        />
                        <YAxis
                          allowDecimals={false}
                          tickLine={false}
                          axisLine={false}
                          fontSize={12}
                          stroke="currentColor"
                          className="text-muted-foreground"
                        />
                        <Tooltip
                          cursor={{ fillOpacity: 0.08 }}
                          contentStyle={{
                            borderRadius: 8,
                            border: "1px solid var(--border)",
                            background: "var(--background)",
                            fontSize: 12,
                          }}
                        />
                        <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={64}>
                          {charted.map((entry) => (
                            <Cell
                              key={entry.severity}
                              fill={SEVERITY_COLOR[entry.severity as Severity]}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}

        {runs && runs.length === 0 && (
          <EmptyState
            title="No runs yet"
            hint="Point a run at a target under /targets — crapi, or seeded-race for the race-condition demo."
            action={
              <Button asChild size="sm" className="mt-1">
                <Link to="/runs/new">Start the first run</Link>
              </Button>
            }
          />
        )}

        {runs && runs.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>History</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {runs.map((run) => {
                const counts = SEVERITY_ORDER.filter((s) => (run.severity_counts[s] ?? 0) > 0);
                return (
                  <Link
                    key={run.id}
                    to={`/runs/${run.id}`}
                    className="hover:bg-accent flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border px-3 py-2 transition-colors"
                  >
                    <span className="font-medium tabular-nums">#{run.id}</span>
                    <span className="text-muted-foreground truncate">{run.target_name}</span>
                    <div className="flex flex-wrap items-center gap-1">
                      {counts.map((severity) => (
                        <span key={severity} className="flex items-center gap-1">
                          <SeverityBadge severity={severity} />
                          <span className="text-muted-foreground text-xs tabular-nums">
                            {run.severity_counts[severity]}
                          </span>
                        </span>
                      ))}
                    </div>
                    <span className="text-muted-foreground ml-auto text-xs">
                      {relativeTime(run.created_at)}
                    </span>
                    <Badge variant={STATUS_VARIANT[run.status]}>{run.status}</Badge>
                  </Link>
                );
              })}
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
