## Context

本設計回應 Google × Kaggle「AI Agents Intensive Vibe Coding Capstone Project」競賽,在 2026-06-28 至 2026-07-06 共 8 天內交付一個生產級思維下的 PRD 入場 Triager。

**現況約束**:
- 專案為 greenfield,目前只有 Spectra scaffolding(無應用程式碼)
- 必須展示 ≥ 3 個(目標 6 個)課程 Key Concepts:ADK、MCP、Antigravity、Security、Deployability、Skills
- 提交形式:Writeup(≤2,500 字)+ YouTube 影片(≤5 分鐘)+ 公開 GitHub Repo + Media Gallery
- 開發者為軟體業背景,熟悉 Python 與 ADK 概念
- 部署目標:Google Cloud Run(需已啟用計費的 GCP 專案)

**課程對齊**:
- ADK 2.0 圖形工作流程(Day 3-4)
- MCP 自建伺服器(Day 2)
- Policy Server + HITL 護欄(Day 4)
- Agent Runtime / Cloud Run 部署(Day 5)
- Skills 漸進式揭露(Day 3)

## Goals / Non-Goals

**Goals:**

- 交付一個可在 Cloud Run 上運行的 PRD 入場 Triager,接受 PRD Markdown 文件,輸出結構化體檢報告
- 展示全部 6 個 Key Concepts,鎖定「衝高分」組合
- 架構保留擴充點,允許 MVP(4 agents 子集)先交付再加層
- 所有護欄(Policy、HITL)可被驗證、可在影片展示
- 程式碼有完整 README + 設計註解,讓評審能理解「為什麼這樣設計」

**Non-Goals:**

- 不建構 Jira / Slack / GitHub 的真實雙向整合(僅在文件中說明擴充點)
- 不處理多種 PRD 格式(Word、PDF)——僅支援 Markdown
- 不為真實企業團隊提供生產級 SLA——這是競賽作品集,非商業產品
- 不實作使用者認證 / 多租戶隔離(公開端點 + 範例資料即可)
- 不實作多輪對話式釐清(Ambient 模式)——HITL 採單次問答 + override

## Decisions

### Decision: Document MCP Server via ADK McpServer module

以 ADK 內建的 `google.adk.tools.mcp_tool` 模組實作自建 MCP server,而非用獨立的 `mcp` Python 套件從零搭建。原因:ADK 模組與 ADK agent workflow 原生整合,工具註冊與型別推導自動處理,且符合課程「Agents CLI + ADK」技術堆疊要求。MVP 階段先實作 `list_prds` 與 `get_prd` 兩個 tool,`get_architecture_context` 與 `get_similar_prds` 屬強化層。

**資料來源**:`data/prds/*.md`(範例 PRD)+ `data/architecture/architecture.md` + `data/architecture/adr/*.md`(範例 ADR)。檔案以 frontmatter(YAML)携带 metadata(id、title、status、updated_at),正文為 Markdown。

### Decision: Four specialist agents as LlmAgent with Pydantic structured output

四個專家代理皆實作為 `google.adk.agents.LlmAgent`,各自有獨立的 system prompt 與 output schema(Pydantic model)。不使用 `FunctionTool` 包裝,因為這四個代理的「智能」全在 LLM 推理,不需要呼叫外部函式。結構化輸出確保 Synthesis Agent 能可靠解析。

**Output schema 統一欄位**:每個專家報告都有 `agent_name`、`findings`(list)、`severity_summary`(dict)、`raw_analysis`(str)。差異在 findings 的結構——例如 Clarity 的 finding 帶 `generated_question`,Risk 的 finding 帶 `compliance_framework`。

### Decision: ADK Parallel workflow for specialist fan-out

用 ADK 2.0 的 `Workflow` + `ParallelNode` 實作四專家並行。並行勝過循序的理由:(1) 評分表明確看重 ADK 圖形結構的豐富度,並行 + 條件分支 + 循序三種模式都出現才是高分;(2) 四個代理讀同一份 PRD、無寫入衝突,天然適合並行。

**容錯**:任一代理拋出例外時,orchestrator 捕獲並填入 `failed` 報告,其餘代理繼續。這比「一個失敗全部重來」更貼近生產級思維,也更好 demo(可以展示「即使一個 agent 壞了,pipeline 仍產出部分報告」)。

### Decision: Synthesis Agent with critical-risk veto logic

Synthesis Agent 是一個 `LlmAgent`,但在 LLM 生成後加一個 deterministic post-check:若任一 Risk finding 的 severity 為 `critical`,則強制把 verdict 覆寫為 `needs_clarification`,不論 LLM 怎麼說。理由:LLM 對「critical 是否該擋」的判斷不穩定,但這是安全關鍵決策,必須可預測。這個 hybrid(LLM 生成 + 規則覆寫)設計本身可寫進 Writeup,展示「知道何時不該信任 LLM」。

