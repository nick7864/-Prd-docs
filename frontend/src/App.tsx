import { useState } from "react";
import { downloadReport, useStartTriage } from "./api/client";
import { HitlForm } from "./components/HitlForm";
import { PrdPicker } from "./components/PrdPicker";
import { TriageReportView } from "./components/TriageReportView";
import type { TriageReport } from "./types/schemas";

export default function App() {
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<TriageReport | null>(null);
  const triageMutation = useStartTriage();

  const runTriage = () => {
    if (!selected) return;
    triageMutation.mutate(selected, { onSuccess: setReport });
  };

  const reset = () => {
    setReport(null);
    triageMutation.reset();
  };

  const isAwaiting = report?.status === "awaiting_pm" && report.session_id;
  const isFinal =
    report && (report.status === "completed" || report.status === "terminated");

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-5xl px-6 py-4">
          <h1 className="text-lg font-semibold text-slate-900">
            PRD 審查代理人
          </h1>
          <p className="text-sm text-slate-500">多代理人需求文件審查</p>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="grid gap-8 md:grid-cols-[280px_1fr]">
          <aside>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              需求文件
            </h2>
            <PrdPicker selected={selected} onSelect={setSelected} />
          </aside>

          <section>
            {!selected && !report && (
              <p className="text-sm text-slate-400">選擇一份需求文件開始。</p>
            )}

            {selected && !report && (
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={runTriage}
                  disabled={triageMutation.isPending}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {triageMutation.isPending ? "分析中…" : "執行審查"}
                </button>
                {triageMutation.isPending && (
                  <span className="text-sm text-slate-400">
                    審查流程約需 10–30 秒。
                  </span>
                )}
                {triageMutation.isError && (
                  <span className="text-sm text-rose-600">
                    審查失敗——後端伺服器是否運行中？
                  </span>
                )}
              </div>
            )}

            {isAwaiting && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-900">
                    需要釐清
                  </h2>
                  <button
                    onClick={reset}
                    className="text-sm text-slate-500 hover:text-slate-700"
                  >
                    重新開始
                  </button>
                </div>
                <HitlForm
                  questions={report.clarifying_questions}
                  sessionId={report.session_id!}
                  onResolved={setReport}
                  onRestart={reset}
                />
              </div>
            )}

            {isFinal && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-900">
                    審查報告
                  </h2>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => downloadReport(report)}
                      className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      下載報告 (Markdown)
                    </button>
                    <button
                      onClick={reset}
                      className="text-sm text-slate-500 hover:text-slate-700"
                    >
                      新一輪審查
                    </button>
                  </div>
                </div>
                <TriageReportView report={report} />
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
