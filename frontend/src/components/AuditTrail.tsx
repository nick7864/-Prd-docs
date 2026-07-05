import type { AuditEntry, AuditStageStatus } from "../types/schemas";

const STATUS_DOT: Record<AuditStageStatus, string> = {
  running: "bg-blue-500",
  completed: "bg-emerald-500",
  failed: "bg-rose-500",
  skipped: "bg-slate-300",
};

const STATUS_LABEL: Record<AuditStageStatus, string> = {
  running: "進行中",
  completed: "完成",
  failed: "失敗",
  skipped: "略過",
};

const STAGE_LABEL: Record<string, string> = {
  intake: "審查入口",
  policy: "政策閘門",
  specialists: "專家分析",
  synthesis: "綜合統整",
};

export function AuditTrail({ entries }: { entries: AuditEntry[] }) {
  if (!entries.length) return null;
  return (
    <ol className="space-y-3">
      {entries.map((e, i) => (
        <li key={i} className="flex gap-3 text-sm">
          <span
            className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[e.status]}`}
          />
          <div>
            <p className="font-medium text-slate-900">
              {STAGE_LABEL[e.stage] ?? e.stage}
              {e.agent_name ? ` · ${e.agent_name}` : ""}
              <span className="ml-2 text-xs font-normal text-slate-400">
                {STATUS_LABEL[e.status]}
              </span>
            </p>
            {e.error && <p className="text-slate-500">{e.error}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
