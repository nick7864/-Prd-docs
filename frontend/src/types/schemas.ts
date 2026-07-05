// TypeScript mirror of src/models/schemas.py — the API contract.
// Backend serializes via model_dump(mode="json"): enums → strings, datetimes → ISO strings.

export type Verdict = "pass" | "needs_clarification" | "reject";
export type Severity = "low" | "medium" | "high" | "critical";
export type ReportStatus = "completed" | "awaiting_pm" | "terminated";
export type AuditStageStatus = "running" | "completed" | "failed" | "skipped";

export interface PrdListItem {
  id: string;
  title: string;
  status: string;
  updated_at: string;
}

export interface Finding {
  description: string;
  severity: Severity;
}

export interface RiskFinding extends Finding {
  compliance_framework?: string | null;
}

export interface PolicyViolation {
  type: string;
  pattern: string;
  line_number?: number | null;
}

export interface PolicyDecision {
  allowed: boolean;
  violations: PolicyViolation[];
}

export interface MissingSection {
  section: string;
  severity: Severity;
}

export interface CompletenessReport {
  agent_name: string;
  completeness_score: number;
  missing_sections: MissingSection[];
  raw_analysis: string;
}

export interface AmbiguousItem {
  phrase: string;
  type: string;
  generated_question: string;
}

export interface ClarityReport {
  agent_name: string;
  ambiguous_items: AmbiguousItem[];
  raw_analysis: string;
}

export interface ArchitectureConflict {
  description: string;
  severity: Severity;
}

export interface IntegrationPoint {
  description: string;
  service?: string | null;
}

export interface ArchitectureReport {
  agent_name: string;
  conflicts: ArchitectureConflict[];
  integration_points: IntegrationPoint[];
  raw_analysis: string;
}

export interface RiskReport {
  agent_name: string;
  findings: RiskFinding[];
  raw_analysis: string;
}

export interface FailedReport {
  agent_name: string;
  status: "failed";
  error: string;
}

export interface ClarifyingQuestion {
  question_id: string;
  question: string;
  context?: string | null;
}

export interface PmAnswer {
  question_id: string;
  answer: string;
}

export interface AuditEntry {
  stage: string;
  status: AuditStageStatus;
  agent_name?: string | null;
  error?: string | null;
}

export interface ConfidenceInterval {
  low: number;
  median: number;
  high: number;
}

export interface Estimate {
  point_estimate_days: number;
  confidence_interval: ConfidenceInterval;
  drivers: string[];
  low_confidence: boolean;
}

export interface Ticket {
  title: string;
  description: string;
  acceptance_criteria: string[];
  estimated_effort_days: number;
  dependencies: string[];
}

export interface TriageReport {
  prd_id: string;
  verdict: Verdict;
  status: ReportStatus;
  session_id?: string | null;
  completeness?: CompletenessReport | null;
  clarity?: ClarityReport | null;
  architecture?: ArchitectureReport | null;
  risk?: RiskReport | null;
  failed_agents: FailedReport[];
  risk_register: Finding[];
  clarifying_questions: ClarifyingQuestion[];
  pm_responses: PmAnswer[];
  estimate?: Estimate | null;
  tickets: Ticket[];
  audit_trail: AuditEntry[];
  hitl_overridden: boolean;
  policy_decision?: PolicyDecision | null;
}

export interface SessionStatus {
  status: ReportStatus;
  prd_id: string;
  expires_at: string;
}
