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
]
