import { usePrds } from "../api/client";

export function PrdPicker({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { data: prds, isLoading, error } = usePrds();

  if (isLoading) {
    return <p className="text-sm text-slate-500">載入需求文件中…</p>;
  }
  if (error) {
    return <p className="text-sm text-rose-600">無法載入需求文件。</p>;
  }

  return (
    <ul className="space-y-1">
      {prds?.map((p) => (
        <li key={p.id}>
          <button
            onClick={() => onSelect(p.id)}
            className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
              selected === p.id
                ? "border-indigo-600 bg-indigo-50"
                : "border-slate-200 hover:border-slate-300"
            }`}
          >
            <span className="font-mono text-xs text-slate-500">{p.id}</span>
            <span className="ml-2 text-slate-800">{p.title}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