### Decision: HITL gate via ADK InteractiveCallback + workflow state

HITL gate 用 ADK 的 `InteractiveCallback`(或等效的 `CallbackContext.pause`)實作:到達 gate 節點時,pipeline 暫停、把 clarifying questions 寫入 workflow state、發出事件等待 PM 回應。PM 透過 CLI 或 API 提交回應後,pipeline 從 state 恢復、繼續往下。

**MVP 簡化**:若 InteractiveCallback 在 8 天內來不及完整實作,退而求其次改為 synchronous 模式——CLI 互動式提示(prompt)直接在終端讀 PM 回應。影片展示時仍清楚可見「系統暫停 → 問問題 → PM 回答 → 系統繼續」。Writeup 誠實標註此為同步簡化版。

### Decision: Policy gate via regex patterns + lightweight LLM triage

Policy gate 分兩層:(1) regex 層掃描已知模式(Google API key `AIza...`、email、phone、常見 secret prefix),這層確定性、零成本、可在影片直接展示規則;(2) LLM 層判斷 regex 抓不到的語意型敏感資訊(例如「客戶名單」這類描述性 PII)。regex 層是必做、LLM 層是強化。

**Policy 規則存放於** `src/policy/policies.yaml`,讓規則可被 review、可在影片展示檔案內容。這直接展示 Day 4 的 Policy Server 觀念。

### Decision: Estimation via vector similarity retrieval + LLM reasoning

Estimation Agent 先呼叫 `get_similar_prds` 取得歷史類比,再讓 LLM 基於類比的 actual effort 推估目標 PRD 的點估計與信心區間。向量搜尋用 SQLite + pgvector-lite(或純 Python cosine similarity over embeddings),不需獨立資料庫伺服器,降低部署複雜度。

**無歷史資料時的退化**:若 `get_similar_prds` 回空,Estimation Agent 改用 LLM 基於 PRD 複雜度啟發式估算,並 flag `low_confidence: true`、放大信心區間。這確保即使歷史資料庫為空,pipeline 仍能產出估算。

### Decision: Phased delivery (MVP → strengthen → bonus)

| 階段 | 內容 | Key Concepts | 提交能力 |
|------|------|-------------|---------|
| MVP(D1-D4) | Document MCP(2 tools)+ Completeness + Clarity + Synthesis + Markdown output + Cloud Run 部署 | ADK + MCP + Antigravity + Deployability = 4 | 可提交、過門檻 |
| 強化(D5-D6) | + Architecture Fit + Risk agents + Policy gate + HITL gate | + Security = 5 | 穩健高分區 |
| 加分(D7) | + Estimation + Task Breakdown + 自訂 Skill | + Skills = 6 | 衝獎區 |

**階段切換準則**:D4 晚上必須有可 demo 的 MVP。若 MVP 未通,立即放棄強化層,把 D5-D7 全拿去做部署 + 錄影。MVP 與強化層的差異只是「多兩個 agent + 兩個護欄」,架構不需重寫——只要在 orchestrator 的 ParallelNode 多加兩個 agent、在 synthesis 前多加 policy gate 節點。

### Decision: Deployment via Dockerfile + Cloud Run + agents-cli deploy

容器化用 `Dockerfile`(基於 `python:3.12-slim`),透過 `agents-cli deploy --project --region` 部署至 Cloud Run。公開端點接受 POST `/triage` with `{"prd_id": "..."}` 回傳 `TriageReport` JSON。README 記錄重現步驟。

**部署 fallback**:若 GCP 計費未啟用或部署失敗,D5-D6 改部署到本機 + ngrok 公開通道,影片仍可展示「公開可訪問的端點」。Writeup 誠實標註部署方式。

### Decision: ADK CLI toolchain correction (agents-cli → adk)

Spec 與 tasks.md 中提到的 `agents-cli` 是 **Google Agents CLI 舊名**;2026 年起 ADK 2.x 已內建 CLI,entry point 為 `adk`(由 `google-adk` 套件直接提供)。**不需要另外安裝 `google-agents-cli`**。指令對應:

