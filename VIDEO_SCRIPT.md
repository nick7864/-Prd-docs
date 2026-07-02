# YouTube Video Script — PRD Triage Agent (≤5 minutes)

> Per spec: video MUST show Antigravity + Deployability (both Video-only Key Concepts).
> Target length: 4:30-4:50 (leave 10-30s buffer under the 5:00 hard limit).

## Pre-recording checklist

- [ ] `export GOOGLE_API_KEY="..."` set in terminal
- [ ] `uv run adk web` tested — playground loads at localhost:8000
- [ ] Antigravity opened, project folder loaded, `prd-analysis` Skill visible
- [ ] Deployment endpoint live (Cloud Run URL or ngrok URL)
- [ ] Screen recording software ready (QuickTime / OBS)
- [ ] Microphone tested

---

## Segment 1: Problem Statement (0:00 — 0:45, 45s)

**Screen**: Terminal showing a PRD file scrolling, then cut to a Jira ticket with "blocked — missing acceptance criteria"

**Narration**:
> "When a PM hands a PRD to engineering, the team often discovers problems only during implementation — missing acceptance criteria, architecture conflicts, vague requirements. By then, it's too late: estimates are wrong, sprints are missed.
>
> I built PRD Triage Agent — a multi-agent system that catches these issues BEFORE engineering begins. Four specialist agents analyze the PRD in parallel, flag risks, and produce a structured triage report. Let me show you how it works."

## Segment 2: Architecture Overview (0:45 — 1:30, 45s)

**Screen**: Architecture diagram from README.md (the ASCII pipeline). Animate/highlight each stage as you mention it.

**Narration**:
> "The pipeline has five stages. First, the Document MCP Server reads the PRD. Then a Policy Gate rejects any PRD containing API keys or PII. Next, four ADK agents run in PARALLEL — Completeness, Clarity, Architecture, and Risk. A Synthesis Agent merges their findings, and a deterministic veto layer forces a pause if any risk is critical. Finally, a Human-in-the-Loop gate asks the PM clarifying questions.
>
> Built on Google ADK 2.0 with Gemini, using MCP for the document server, and deployed to Cloud Run."

## Segment 3: Antigravity Demo (1:30 — 2:30, 60s) — **REQUIRED Key Concept**

**Screen**: Switch to Antigravity app. Show:
1. Project open in Antigravity IDE (10s)
2. `prd-analysis` Skill in the Skills panel — point to it (10s)
3. Trigger the Skill by asking "Triage prd-002" (20s)
4. Watch the pipeline run — show parallel agents executing (20s)

**Narration**:
> "I developed this entirely in Google Antigravity. The custom Skill `prd-analysis` triggers the triage pipeline directly from the IDE. Watch as I ask it to triage a PRD that's missing acceptance criteria — the Completeness Checker catches it immediately, and the pipeline produces a structured report with clarifying questions for the PM."

## Segment 4: Deployment Demo (2:30 — 3:15, 45s) — **REQUIRED Key Concept**

**Screen**: Terminal showing:
1. `curl -X POST <endpoint>/health` → `{"status":"ok"}` (10s)
2. `curl -X POST <endpoint>/triage -d '{"prd_id":"prd-003"}'` → reject verdict (20s)
3. Show the Cloud Run console (or ngrok URL) proving public access (15s)

**Narration**:
> "The agent is deployed on Google Cloud Run. This is a public endpoint — anyone can send a PRD for triage. Watch what happens when I submit a PRD containing an embedded API key: the Policy Gate catches it instantly and rejects the PRD before any agent even reads it."

## Segment 5: Demo Cases (3:15 — 4:15, 60s)

**Screen**: Show 2-3 triage results side by side (from `reports/` directory or terminal output):

| Case | What to show | Time |
|---|---|---|
| prd-001 (Dark Mode) | verdict=pass, completeness=88/100 | 15s |
| prd-004 (Search Perf) | vague terms flagged ("fast", "scalable") + clarifying questions | 25s |
| prd-005 (Inventory Sync) | verdict=pass + estimate + tickets generated | 20s |

**Narration**:
> "Five sample PRDs exercise every triage path. A complete PRD passes with a high completeness score. A PRD with vague terms like 'the system shall be fast' gets flagged by the Clarity Checker, which generates specific clarifying questions. And a well-scoped PRD not only passes — it gets an effort estimate and a ticket breakdown."

## Segment 6: The Build (4:15 — 4:45, 30s)

**Screen**: Quick montage — code editor scrolling through agent files, test output (`119 passed`), Spectra spec view

**Narration**:
> "The entire project was built with Spec-Driven Development using Spectra — 29 of 30 tasks tracked to completion, 119 tests passing. Six Google AI agent Key Concepts: ADK for multi-agent orchestration, MCP for the document server, Antigravity for development, Security via policy gates and HITL, Cloud Run for deployment, and custom Skills. All in eight days."

## Outro (4:45 — 4:50, 5s)

**Screen**: GitHub repo URL + "Built for Google × Kaggle AI Agents Capstone 2026"

---

## Recording tips

1. **Record in one take** if possible — editing eats time. If you stumble, pause 3 seconds, re-start the sentence.
2. **Narration first, screen second** — record audio cleanly, then re-record screen if needed.
3. **Font size**: increase terminal font to 18pt+ for readability.
4. **No music** — evaluation cares about content clarity, not production value.
5. **Upload as Public** — private/unlisted videos cannot be submitted.
