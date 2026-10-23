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
    ApprovalCalculateResponse,
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
    "ApprovalCalculateResponse",
    "DocumentGenerateRequest",
    "DocumentGenerateResponse",
    "TemplateModuleInfo",
]
