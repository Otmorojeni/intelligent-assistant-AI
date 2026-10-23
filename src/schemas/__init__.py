"""
Pydantic схемы контрактов API.
"""
from src.schemas.api_models import (
    HealthResponse,
    SourceRef,
    DetectedTermRef,
    QueryRequest,
    QueryResponse,
    ApprovalCalculateRequest,
    ApprovalStage,
    ApprovalRecommendation,
    ApprovalCalculateResponse,
    ApprovalRuleItem,
    DocumentGenerateRequest,
    DocumentGenerateResponse,
    TemplateModuleInfo,
    ProjectCardItem,
    DocumentVersionItem,
    AuditLogItem,
    TokenRequest,
    TokenResponse,
)

__all__ = [
    "HealthResponse",
    "SourceRef",
    "DetectedTermRef",
    "QueryRequest",
    "QueryResponse",
    "ApprovalCalculateRequest",
    "ApprovalStage",
    "ApprovalRecommendation",
    "ApprovalCalculateResponse",
    "ApprovalRuleItem",
    "DocumentGenerateRequest",
    "DocumentGenerateResponse",
    "TemplateModuleInfo",
    "ProjectCardItem",
    "DocumentVersionItem",
    "AuditLogItem",
    "TokenRequest",
    "TokenResponse",
]

