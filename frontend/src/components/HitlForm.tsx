import { useState } from "react";
import { useResumeTriage } from "../api/client";
import type { ClarifyingQuestion, PmAnswer, TriageReport } from "../types/schemas";

export function HitlForm({
  questions,
  sessionId,
  onResolved,
  onRestart,
}: {
  questions: ClarifyingQuestion[];
  sessionId: string;
  onResolved: (report: TriageReport) => void;
  onRestart: () => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const mutation = useResumeTriage();

  const submit = (override: boolean) => {
    const pmAnswers: PmAnswer[] = questions.map((q) => ({
      question_id: q.question_id,
      answer: answers[q.question_id] ?? "",
    }));
    mutation.mutate(
      { sessionId, answers: override ? [] : pmAnswers, override },
      { onSuccess: onResolved },
    );
  };

  const errorStatus = (mutation.error as { status?: number } | null)?.status;
  if (errorStatus === 404) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm">
        <p className="font-medium text-amber-800">工作階段已過期</p>
        <p className="mt-1 text-amber-700">
          此審查工作階段已失效，請重新執行審查。
        </p>
        <button
          onClick={onRestart}
          className="mt-3 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          重新執行審查
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        流程已暫停——需要您的輸入才能繼續實作。
      </div>

      <ol className="space-y-4">
        {questions.map((q, i) => (
          <li key={q.question_id}>
            <label className="block text-sm font-medium text-slate-900">
              {i + 1}. {q.question}
            </label>
            {q.context && (
              <p className="mt-1 text-xs text-slate-500">{q.context}</p>
            )}
            <textarea
              className="mt-2 block w-full rounded-md border border-slate-300 p-2 text-sm"
              rows={2}
              value={answers[q.question_id] ?? ""}
              onChange={(e) =>
                setAnswers({ ...answers, [q.question_id]: e.target.value })
              }
            />
          </li>
        ))}
      </ol>

      {mutation.isError && errorStatus !== 404 && (
        <p className="text-sm text-rose-600">提交失敗，請重試。</p>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => submit(false)}
          disabled={mutation.isPending}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {mutation.isPending ? "提交中…" : "提交回答"}
        </button>
        <button
          onClick={() => submit(true)}
          disabled={mutation.isPending}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          覆寫（承擔風險）
        </button>
      </div>
    </div>
  );
}
