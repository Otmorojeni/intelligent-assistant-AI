"""Security, Role-Based Access Control (RBAC), and Audit Trail for CDO AI Assistant.

Features:
- Role definitions: employee, dou_specialist, security_auditor, admin.
- Document access levels: public, dsp, confidential, secret.
- Role-to-document access matrix enforcement.
- JWT token creation and verification with configurable expiry and secret.
- Header-based user context extraction (X-User-Role, X-User-Name, Authorization Bearer).
- FastAPI role-based access dependency (require_role) with automated audit logging on 403 Forbidden.
- Prompt injection & malicious query detection guards.
- Structured PostgreSQL audit trail logging (audit_logs table).
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import unicodedata
import uuid

from fastapi import Depends, Header, HTTPException, Request, status
import jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.database import get_db
from src.db.models import AuditLog

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """Authoritative user roles defined in Section 6 RBAC specification."""
    EMPLOYEE = "employee"
    DOU_SPECIALIST = "dou_specialist"
    SECURITY_AUDITOR = "security_auditor"
    ADMIN = "admin"


class AccessLevel(str, Enum):
    """Document confidentiality and distribution classification levels."""
    PUBLIC = "public"
    DSP = "dsp"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


# Mapping of what roles can access what document classification levels
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    UserRole.EMPLOYEE.value: {AccessLevel.PUBLIC.value},
    UserRole.DOU_SPECIALIST.value: {
        AccessLevel.PUBLIC.value,
        AccessLevel.DSP.value,
    },
    UserRole.SECURITY_AUDITOR.value: {
        AccessLevel.PUBLIC.value,
        AccessLevel.DSP.value,
        AccessLevel.CONFIDENTIAL.value,
    },
    UserRole.ADMIN.value: {
        AccessLevel.PUBLIC.value,
        AccessLevel.DSP.value,
        AccessLevel.CONFIDENTIAL.value,
        AccessLevel.SECRET.value,
    },
}

# Synonyms and aliases mapping to canonical roles
ROLE_ALIASES: Dict[str, str] = {
    "user": UserRole.EMPLOYEE.value,
    "employee": UserRole.EMPLOYEE.value,
    "сотрудник": UserRole.EMPLOYEE.value,
    "специалист": UserRole.EMPLOYEE.value,
    "specialist": UserRole.DOU_SPECIALIST.value,
    "dou_specialist": UserRole.DOU_SPECIALIST.value,
    "специалист_доу": UserRole.DOU_SPECIALIST.value,
    "специалист доу": UserRole.DOU_SPECIALIST.value,
    "auditor": UserRole.SECURITY_AUDITOR.value,
    "security_auditor": UserRole.SECURITY_AUDITOR.value,
    "аудитор": UserRole.SECURITY_AUDITOR.value,
    "аудитор_иб": UserRole.SECURITY_AUDITOR.value,
    "аудитор иб": UserRole.SECURITY_AUDITOR.value,
    "admin": UserRole.ADMIN.value,
    "administrator": UserRole.ADMIN.value,
    "администратор": UserRole.ADMIN.value,
}


def normalize_role(role_name: Optional[str]) -> str:
    """Normalize input role string to canonical UserRole enum value, defaulting to 'employee'."""
    if not role_name:
        return UserRole.EMPLOYEE.value
    clean = role_name.strip().lower()
    return ROLE_ALIASES.get(clean, UserRole.EMPLOYEE.value)


def check_document_access(user_role: str, doc_access_level: str) -> bool:
    """Check whether a given user role has permission to access a document of given access level."""
    norm_role = normalize_role(user_role)
    allowed = ROLE_PERMISSIONS.get(norm_role, {AccessLevel.PUBLIC.value})
    target_level = (doc_access_level or AccessLevel.PUBLIC.value).strip().lower()
    return target_level in allowed


def get_role_access_levels(user_role: str) -> List[str]:
    """Return sorted list of document access levels accessible by a role."""
    norm_role = normalize_role(user_role)
    allowed = ROLE_PERMISSIONS.get(norm_role, {AccessLevel.PUBLIC.value})
    return sorted(list(allowed))


class UserContext(BaseModel):
    """Authenticated user context containing username and normalized role."""
    username: str = "Пользователь"
    role: str = UserRole.EMPLOYEE.value


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate signed JWT access token containing user identity and role."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    secret = settings.SECRET_KEY or "cdo-assistant-super-secret-key-hackathon-2026"
    return jwt.encode(to_encode, secret, algorithm=settings.ALGORITHM)


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token, returning its payload if valid."""
    secret = settings.SECRET_KEY or "cdo-assistant-super-secret-key-hackathon-2026"
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.ALGORITHM])
        return payload
    except Exception as e:
        logger.debug(f"JWT verification failed: {e}")
        return None


async def get_current_user(
    request: Request,
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_name: Optional[str] = Header(None, alias="X-User-Name"),
    authorization: Optional[str] = Header(None),
) -> UserContext:
    """Fast authentication resolver: checks Bearer JWT, X-User-Role header (non-admin), or defaults to employee."""
    # 1. Check Bearer JWT token — if provided, it MUST be valid (never fall back to plaintext headers)
    if authorization:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format. Expected 'Bearer <token>'.",
            )
        token = authorization.split(" ", 1)[1].strip()
        payload = verify_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Bearer JWT token.",
            )
        role = payload.get("role") or payload.get("user_role") or "employee"
        username = payload.get("sub") or payload.get("username") or payload.get("user_name") or "Пользователь"
        return UserContext(username=username, role=normalize_role(role))

    # 2. Check X-User-Role header — admin privileges MUST NEVER be granted via unauthenticated plaintext header
    if x_user_role:
        norm_role = normalize_role(x_user_role)
        if norm_role == UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin role requires signed Bearer JWT authentication.",
            )
        return UserContext(
            username=x_user_name or "Пользователь",
            role=norm_role,
        )

    # 3. Default to employee
    return UserContext(
        username=x_user_name or "Пользователь",
        role=UserRole.EMPLOYEE.value,
    )