| spec/tasks.md 寫法 | 實際指令(ADK 2.3.0) | 用途 |
|---|---|---|
| `agents-cli scaffold` | `adk create` | 建立 agent app 骨架 |
| `agents-cli playground` | `adk web` | 啟動 Web UI playground(熱重載) |
| `agents-cli run` | `adk run` | CLI 跑單一 agent |
| `agents-cli eval` | `adk eval` | 用 eval set 評估 |
| `agents-cli deploy --project --region` | `adk deploy cloud_run --project --region` | 部署至 Cloud Run |
| `agents-cli lint` | (無直接對應;`adk conformance` 最接近) | 規範檢查 |

**Impact**:tasks.md 中所有引用 `agents-cli` 的地方,實際執行時改用 `adk`。verification targets(例:`agents-cli --version`)對應改為 `uv run adk --version`(已驗證返回 `adk, version 2.3.0`)。

> 註:`uvx google-agents-cli setup` 來自 Day 3 課程,用來安裝 7 個領域技能到 Antigravity。本專案不依賴那些領域技能(只用自訂 `prd-analysis` Skill),因此略過這步不影響 Key Concepts 展示。

### Decision: Antigravity showcase strategy (Key Concept — Video only)

Antigravity 是 Day 1-2 課程核心,官方評分表明文 **Antigravity 只在 Video 算數**。本專案在以下三個點部署 Antigravity 介入,並於 YouTube 影片(≤5 分鐘)錄下對應畫面:

| 階段 | Antigravity 用途 | 影片展示重點(30-60 秒/段) |
|---|---|---|
| **D1 sample data** | 用 Antigravity IDE + 自然語言生成 `prd-001~005` 的初稿(實際底稿由人類修正) | Antigravity 對話視窗 + 生成 PRD 的差異畫面 |
| **D2-D5 agent dev** | 用 Antigravity IDE 作為主要程式碼編輯器,展示斜線指令(`/browser` 開文件、`/schedule` 排程測試) | IDE 介面、檔案結構、Skill 漸進式揭露的 tooltip |
| **D6 demo run** | 把自訂 Skill `prd-analysis` 裝到 `~/.gemini/config/skills/` 或專案 `.agents/skills/`,在 Antigravity 內觸發 triage pipeline | Skill 觸發 → pipeline 跑 → 結構化報告輸出的完整鏈路 |

**為什麼要這樣安排**:
1. Antigravity 不能「只用 logo」 — 評審想看**真的在 Antigravity 裡操作**
2. 跨 D1/D5/D6 三個點出現,剪輯時有素材多段剪接,敘事立體
3. 把自訂 Skill 在 Antigravity 內觸發,**同時命中 Antigravity + Skills 兩個 Key Concepts**,一石二鳥

**Fallback**:若 D6 前 Antigravity 未裝(開發者下載延遲),至少錄 D6 那段(Skill 觸發),D1/D5 用其他 IDE 畫面,Writeup 誠實標註。但**只有 D6 那段足夠展示 Key Concept**,建議務必錄到。

**影片拍攝清單更新(D6/D7 階段)**:
- [ ] Antigravity IDE 介面導覽(30 秒)
- [ ] 自訂 Skill `prd-analysis` 在 Antigravity 內觸發 triage(45 秒)
- [ ] Pipeline 跑完後結構化報告畫面(15 秒)
- [ ] (可選)用 `/browser` 開部署端點的 curl 結果(15 秒)

### Decision: Rename src/mcp to src/doc_mcp (namespace collision)

D2 實作時發現:**`src/mcp/` 與上游 `mcp` PyPI 套件命名空間撞名**。Python 在 `pythonpath=["src"]` 下執行 `from mcp.server.fastmcp import FastMCP` 時,會優先找到 `src/mcp/server.py`(我們的本地模組),導致 `ModuleNotFoundError: No module named 'mcp.server.fastmcp'; 'mcp.server' is not a package`。

**修正**:本地模組更名為 `src/doc_mcp/`。所有 import 從 `from mcp.X import Y`(指我們的 code)改為 `from doc_mcp.X import Y`。上游 `mcp` 套件的 import 不受影響。

**Impact**:
- 路徑:`src/mcp/server.py` → `src/doc_mcp/server.py`,`src/mcp/repository.py` → `src/doc_mcp/repository.py`
- 加入檔:`src/doc_mcp/__init__.py` 說明命名由來
- tasks.md 中所有 `src/mcp/` 路徑引用,實際對應 `src/doc_mcp/`
- 執行 MCP server:`uv run python -m doc_mcp.server`(原本會是 `-m src.mcp.server`)

**為什麼不重新命名上游依賴**:上游 `mcp` 套件是 Model Context Protocol 官方 Python SDK,改名會破壞所有 MCP 相容工具的整合。本地模組改名成本最低。

## Implementation Contract

### Contract: Document MCP Server

