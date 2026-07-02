## Why

`triage()` 函式內的 `_run_adk_pipeline` 在呼叫 ADK 2.x 的 `InMemorySessionService.create_session` / `get_session` 時使用同步寫法，但這兩個方法在當前安裝的 ADK 版本（`google-adk>=2.0`）已改為 `async`。實際呼叫 `eval/judge.py` 驗證：4 個需要 LLM specialist 的 PRD 全部以 `AttributeError("'coroutine' object has no attribute 'id'")` 失敗，LLM pipeline 從未真正端對端跑通過。

## Problem

`eval/judge.py` 對 5 個 PRD 跑出 `Verdict accuracy: 60%`（應為 100%），其中：

- `prd-003`（policy reject）正確——在 regex 攔截，未進 LLM pipeline。
- `prd-002`、`prd-004` 期望 `needs_clarification`，看似正確但其實是 `triage()` 的 `except` 接住 exception 後回傳 `needs_clarification`（`orchestrator.py:187-193`）的副作用，不是真的 LLM 判決。
- `prd-001`、`prd-005` 期望 `pass`，但 pipeline 掛掉後走 except 路徑被誤判成 `needs_clarification` → ❌ 驗收失敗。

錯誤蹤跡：

```
[orchestrator] ADK pipeline failed: AttributeError("'coroutine' object has no attribute 'id'")
RuntimeWarning: coroutine 'InMemorySessionService.create_session' was never awaited
```

## Root Cause

`src/agents/orchestrator.py:211` 的 `_run_adk_pipeline` 函式把 ADK API 當同步 call：

```python
session = session_service.create_session(app_name=..., user_id=...)  # ← 回傳 coroutine
runner = Runner(agent=root_agent, ...)
for event in runner.run(...):  # ← session.id 在這行爆炸
    ...
final_session = session_service.get_session(...)  # ← 同樣是 async，也沒 await
```

但 ADK 2.x 的這兩個方法已改為 coroutine（已用 `inspect.iscoroutinefunction` 驗證）。同步呼叫得到未執行的 coroutine 物件，後續存取 `.id` 時屬性錯誤。

## Proposed Solution

把 `_run_adk_pipeline` 改為 `async def`，內部 `await` 兩個 coroutine call；`triage()` 透過 `asyncio.run()` 呼叫 async 版本。`Runner.run()` 本身是同步 generator（已驗證），不需要 await，但要包在 async 函式內部即可。

不變的設計原則：保持 `triage(prd_id) -> TriageReport` 對外同步 API 不變（CLI / FastAPI / Antigravity Skill 呼叫者不需改動）——async 只在內部使用。

## Non-Goals

- 不修 `estimation_agent` / `breakdown_agent` 沒接上 pipeline 的問題（另一個獨立 change 處理）。
- 不重寫 ADK Workflow 取代 deprecated 的 `ParallelAgent` / `SequentialAgent`（同樣是獨立 change，目前能用）。
- 不改 4 個 specialist agent 的 instruction 或 schema——只動 orchestrator 的執行層。
- 不改 `triage()` 對外 signature，保持呼叫端零更動。

## Success Criteria

1. `uv run python eval/judge.py`（在 `GOOGLE_API_KEY` 已設的環境下）跑完 5 個 PRD 全部 ✅，輸出 `Verdict accuracy: 100%`、`Checks: 9/9 passed`、exit code 0。
2. `uv run pytest tests/test_orchestrator.py tests/test_pipeline_integration.py`——4 個本來被 skip（缺 key）的整合測試，在設 key 後全綠。其餘 121 個測試保持綠燈不退化。
3. `triage(prd_id)` 的對外同步 API 不變：CLI、FastAPI server、`eval/judge.py` 都不需要改呼叫端。
4. `prd-001`（Dark Mode）實際跑出 `verdict=pass`、`completeness_score >= 80`；`prd-004`（Search Perf）實際抓到 `fast` / `scalable` / `user-friendly` 至少一個 vague term。

## Capabilities

### New Capabilities

- `triage-pipeline-runtime`: 執行期合約——`triage()` 對外同步 API 與內部 ADK async 呼叫的邊界。此 bug 修復把這條邊界明確化為 spec 層級的可驗證要求。

### Modified Capabilities

(none — 既有 capability 目錄目前為空，前一個 change 尚未 archive，本 change 改以 New Capability 形式明確化執行期合約。)

## Impact

- Affected code:
  - Modified: `src/agents/orchestrator.py`（只動 `_run_adk_pipeline` 與 `triage()` 的呼叫方式）
  - Modified: `tests/test_orchestrator.py`、`tests/test_pipeline_integration.py`（為 4 個 skipped 整合測試補上 `@pytest.mark.asyncio` 或等價的 async wrapper，使其在設 key 時真的跑）
- Affected code (no change needed, but verified):
  - `src/main.py`（FastAPI `/triage` endpoint 呼叫 `triage()`，同步 API 不變）
  - `eval/judge.py`（呼叫 `triage()`，同步 API 不變）
  - `.agents/skills/prd-analysis/SKILL.md`（呼叫 `triage`，API 不變）