async def log_audit_event(
    session: AsyncSession,
    user_role: str,
    user_name: str = "Пользователь",
    action_type: str = "query",
    query_text: Optional[str] = None,
    response_summary: Optional[str] = None,
    status: str = "success",
    latency_ms: float = 0.0,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Persist structured audit trail record directly to audit_logs PostgreSQL table."""
    try:
        audit = AuditLog(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            user_role=normalize_role(user_role),
            user_name=user_name,
            action_type=action_type,
            query_text=query_text,
            response_summary=response_summary[:1000] if response_summary else None,
            status=status,
            latency_ms=round(latency_ms, 2),
            ip_address=ip_address,
        )
        session.add(audit)
        await session.flush()
        return audit
    except Exception as e:
        logger.error(f"Failed to persist audit log: {e}")
        raise


def require_role(allowed_roles: Union[List[str], Set[str]]):
    """FastAPI dependency factory enforcing that caller role is in allowed_roles.
    
    If forbidden, immediately logs security violation to audit_logs in PostgreSQL and raises HTTP 403.
    """
    normalized_allowed = {normalize_role(r) for r in allowed_roles}

    async def role_checker(
        request: Request,
        current_user: UserContext = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> UserContext:
        if current_user.role not in normalized_allowed:
            client_ip = request.client.host if request.client else None
            try:
                await log_audit_event(
                    session=session,
                    user_role=current_user.role,
                    user_name=current_user.username,
                    action_type="access_denied",
                    query_text=f"Unauthorized access attempt to {request.url.path} [{request.method}]",
                    response_summary=f"Forbidden: role '{current_user.role}' required one of {sorted(list(normalized_allowed))}",
                    status="forbidden",
                    latency_ms=0.0,
                    ip_address=client_ip,
                )
                await session.commit()
            except Exception as audit_err:
                logger.error(f"Failed to record access_denied audit event: {audit_err}")
                await session.rollback()

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{current_user.role}' lacks permission for this operation. Required: {sorted(list(normalized_allowed))}",
            )
        return current_user

    return role_checker


# Prompt Injection and Malicious Input Guard Patterns
PROMPT_INJECTION_PATTERNS = [
    # English jailbreak & override
    r"(?i)\b(?:ignore|disregard|forget|bypass|override)\b.*?\b(?:previous|prior|above|all)\b.*?\b(?:instructions|rules|prompts|directives)\b",
    r"(?i)\b(?:system\s+prompt|reveal\s+(?:system\s+)?prompt|show\s+system\s+prompt|print\s+system\s+instructions)\b",
    r"(?i)\b(?:act\s+as|pretend\s+to\s+be|you\s+are\s+now)\b.*?\b(?:dan|jailbreak|developer\s+mode|unrestricted)\b",
    # Russian jailbreak & override (singular, plural/polite imperatives, and infinitives)
    r"(?i)\b(?:про)?(?:игнорируй(?:те)?|забудь(?:те)?|отмени(?:те)?|сбрось(?:те)?|обойти|обойди(?:те)?|не\s+учитывай(?:те)?)\b.*?\b(?:все|предыдущие|ранее\s+данные)?\b.*?\b(?:инструкции|правила|указания|промпты|ограничения)\b",
    r"(?i)\b(?:покажи(?:те)?|раскрой(?:те)?|выведи(?:те)?|напечатай(?:те)?)\b.*?\b(?:системный\s+промпт|системную\s+инструкцию|скрытые\s+инструкции|внутренние\s+правила\s+модели|исходный\s+промпт)\b",
    r"(?i)\b(?:ты\s+теперь|вы\s+теперь|действуй(?:те)?\s+как|притворись|притворитесь|ответь(?:те)?)\b.*?\b(?:dan|взлом|режим\s+разработчика|без\s+ограничений)\b",
    # Script / HTML injection
    r"(?i)<\s*(?:script|iframe|svg|object|embed|style)\b",
    # Shell / SQL injection markers
    r"(?i)(?:;\s*drop\s+table|--\s*$|union\s+select\s+)",
]

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\u00ad\x00-\x08\x0b\x0c\x0e-\x1f]")


def _strip_invisible_chars(text: str) -> str:
    """Normalize NFKC and strip zero-width / formatting obfuscation characters."""
    normalized = unicodedata.normalize("NFKC", text)
    cleaned = _ZERO_WIDTH_RE.sub("", normalized)
    return "".join(ch for ch in cleaned if unicodedata.category(ch) != "Cf")


def detect_prompt_injection(query: str) -> Tuple[bool, Optional[str]]:
    """Detect whether user query contains malicious prompt injection or system override attempts."""
    if not query:
        return False, None

    normalized_query = _strip_invisible_chars(query)
    for pattern in PROMPT_INJECTION_PATTERNS:
        match = re.search(pattern, normalized_query)
        if match:
            return True, f"Matched malicious pattern: {match.group(0)}"

    return False, None


def sanitize_query(query: str) -> str:
    """Sanitize query string by stripping null/invisible bytes and normalizing whitespace."""
    if not query:
        return ""
    clean = _strip_invisible_chars(query).replace("\r", " ").strip()
    return re.sub(r"\s+", " ", clean)