**Behavior**: MCP server 啟動後,任何 MCP 相容客戶端(含 ADK agent、Claude Desktop、Cursor)可連線並呼叫四個工具讀取文件庫。工具回傳符合 schema 的 JSON。

**Interface**:
- Tool `list_prds() -> [{"id": str, "title": str, "status": str, "updated_at": str}]`
- Tool `get_prd(prd_id: str) -> {"id": str, "title": str, "content": str, "metadata": dict} | {"error": str}`
- Tool `get_architecture_context() -> {"architecture_doc": str, "adrs": [{"id","title","status","content"}]}`
- Tool `get_similar_prds(query: str, top_k: int = 3) -> [{"id","title","similarity_score": float}]`

**Failure modes**:
- 未知 `prd_id`:回傳 `{"error": "PRD not found: <id>"}`,不拋例外
- 讀檔失敗(權限、编码):回傳 `{"error": "..."}`
- `data/prds/` 不存在:server 啟動時自動建立空目錄,不 crash

**Acceptance criteria**:
- 從 ADK playground 能看到四個工具出現在工具列表
- 呼叫 `list_prds` 在空目錄回 `[]`,在含 3 檔的目錄回 3 個物件
- 呼叫 `get_prd` 帶未知 id 回傳 error 物件,非例外
- `pytest tests/test_mcp_server.py` 全綠

**Scope boundaries**:
- In:四個唯讀工具,本地檔案系統資料來源
- Out:寫入工具(create/update/delete PRD)、認證、多租戶、外部資料庫

### Contract: Four Specialist Agents

**Behavior**: 給定 PRD 全文,每個代理產出結構化報告(findings list + severity summary + raw analysis)。四個代理可獨立測試,不依賴彼此。

**Interface**:
```
CompletenessReport: {completeness_score: int, missing_sections: [{section, severity}], ...}
ClarityReport: {ambiguous_items: [{phrase, type, generated_question}], ...}
ArchitectureReport: {conflicts: [{description, severity}], integration_points: [...], ...}
RiskReport: {findings: [{description, severity, compliance_framework}], ...}
```

**Failure modes**:
- LLM 回應無法解析為 schema:重試一次(加更嚴格的 system prompt),仍失敗則回 `{"agent_name": ..., "status": "failed", "error": "unparseable"}`
- LLM API 逾時 / 限流:回 `failed` 報告,不阻塞其他代理

**Acceptance criteria**:
- 餵入「缺 acceptance criteria 的 PRD」,CompletenessReport.completeness_score < 60 且 missing_sections 含 `acceptance_criteria` / severity `high`
- 餵入含 `AIza...` 的 PRD,RiskReport 若被執行(政策 gate 未擋)應回 finding 含 `compliance_framework: "secret_exposure"`
- 餵入含「the system shall be fast」的 PRD,ClarityReport.ambiguous_items 至少一筆 type `vague_quantifier`
- `pytest tests/test_agents/` 全綠

**Scope boundaries**:
- In:單一 PRD 的靜態分析,不跨 PRD 比對(除 Architecture 需讀架構文件)
- Out:PRD 之間的版本 diff、多人協作痕跡分析

### Contract: Orchestrator Workflow Graph

**Behavior**: 給定 `prd_id`,workflow 依序執行:intake(MCP) → policy gate → parallel(4 specialists) → synthesis → conditional(HITL?) → estimation → breakdown → output。可序列化為 ADK graph 並被 `agents-cli playground` 視覺化。

**Interface**:
- Entry: `triage(prd_id: str) -> TriageReport`
- `TriageReport` 含:`prd_id, verdict(pass|needs_clarification|reject), risk_register, completeness, clarifying_questions, pm_responses, estimate, tickets, audit_trail, hitl_overridden: bool`

**Failure modes**:
- MCP `get_prd` 失敗:回 `TriageReport(verdict="reject", audit_trail=[{stage:"intake", status:"failed"}])`
- Policy gate reject:回 `TriageReport(verdict="reject")` 帶 redaction report,不進入 specialist
- 一個 specialist failed:synthesis 仍執行,audit_trail 記錄哪個 agent failed
- HITL timeout(>24h):回 `TriageReport(verdict="needs_clarification", status="awaiting_pm")`,無 estimate

**Acceptance criteria**:
- 餵入含 API key 的 PRD,report.verdict 為 `reject`,report 不含 specialist findings
- 餵入乾淨 PRD,report.verdict 為 `pass`,含 estimate + tickets
- 餵入含 critical risk 的 PRD,report.verdict 為 `needs_clarification`,含 clarifying_questions
- 序列化 workflow graph,graph 含 ≥1 parallel segment + ≥1 conditional edge + ≥3 sequential nodes
- `pytest tests/test_orchestrator.py` 全綠

