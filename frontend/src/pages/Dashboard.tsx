import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { apiGet } from "@/lib/apiClient";

interface HealthResponse {
  status: string;
}

export default function Dashboard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: () => apiGet<HealthResponse>("/health"),
  });

  return (
    <div className="mx-auto max-w-2xl p-8">
      <Card>
        <CardHeader>
          <CardTitle>Auth-Logic Hunter</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-2">
          <span className="text-muted-foreground">Backend status:</span>
          {isLoading && <Badge variant="secondary">checking…</Badge>}
          {isError && <Badge variant="destructive">unreachable</Badge>}
          {data && <Badge>{data.status}</Badge>}
        </CardContent>
      </Card>
    </div>
  );
}
