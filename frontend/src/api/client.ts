import { useMutation, useQuery } from "@tanstack/react-query";
import type {
  PmAnswer,
  PrdListItem,
  SessionStatus,
  TriageReport,
} from "../types/schemas";

async function asJson<T>(resPromise: Promise<Response>): Promise<T> {
  const res = await resPromise;
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`) as Error & {
      status: number;
    };
    err.status = res.status;
    throw err;
  }
  return (await res.json()) as T;
}

export function fetchPrds(): Promise<PrdListItem[]> {
  return asJson<PrdListItem[]>(fetch("/prds"));
}

export function startTriage(prdId: string): Promise<TriageReport> {
  return asJson<TriageReport>(
    fetch("/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prd_id: prdId }),
    }),
  );
}

export function resumeTriage(
  sessionId: string,
  answers: PmAnswer[],
  override = false,
): Promise<TriageReport> {
  return asJson<TriageReport>(
    fetch(`/triage/sessions/${sessionId}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers, override }),
    }),
  );
}

export function getSessionStatus(sessionId: string): Promise<SessionStatus> {
  return asJson<SessionStatus>(fetch(`/triage/sessions/${sessionId}`));
}

export async function downloadReport(report: TriageReport): Promise<void> {
  const res = await fetch("/render-report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${report.prd_id}-triage-report.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function usePrds() {
  return useQuery({ queryKey: ["prds"], queryFn: fetchPrds });
}

export function useStartTriage() {
  return useMutation({ mutationFn: (prdId: string) => startTriage(prdId) });
}

export function useResumeTriage() {
  return useMutation({
    mutationFn: ({
      sessionId,
      answers,
      override,
    }: {
      sessionId: string;
      answers: PmAnswer[];
      override?: boolean;
    }) => resumeTriage(sessionId, answers, override),
  });
}
