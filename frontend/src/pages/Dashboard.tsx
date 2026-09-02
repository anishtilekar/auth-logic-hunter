import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { listRuns, type RunStatus } from "@/lib/apiClient";

const STATUS_VARIANT: Record<RunStatus, "default" | "secondary" | "destructive"> = {
  pending: "secondary",
  running: "secondary",
  completed: "default",
  failed: "destructive",
};

export default function Dashboard() {
  const { data: runs, isLoading } = useQuery({ queryKey: ["runs"], queryFn: listRuns });

  return (
    <div className="mx-auto max-w-3xl p-8 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Auth-Logic Hunter</h1>
        <Button asChild>
          <Link to="/runs/new">New Run</Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Runs</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
          {runs?.length === 0 && (
            <p className="text-muted-foreground text-sm">No runs yet.</p>
          )}
          {runs?.map((run) => (
            <Link
              key={run.id}
              to={`/runs/${run.id}`}
              className="flex items-center justify-between rounded-md border px-3 py-2 hover:bg-accent"
            >
              <div>
                <span className="font-medium">#{run.id}</span>{" "}
                <span className="text-muted-foreground">{run.target_name}</span>
              </div>
              <Badge variant={STATUS_VARIANT[run.status]}>{run.status}</Badge>
            </Link>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
