import type { Finding, Severity } from "../types/schemas";

const SEV_DOT: Record<Severity, string> = {
  low: "bg-slate-400",
  medium: "bg-amber-500",
  high: "bg-orange-500",
  critical: "bg-rose-600",
};

const SEV_LABEL: Record<Severity, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "嚴重",
};

export function RiskRegister({ findings }: { findings: Finding[] }) {
  if (!findings.length) return null;
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs text-slate-500">
          <tr>
            <th className="px-4 py-2 font-medium">嚴重度</th>
            <th className="px-4 py-2 font-medium">發現</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {findings.map((f, i) => (
            <tr key={i}>
              <td className="px-4 py-2">
                <span className="inline-flex items-center gap-2 text-slate-600">
                  <span className={`h-2 w-2 rounded-full ${SEV_DOT[f.severity]}`} />
                  {SEV_LABEL[f.severity]}
                </span>
              </td>
              <td className="px-4 py-2 text-slate-700">{f.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
