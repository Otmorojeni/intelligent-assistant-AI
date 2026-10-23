from datetime import datetime
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
    top_k: int = 5


class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    answer: str
    relevance_score: float
    detected_terms: List[DetectedTermRef]
    sources: List[SourceRef]
    approval_recommendation: Optional[ApprovalRecommendation] = None
    zero_hallucination_triggered: bool = False
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


class DocumentGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    file_name: str
    download_url: str
    note_text: str
    approval_route: List[ApprovalStage]
    created_at: datetime
