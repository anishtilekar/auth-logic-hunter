import { useEffect, useRef, useState } from "react";
import { runEventsUrl, type RunStatus } from "@/lib/apiClient";

export interface RunEvent {
  type: string;
  status?: RunStatus;
  stage?: string;
  round?: number;
  error?: string | null;
  summary?: {
    resources: number;
    endpoints: number;
    transitions: number;
    invariants: number;
    hypotheses: number;
    findings: number;
    proven: number;
  };
}

export function useRunEvents(runId: number | undefined) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (runId === undefined) return;
    // Reset the log when switching to a different run — same pattern React's
    // own docs use for resetting state on a changed effect dependency.
    // oxlint-disable-next-line react/set-state-in-effect
    setEvents([]);

    const ws = new WebSocket(runEventsUrl(runId));
    socketRef.current = ws;
    ws.onmessage = (e) => {
      const event = JSON.parse(e.data) as RunEvent;
      setEvents((prev) => [...prev, event]);
    };

    return () => ws.close();
  }, [runId]);

  return events;
}
