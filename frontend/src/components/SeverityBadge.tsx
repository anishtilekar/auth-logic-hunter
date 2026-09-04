import { SEVERITY_COLOR, SEVERITY_HINT, isSeverity } from "@/lib/severity";

/** Solid-colour pill: severity is the one thing a reader scans for, so it does not
 * share the muted palette the rest of the badges use. */
export function SeverityBadge({ severity }: { severity: string }) {
  const known = isSeverity(severity);
  return (
    <span
      title={known ? SEVERITY_HINT[severity] : undefined}
      className="inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide text-white uppercase"
      style={{ backgroundColor: known ? SEVERITY_COLOR[severity] : "#64748b" }}
    >
      {severity}
    </span>
  );
}
