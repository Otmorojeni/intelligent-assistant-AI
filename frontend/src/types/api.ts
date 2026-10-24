export type UserRole = "employee" | "dou_specialist" | "security_auditor" | "admin";
export type AccessLevel = "public" | "internal" | "dsp" | "confidential" | "secret";

export type ScreenId = "assistant" | "constructor" | "compliance" | "governance";

export interface HealthResponse {
  status: string;
  db_connected: boolean;
  ollama_connected: boolean;
  active_version: string;
  timestamp: string;
}

export interface TokenRequest {
  username: string;
  role: UserRole;
  password?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: UserRole;
  username: string;
}

export interface SourceRef {
  document_code: string;
  document_title: string;
  chapter: string | null;
  clause: string | null;
  page_number?: number;
  quote: string;
  full_content?: string | null;
  relevance_pct: number;
  version?: string;
  edition?: string;
  access_level: string;
}

export interface DetectedTermRef {
  canonical: string;
  expansion: string;
  definition?: string | null;
}

export interface ApprovalStage {
  order: number;
  stage?: string;
  role_name: string;
  department: string;
  reason: string;
  is_mandatory?: boolean;
  required?: boolean;
  condition?: string | null;
}

export interface ApprovalRecommendation {
  rule_number: number;
  doc_type_name: string;
  is_modular?: boolean;
  stages: ApprovalStage[];
  signatory: string;
  notes?: string[] | string | null;
}

export interface QueryRequest {
  query: string;
  request_id?: string;
  user_role?: UserRole;
  top_k?: number;
  session_id?: string | null;
  conversation_id?: string | null;
  history?: Array<{ role: "user" | "assistant"; content: string }> | null;
}

export interface DocumentGenerateResponse {
  project_id: string;
  file_name: string;
  download_url: string;
  note_text: string;
  approval_route: ApprovalStage[];
  created_at: string;
}

export interface QueryResponse {
  request_id: string;
  session_id?: string | null;
  answer: string;
  relevance_score: number;
  detected_terms: DetectedTermRef[];
  sources: SourceRef[];
  approval_recommendation?: ApprovalRecommendation | null;
  zero_hallucination_triggered: boolean;
  needs_clarification: boolean;
  clarification_question?: string | null;
  quick_replies: string[];
  slot_filling_state?: Record<string, any> | null;
  generated_document?: DocumentGenerateResponse | null;
  latency_ms: number;
  t_match_ms?: number;
  t_retriever_ms?: number;
  t_llm_ms?: number;
}

export interface TemplateFieldSchema {
  name: string;
  label: string;
  required?: boolean;
  default?: string;
  description?: string;
}

export interface TemplateModuleInfo {
  module_code: string;
  doc_kind: string;
  title: string;
  reg_number: string;
  version: string;
  file_name: string;
  fields_schema: TemplateFieldSchema[];
}

export interface DocumentGenerateRequest {
  module_code: string;
  executor_name: string;
  executor_department: string;
  signatory_name: string;
  access_level?: string;
  fields: Record<string, any>;
  user_role?: UserRole;
  project_title?: string | null;
}

export interface ProjectCardItem {
  id: string;
  template_id: string;
  module_code?: string | null;
  project_title: string;
  executor_name: string;
  executor_department: string;
  signatory_name: string;
  access_level: string;
  note_text: string;
  filled_fields: Record<string, any>;
  approval_route: ApprovalStage[];
  generated_file_name: string;
  download_url: string;
  status: string;
  created_at: string;
}

export interface ComplianceIssue {
  rule_id: string;
  severity: "critical" | "warning" | "info";
  clause_ref: string;
  title: string;
  description: string;
  recommendation: string;
}

export interface ComplianceCheckResponse {
  file_name: string;
  detected_doc_kind: string;
  is_modular: boolean;
  detected_module_code?: string | null;
  score_pct: number;
  passed: boolean;
  is_compliant: boolean;
  total_checks: number;
  passed_checks: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  issues: ComplianceIssue[];
  approval_recommendation?: ApprovalRecommendation | null;
  fixed_file_url?: string | null;
  checked_at: string;
}

export interface ApprovalCalculateRequest {
  doc_type: string;
  uses_module: boolean;
  involves_infosec_access: boolean;
  involves_it: boolean;
  involves_regional: boolean;
  initiator_department?: string | null;
}

export interface ApprovalCalculateResponse {
  rule_number: number;
  doc_type_name: string;
  is_modular: boolean;
  stages: ApprovalStage[];
  signatory: string;
  notes: string[];
}

export interface ApprovalRuleItem {
  id?: string | null;
  rule_number: number;
  category: string;
  doc_type_name: string;
  is_modular: boolean;
  requires_legal: boolean;
  requires_dou: boolean;
  requires_hr: boolean;
  requires_infosec: string;
  requires_it: string;
  requires_regional: string;
  condition_description?: string | null;
  signatory: string;
  extra_info: Record<string, any>;
}

export interface DocumentVersionItem {
  id: string;
  doc_code: string;
  title: string;
  doc_type: string;
  version: string;
  access_level: string;
  is_active: boolean;
  file_name: string;
  file_size: number;
  sha256?: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface AuditLogItem {
  id: string;
  timestamp: string;
  user_role: string;
  user_name: string;
  action_type: string;
  query_text?: string | null;
  response_summary?: string | null;
  status: string;
  latency_ms: number;
  ip_address?: string | null;
}
