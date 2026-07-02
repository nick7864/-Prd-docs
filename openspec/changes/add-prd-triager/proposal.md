## Why

軟體團隊收到新需求(PRD)後,普遍缺少一致的「入場體檢」流程:PM 寫完 PRD 直接丟給工程,工程師在實作中才發現缺 acceptance criteria、跟現有架構衝突、有合規風險、或關鍵術語模糊。這導致 rework、估算失準、後期才暴露的風險。現有的靜態檢查工具(範本驗證、linting)只能抓格式問題,無法判斷「這份 PRD 是否真的可執行」——這需要理解上下文、類比歷史、多面向評估,正是 agent 擅長、規則引擎做不到的事。

本專案回應 Google × Kaggle「AI Agents Intensive Vibe Coding Capstone Project」競賽,在 8 天內交付一個生產級思維下的 PRD 入場 Triager,整合五天課程所學(ADK 多代理編排、MCP 自建伺服器、安全護欄、雲端部署)。

## What Changes

- 新增 **Document MCP Server**:把 PRD 文件庫與架構文件暴露為 MCP 工具,讓 agent 可透過標準協定讀取
- 新增 **PRD Triage Pipeline**:4 個專家代理(完整度 / 架構適配 / 風險合規 / 清晰度)並行分析同一份 PRD,由 Synthesis Agent 彙整成結構化報告
- 新增 **條件式 HITL Gate**:高風險或高模糊度時暫停 pipeline,生成釐清問題清單交回 PM,PM 回覆後才繼續估算
- 新增 **Policy Server**:檢查 PRD 是否含 PII / 機密資訊,未通過則拒絕進入 pipeline
- 新增 **Estimation + Task Breakdown**:釐清完成後,類比歷史 PRD 產出工作量估算(含信心區間)與可執行 ticket 拆分
- 新增 **Cloud Run 部署**:容器化並部署至 Google Cloud Run,提供公開端點
- 新增 **自訂 Skill**(`prd-analysis`):封裝分析流程為可重用的 ADK Skill

## Capabilities

### New Capabilities

- `document-repository`: MCP server,將 PRD 文件庫與架構文件(architecture.md、ADRs)暴露為標準 MCP 工具(list_prds / get_prd / get_architecture_context / get_similar_prds),供 triage pipeline 與外部消費者使用
- `prd-triage`: 多代理 PRD 入場體檢 pipeline,從文件攝取 → Policy 檢查 → 4 專家並行分析 → Synthesis → 條件式 HITL Gate → 估算 → 任務拆分 → 結構化報告輸出

### Modified Capabilities

(none)

## Impact

- Affected specs: 新增 `document-repository`、`prd-triage` 兩個 capability spec
- Affected code:
  - New:
    - `src/mcp/server.py` — Document MCP server 入口
    - `src/agents/completeness.py` — 完整度檢查代理
    - `src/agents/clarity.py` — 清晰度檢查代理
    - `src/agents/architecture.py` — 架構適配評估代理
    - `src/agents/risk.py` — 風險合規檢查代理
    - `src/agents/synthesis.py` — 彙整代理
    - `src/agents/orchestrator.py` — 主 ADK workflow 編排
    - `src/agents/estimation.py` — 工作量估算代理(加分層)
    - `src/agents/breakdown.py` — 任務拆分代理(加分層)
    - `src/models/schemas.py` — Pydantic 結構化輸出 schema
    - `src/policy/policies.yaml` — Policy Server 規則
    - `data/prds/` — 範例 PRD 文件目錄
    - `data/architecture/` — 架構文件與 ADR 目錄
    - `eval/evalset.jsonl` — 評估資料集
    - `tests/` — pytest 單元與整合測試
    - `.agents/skills/prd-analysis/SKILL.md` — 自訂 Skill 定義
    - `Dockerfile` — Cloud Run 部署映像
    - `pyproject.toml` — uv 管理依賴
    - `README.md` — 專案文件
  - Modified: (none,greenfield 專案)
  - Removed: (none)

