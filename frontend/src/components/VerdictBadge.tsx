import type { Verdict } from "../types/schemas";

const STYLES: Record<Verdict, string> = {
  pass: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  needs_clarification: "bg-amber-50 text-amber-700 ring-amber-200",
  reject: "bg-rose-50 text-rose-700 ring-rose-200",
};

const LABELS: Record<Verdict, string> = {
  pass: "通過",
  needs_clarification: "需釐清",
  reject: "駁回",
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[verdict]}`}
    >
      {LABELS[verdict]}
    </span>
  );
}
