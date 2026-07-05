# PRD Triage Agent — Design System

A focused internal tool for triaging PRDs. Aesthetic: calm, information-dense,
dev-tool grade (Linear / Notion register). No decorative imagery; the data is
the interface.

## Tokens

All values use the Tailwind v4 default palette — no custom theme config needed.

### Color — verdict (the central signal)

| Verdict | Token | Usage |
|---|---|---|
| `pass` | `emerald-600` text / `emerald-50` bg / `emerald-200` ring | PRD is ready to build |
| `needs_clarification` | `amber-600` text / `amber-50` bg / `amber-200` ring | PM input required |
| `reject` | `rose-600` text / `rose-50` bg / `rose-200` ring | Policy gate blocked |

### Color — severity (risk register, findings)

| Severity | Token |
|---|---|
| `low` | `slate-500` |
| `medium` | `amber-500` |
| `high` | `orange-500` |
| `critical` | `rose-600` |

### Color — surfaces & text

| Role | Token |
|---|---|
| App background | `slate-50` |
| Card surface | `white` with `border-slate-200` |
| Heading text | `slate-900` |
| Body text | `slate-600` |
| Muted text | `slate-400` |
| Primary action | `indigo-600` (hover `indigo-700`) |
| Destructive action | `rose-600` |

### Typography

System UI stack (`font-sans`). Scale: page title `text-2xl font-semibold`,
section heading `text-lg font-semibold`, body `text-sm`, muted `text-xs`.

### Spacing / shape / depth

- Card: `rounded-lg border border-slate-200 p-5`
- Badge: `rounded-full px-2.5 py-0.5 text-xs font-medium`
- Buttons: `rounded-md px-4 py-2 text-sm font-medium`
- Depth: `shadow-sm` only (no heavy elevation)

## Components

- **VerdictBadge** — pill colored by verdict, label = verdict value.
- **SpecialistCard** — one specialist section; omitted entirely when its data
  is null (never render an empty card).
- **RiskRegister** — table of findings; severity dot left of description.
- **AuditTrail** — vertical timeline of `AuditEntry` rows.
- **HitlForm** — numbered clarifying questions, each with a textarea + context
  line; primary "Submit Answers", ghost "Override (accept risk)".

## Rules

- No emojis as icons. Status comes from color + label, not glyphs.
- Animate only `opacity` (e.g. loading fade). No layout animation.
- Loading state: disable trigger + show inline "Analyzing…" with a subtle pulse.
- Empty/missing data is omitted, never shown as an empty box.