**Scope boundaries**:
- In:單次 triage run,同步或單次非同步(PM 回應後恢復)
- Out:批次 triage、排程觸發、多使用者的並發 run 隔離

### Contract: HITL Gate

**Behavior**: verdict 為 `needs_clarification` 時,pipeline 暫停、輸出 clarifying questions、等待 PM 回應。PM 回應後恢復;PM override 則強制通過但標記;逾時則終止。

**Interface**:
- PM 回應 API:POST `/triage/<run_id>/respond` body `{"answers": [{"question_id", "answer"}]}` 或 `{"override": true}`
- 同步 CLI fallback:`input()` 讀 PM 回應

**Failure modes**:
- PM 提交不符 schema 的 answers:回 400,pipeline 維持暫停
- Override 後 report.hitl_overridden 為 true,risk_register 保留原 findings

**Acceptance criteria**:
- 觸發 HITL 後,workflow state 顯示 `paused`,`status` 為 `awaiting_pm`
- PM 回應 3 個 answers,pipeline 恢復並產出含 `pm_responses` 的 report
- PM override,report.verdict 變 `pass` 且 `hitl_overridden: true`
- 逾時(測試時用短 timeout 如 1 秒),report.status 為 `awaiting_pm` 且無 estimate

**Scope boundaries**:
- In:單次問答 + 單次 override
- Out:多輪追問、協同多位 PM、自動升級到上級

### Contract: Policy Gate

**Behavior**: 攝取 PRD 全文後,先跑 regex 掃描,命中任一模式則拒絕。未命中 regex 才進 LLM 層(若有)。拒絕時產出 redaction report 列出命中模式與位置。

**Interface**:
- `check_policy(prd_content: str) -> PolicyDecision`
- `PolicyDecision`: `{allowed: bool, violations: [{"type", "pattern", "line_number"}]}`

**Failure modes**:
- regex 引擎例外:視為 deny(安全預設),回 `allowed: false, violations: [{"type": "scanner_error"}]`

**Acceptance criteria**:
- 餵入含 `AIzaSyD...` 的字串,allowed=false,violations 含 type `google_api_key`
- 餵入含 `john@example.com`,allowed=false,violations 含 type `email`
- 餵入「OAuth 2.0」無命中,allowed=true
- 規則檔 `src/policy/policies.yaml` 存在且可被 human review

**Scope boundaries**:
- In:已知模式的 regex 掃描 + 可選 LLM 語意層
- Out:加解密、資料外洩防護(DLP)等級的深度內容分析

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| 8 天內做不完 6 agents | 分層交付:MVP 只 2 agents + 2 MCP tools,確保 D4 可 demo;其餘逐層加 |
| HITL InteractiveCallback 實作複雜 | 同步 CLI fallback:影片展示仍清楚,Writeup 標註簡化 |
| Cloud Run 部署失敗(GCP 未啟用計費) | Fallback:本機 + ngrok;README 記錄兩種部署路徑 |
| `get_similar_prds` 無歷史資料 | 退化路徑:LLM 啟發式 + flag `low_confidence`,pipeline 不中斷 |
| 評審質疑「agent 只是包裝 LLM call」 | 架構圖與 Writeup 強調:parallel orchestration + conditional branch + synthesis veto 是 rule 無法做到的協調邏輯 |
| 範例 PRD 太假,評審不買單 | 範例 PRD 取材自真實軟體業場景(匿名化):dark mode、rate limiting、第三方支付整合 |

## Migration Plan

本專案為 greenfield,無既有系統需遷移。部署步驟:

1. D6:`docker build -t prd-triager .` 本機驗證
2. D6:`agents-cli deploy --project <gcp-project> --region asia-east1` 部署至 Cloud Run
3. D6:`curl -X POST <endpoint>/triage -d '{"prd_id":"prd-001"}'` 驗證端點
4. Fallback:`uvicorn src.main:app --host 0.0.0.0` + `ngrok http 8000`

**Rollback**:Cloud Run 支援 revision rollback;本機 fallback 隨時可用。

## Open Questions

1. GCP 專案是否已啟用計費?若否,D6 前需處理,或直接走 ngrok fallback。
2. 範例 PRD 的領域——是否鎖定某個一致主題(例如:「給一個電商平台的 5 份 PRD」)以強化 demo 敘事?建議鎖定單一虛構產品(例:`ShopFlow` 電商),讓 5 份 PRD 互相參照、展示 `get_similar_prds` 的價值。
3. 影片是否由開發者本人配音?或用 AI voiceover?影響 D7 時程。

