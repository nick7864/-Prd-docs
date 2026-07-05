import type { TriageReport } from "../types/schemas";
import { AuditTrail } from "./AuditTrail";
import { RiskRegister } from "./RiskRegister";
import { SpecialistCard } from "./SpecialistCard";
import { VerdictBadge } from "./VerdictBadge";

export function TriageReportView({ report }: { report: TriageReport }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <VerdictBadge verdict={report.verdict} />
        {report.hitl_overridden && (
          <span className="text-xs text-slate-400">由 PM 覆寫</span>
        )}
      </div>

      {report.policy_decision && !report.policy_decision.allowed && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <p className="font-medium">政策閘門已駁回</p>
          <ul className="mt-1 list-disc pl-5">
            {report.policy_decision.violations.map((v, i) => (
              <li key={i}>
                {v.type}: {v.pattern}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {report.completeness && (
          <SpecialistCard title="完整性">
            <p>
              分數：
              <span className="font-medium text-slate-900">
                {report.completeness.completeness_score}
              </span>
              /100
            </p>
            {report.completeness.missing_sections.length > 0 && (
              <ul className="list-disc pl-5">
                {report.completeness.missing_sections.map((m, i) => (
                  <li key={i}>
                    {m.section}（{m.severity}）
                  </li>
                ))}
              </ul>
            )}
          </SpecialistCard>
        )}

        {report.clarity && (
          <SpecialistCard title="清晰度">
            {report.clarity.ambiguous_items.length === 0 ? (
              <p>無模糊詞彙。</p>
            ) : (
              <ul className="list-disc pl-5">
                {report.clarity.ambiguous_items.map((a, i) => (
                  <li key={i}>
                    {a.phrase} — {a.generated_question}
                  </li>
                ))}
              </ul>
            )}
          </SpecialistCard>
        )}

        {report.architecture && (
          <SpecialistCard title="架構契合度">
            {report.architecture.conflicts.length === 0 &&
              report.architecture.integration_points.length === 0 && (
                <p>未偵測到衝突。</p>
              )}
            {report.architecture.conflicts.length > 0 && (
              <p className="font-medium text-slate-900">衝突</p>
            )}
            {report.architecture.conflicts.map((c, i) => (
              <p key={i}>{c.description}</p>
            ))}
            {report.architecture.integration_points.length > 0 && (
              <p className="font-medium text-slate-900">整合點</p>
            )}
            {report.architecture.integration_points.map((p, i) => (
              <p key={i}>{p.description}</p>
            ))}
          </SpecialistCard>
        )}

        {report.risk && (
          <SpecialistCard title="風險與合規">
            {report.risk.findings.length === 0 ? (
              <p>未識別出風險。</p>
            ) : (
              <RiskRegister findings={report.risk.findings} />
            )}
          </SpecialistCard>
        )}
      </div>

      {report.failed_agents.length > 0 && (
        <div className="rounded-lg border border-slate-200 p-4 text-sm">
          <p className="font-medium text-slate-900">失敗的代理人</p>
          {report.failed_agents.map((f, i) => (
            <p key={i} className="text-slate-600">
              {f.agent_name}: {f.error}
            </p>
          ))}
        </div>
      )}

      {report.clarifying_questions.length > 0 && report.status === "completed" && (
        <div className="rounded-lg border border-slate-200 p-4 text-sm">
          <p className="font-medium text-slate-900">待釐清問題</p>
          <ul className="mt-1 list-disc pl-5 text-slate-600">
            {report.clarifying_questions.map((q, i) => (
              <li key={i}>{q.question}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="mb-3 text-sm font-semibold text-slate-900">審計軌跡</h3>
        <AuditTrail entries={report.audit_trail} />
      </div>
    </div>
  );
}
