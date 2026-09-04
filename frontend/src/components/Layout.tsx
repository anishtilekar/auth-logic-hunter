import type { ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { Button } from "@/components/ui/button";

export function Layout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <div className="bg-background min-h-screen">
      <header className="bg-background/85 sticky top-0 z-10 border-b backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-baseline gap-2">
            <span className="font-semibold tracking-tight">Auth-Logic Hunter</span>
            <span className="text-muted-foreground hidden text-xs sm:inline">
              proven auth-logic findings
            </span>
          </Link>
          <div className="ml-auto flex items-center gap-2">
            {pathname !== "/" && (
              <Button asChild variant="ghost" size="sm">
                <Link to="/">Runs</Link>
              </Button>
            )}
            <Button asChild size="sm">
              <Link to="/runs/new">New run</Link>
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}

/** Consistent placeholder for the three states every async view needs. Having one
 * component for it is what stops "loading" silently rendering as an empty page. */
export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {hint && <p className="text-muted-foreground max-w-sm text-sm">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="border-destructive/40 bg-destructive/5 flex flex-col items-start gap-2 rounded-lg border px-4 py-3">
      <p className="text-destructive text-sm font-medium">Could not load this data</p>
      <p className="text-muted-foreground font-mono text-xs break-all">{error.message}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`bg-muted animate-pulse rounded ${className}`} />;
}
