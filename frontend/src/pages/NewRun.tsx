import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createRun } from "@/lib/apiClient";

export default function NewRun() {
  const [targetName, setTargetName] = useState("crapi");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => createRun(targetName),
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
      await navigate(`/runs/${run.id}`);
    },
  });

  return (
    <div className="mx-auto max-w-md p-8">
      <Card>
        <CardHeader>
          <CardTitle>New Run</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <label htmlFor="target" className="text-sm font-medium">
              Target
            </label>
            <Input
              id="target"
              value={targetName}
              onChange={(e) => setTargetName(e.target.value)}
              placeholder="crapi"
            />
            <p className="text-muted-foreground text-xs">
              Name of a vendored target under /targets
            </p>
          </div>
          {mutation.isError && (
            <p className="text-destructive text-sm">{mutation.error.message}</p>
          )}
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !targetName}
          >
            {mutation.isPending ? "Starting…" : "Start Run"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
