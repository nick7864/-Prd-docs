## 1. 重構 `_run_adk_pipeline` 為 async

- [x] 1.1 對應 spec requirement「ADK pipeline SHALL await async session service calls」：將 `src/agents/orchestrator.py` 中 `_run_adk_pipeline(prd_id, prd_content)` 改為 `async def`，並在兩處 coroutine 呼叫加上 `await`：`session = await session_service.create_session(app_name=..., user_id=...)` 與 `final_session = await session_service.get_session(app_name=..., user_id=..., session_id=...)`。`Runner.run(...)` 保持同步迭代消費（不可 `await`，否則 `TypeError`）。驗證：`uv run python -c "import inspect; from agents.orchestrator import _run_adk_pipeline; print(inspect.iscoroutinefunction(_run_adk_pipeline))"` 印出 `True`。
- [x] 1.2 對應 spec requirement「Triage entry point SHALL expose synchronous API」：在 `src/agents/orchestrator.py` 頂部新增 `import asyncio`，並將 `triage()` 中呼叫 `_run_adk_pipeline` 那一行從 `result = _run_adk_pipeline(prd_id, prd["content"])` 改為 `result = asyncio.run(_run_adk_pipeline(prd_id, prd["content"]))`。`triage()` 本身維持 `def`（非 `async def`），呼叫端（`eval/judge.py`、`src/main.py`、Antigravity Skill）皆不需改動。驗證：`uv run python -c "import inspect; from agents.orchestrator import triage; print(inspect.iscoroutinefunction(triage))"` 印出 `False`。

## 2. 保留既有失敗處理合約

- [x] 2.1 對應 spec requirement「Pipeline failure mode SHALL preserve observable audit trail」：確認 `triage()` 中包住 `asyncio.run(_run_adk_pipeline(...))` 的 `try/except Exception` 仍捕捉所有例外、append `AuditEntry(stage="specialists", status="failed", error=str(exc))`、回傳 `TriageReport(verdict=Verdict.NEEDS_CLARIFICATION, status="terminated", audit_trail=audit, policy_decision=decision)`。驗證：閱讀修改後的 `triage()` 函式，確認 `except` 區塊未刪、欄位未改、`policy_decision=decision` 仍在（不能變 `None`）。

## 3. 啟用既有的 4 個 skipped 整合測試

- [x] 3.1 找出 `tests/test_orchestrator.py` 與 `tests/test_pipeline_integration.py` 中所有 `@pytest.mark.skipif("GOOGLE_API_KEY" not in os.environ, ...)` 或等價 skip 條件的測試（共 4 個），確認它們在 `GOOGLE_API_KEY` 設妥時會真正執行 `triage(prd_id)` 並斷言 `verdict` / `completeness_score`。若這些測試是用 mock 而非真呼叫 ADK，則新增一個 `test_real_adk_pipeline_runs` 測試：設 key 時跑 `triage("prd-001")`，斷言 `report.verdict == Verdict.PASS` 且 `report.audit_trail[-1].status != "failed"`。驗證：`uv run pytest tests/test_orchestrator.py tests/test_pipeline_integration.py -v` 在設 `GOOGLE_API_KEY` 後全部綠燈、無 skip；在未設 key 時保持原本的 skip 行為（不退化）。

## 4. 端對端驗收

- [ ] 4.1 在 `GOOGLE_API_KEY` 已設的環境下跑 `uv run python eval/judge.py`，確認輸出為 `Verdict accuracy: 100%`、`Checks: 9/9 passed`、exit code 0；5 個 PRD 全部印 ✅。若 accuracy < 100%，逐案查 audit_trail 找剩餘問題（可能為 LLM 不穩定，需要 2 次以上 retry 取多數）。驗證：實際指令輸出擷取為證據。
- [x] 4.2 在未設 `GOOGLE_API_KEY` 的環境下跑 `uv run pytest --tb=no -q`，確認仍為 `121 passed, 4 skipped`（沒有把任何測試改壞、沒新增非預期的 failure）。驗證：指令輸出的最後一行統計。
- [x] 4.3 在未設 `GOOGLE_API_KEY` 的環境下跑 `uv run python eval/judge.py`，確認 `prd-003` 仍正確 reject（policy gate 不需要 key）、其餘 4 案走「沒 key 樂觀 pass」路徑時 `eval/judge.py` 的輸出符合 `orchestrator.py` 第 155-170 行的 fallback 行為（這部分會印 warning 但不應 crash）。驗證：指令完成不抛例外、exit code 與 `prd-003` 正確性對齊。
