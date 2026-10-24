from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    db_connected: bool
    ollama_connected: bool
    active_version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_code: str
    document_title: str
    chapter: str
    clause: str
    page_number: int
    quote: str
    full_content: Optional[str] = None
    relevance_pct: float
    version: str
    access_level: str


class DetectedTermRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical: str
    expansion: str
    definition: Optional[str] = None


class ApprovalStage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: int
    role_name: str
    department: str
    reason: str
    is_mandatory: bool = True


class ApprovalRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_number: int
    doc_type_name: str
    stages: List[ApprovalStage]
    signatory: str


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=2, max_length=4000)
    request_id: Optional[str] = None
    user_role: str = "employee"  # employee, dou_specialist, security_auditor
    top_k: int = Field(default=5, ge=1, le=20)
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    session_id: Optional[str] = None
    answer: str
    relevance_score: float
    detected_terms: List[DetectedTermRef]
    sources: List[SourceRef]
    approval_recommendation: Optional[ApprovalRecommendation] = None
    zero_hallucination_triggered: bool = False
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    quick_replies: List[str] = Field(default_factory=list)
    slot_filling_state: Optional[Dict[str, Any]] = None
    generated_document: Optional[Dict[str, Any]] = None
    latency_ms: float
    t_match_ms: float = 0.0
    t_retriever_ms: float = 0.0
    t_llm_ms: float = 0.0


class ApprovalCalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_type: str
    uses_module: bool = True
    involves_infosec_access: bool = False
    involves_it: bool = False
    involves_regional: bool = False
    initiator_department: Optional[str] = None


class ApprovalCalculateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_number: int
    doc_type_name: str
    is_modular: bool
    stages: List[ApprovalStage]
    signatory: str
    notes: List[str] = []


class ApprovalRuleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Optional[str] = None
    rule_number: int
    category: str
    doc_type_name: str
    is_modular: bool
    requires_legal: bool
    requires_dou: bool
    requires_hr: bool
    requires_infosec: str
    requires_it: str
    requires_regional: str
    condition_description: Optional[str] = None
    signatory: str
    extra_info: Dict[str, Any] = Field(default_factory=dict)


class TemplateModuleInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module_code: str
    doc_kind: str
    title: str
    reg_number: str
    version: str
    file_name: str
    fields_schema: List[Dict[str, Any]]


class DocumentGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module_code: str
    executor_name: str = Field(..., min_length=2)
    executor_department: str = Field(..., min_length=2)
    signatory_name: str = Field(..., min_length=2)
    access_level: str = "public"
    fields: Dict[str, Any]
    user_role: str = "employee"
    project_title: Optional[str] = None


class DocumentGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    file_name: str
    download_url: str
    note_text: str
    approval_route: List[ApprovalStage]
    created_at: datetime


class ProjectCardItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    template_id: str
    module_code: Optional[str] = None
    project_title: str
    executor_name: str
    executor_department: str
    signatory_name: str
    access_level: str
    note_text: str
    filled_fields: Dict[str, Any]
    approval_route: List[ApprovalStage]
    generated_file_name: str
    download_url: str
    status: str
    created_at: datetime


class DocumentVersionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    doc_code: str
    title: str
    doc_type: str
    version: str
    access_level: str
    is_active: bool
    file_name: str
    file_size: int
    sha256: Optional[str] = None
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class SwitchVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_code: str = Field(..., description="Document identifier code")
    version: str = Field(..., description="Version identifier to activate")


class AuditLogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    timestamp: datetime
    user_role: str
    user_name: str
    action_type: str
    query_text: Optional[str] = None
    response_summary: Optional[str] = None
    status: str
    latency_ms: float
    ip_address: Optional[str] = None


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = "Пользователь"
    role: str = "employee"
    password: Optional[str] = None


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class ComplianceIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    severity: str  # critical, warning, info
    clause_ref: str
    title: str
    description: str
    recommendation: str


class ComplianceCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: str
    detected_doc_kind: str
    is_modular: bool
    detected_module_code: Optional[str] = None
    score_pct: float
    passed: bool
    is_compliant: bool = False
    total_checks: int
    passed_checks: int
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    issues: List[ComplianceIssue]
    approval_recommendation: Optional[ApprovalRecommendation] = None
    fixed_file_url: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deleted_doc_code: str
    deleted_versions: List[str]
    deleted_count: int
    activated_version: Optional[str] = None

