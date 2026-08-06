"""
Authentication, Tenancy, and RBAC Infrastructure.

Provides multi-tenant routing and Role-Based Access Control (RBAC).
Integrates with Enterprise Identity Providers (IdP) like Auth0 or Entra ID via JWT.
"""

import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from urllib.parse import urlsplit
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import jwt
from app.services.tenant_context import bind_authenticated_tenant, bind_provider_access


_DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test"}
_JWKS_CLIENTS: dict[str, jwt.PyJWKClient] = {}


def validate_production_oidc_configuration() -> None:
    """Reject an unsafe or incomplete institutional OIDC configuration at startup."""
    if os.environ.get("IRE_ENV", "development").lower() != "production":
        return
    for name in ("JWT_JWKS_URL", "JWT_ISSUER"):
        value = os.environ.get(name, "").strip()
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise RuntimeError(f"{name} must be a credential-free HTTPS URL in production.")
    if not os.environ.get("JWT_AUDIENCE", "").strip():
        raise RuntimeError("JWT_AUDIENCE must be configured in production.")

class Role(str, Enum):
    TENANT_ADMIN = "tenant_admin"
    STAFF_MEMBER = "staff_member"
    POLICY_EDITOR = "policy_editor"
    APPROVER = "approver"
    AUDITOR = "auditor"
    SUBJECT = "subject"


class ProviderRole(str, Enum):
    PLATFORM_OPERATOR = "platform_operator"
    PLATFORM_AUDITOR = "platform_auditor"

class UserIdentity(BaseModel):
    tenant_id: str
    role: Role
    user_id: str
    subject_id: str | None = None
    domain_ids: list[str] = Field(default_factory=list)
    acting_for: str | None = None
    assignment_expires_at: datetime | None = None


class ProviderIdentity(BaseModel):
    user_id: str
    role: ProviderRole

security = HTTPBearer()


def _jwt_jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    client = _JWKS_CLIENTS.get(jwks_url)
    if client is None:
        client = jwt.PyJWKClient(jwks_url, cache_keys=True, timeout=5)
        _JWKS_CLIENTS[jwks_url] = client
    return client


def _decode_token(token: str) -> dict[str, object]:
    """Validate an institutional OIDC token, or use the explicit dev fallback."""
    jwks_url = os.environ.get("JWT_JWKS_URL")
    if jwks_url:
        issuer = os.environ.get("JWT_ISSUER")
        audience = os.environ.get("JWT_AUDIENCE")
        if not issuer or not audience:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWT_JWKS_URL requires both JWT_ISSUER and JWT_AUDIENCE.",
            )
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
                raise jwt.InvalidAlgorithmError("Unsupported OIDC signing algorithm.")
            signing_key = _jwt_jwks_client(jwks_url).get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=audience,
                issuer=issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired institutional access token.",
            ) from exc

    environment = os.environ.get("IRE_ENV", "development").lower()
    if environment not in _DEVELOPMENT_ENVIRONMENTS:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Production authentication requires JWT_JWKS_URL, JWT_ISSUER, and JWT_AUDIENCE.",
        )

    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY environment variable is missing.")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired development access token.",
        ) from exc


def _decode_provider_token(token: str) -> dict[str, object]:
    """Validate provider-control-plane tokens against a separate trust boundary."""
    jwks_url = os.environ.get("IRE_PROVIDER_JWKS_URL")
    if jwks_url:
        issuer = os.environ.get("IRE_PROVIDER_ISSUER")
        audience = os.environ.get("IRE_PROVIDER_AUDIENCE")
        if not issuer or not audience:
            raise HTTPException(status_code=500, detail="Provider OIDC configuration is incomplete.")
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
                raise jwt.InvalidAlgorithmError("Unsupported OIDC signing algorithm.")
            signing_key = _jwt_jwks_client(jwks_url).get_signing_key_from_jwt(token)
            return jwt.decode(token, signing_key.key, algorithms=[algorithm], audience=audience, issuer=issuer, options={"require": ["exp", "iss", "aud", "sub"]})
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired provider access token.") from exc
    if os.environ.get("IRE_ENV", "development").lower() not in _DEVELOPMENT_ENVIRONMENTS:
        raise HTTPException(status_code=500, detail="Production provider access requires separate provider OIDC configuration.")
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY environment variable is missing.")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired development provider token.") from exc


def get_current_user(auth: HTTPAuthorizationCredentials = Depends(security)) -> UserIdentity:
    """
    Verifies the JWT from the Enterprise Identity Provider (OIDC/SAML).
    Requires a valid JWT signed by the IdP.
    """
    if not auth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authentication Token")
        
    token = auth.credentials
    
    try:
        payload = _decode_token(token)
        tenant_claim = os.environ.get("IRE_TENANT_CLAIM", "tenant_id")
        role_claim = os.environ.get("IRE_ROLE_CLAIM", "role")
        domain_ids_claim = os.environ.get("IRE_DOMAIN_IDS_CLAIM", "domain_ids")
        subject_claim = os.environ.get("IRE_SUBJECT_ID_CLAIM", "sub")
        tenant_id = payload.get(tenant_claim)
        user_id = payload.get("sub")
        domain_ids = payload.get(domain_ids_claim, [])
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError(f"{tenant_claim} must be a non-empty string.")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("sub must be a non-empty string.")
        if (
            not isinstance(domain_ids, list)
            or not all(isinstance(value, str) and value.strip() for value in domain_ids)
            or len(set(domain_ids)) != len(domain_ids)
        ):
            raise ValueError(f"{domain_ids_claim} must be a list of strings.")
        role = Role(str(payload[role_claim]))
        subject_claim_value = payload.get(subject_claim)
        if role == Role.SUBJECT and (
            not isinstance(subject_claim_value, str) or not subject_claim_value.strip()
        ):
            raise ValueError(f"{subject_claim} must be a string for subject identities.")
        delegation_claim = os.environ.get("IRE_DELEGATION_CLAIM", "ire_delegation")
        delegation = payload.get(delegation_claim)
        acting_for: str | None = None
        assignment_expires_at: datetime | None = None
        if delegation is not None:
            if not isinstance(delegation, dict):
                raise ValueError(f"{delegation_claim} must be an object.")
            delegated_role = Role(str(delegation.get("role")))
            delegated_domains = delegation.get("domain_ids")
            expires_at = delegation.get("expires_at")
            acting_for = delegation.get("acting_for")
            if not isinstance(delegated_domains, list) or not all(isinstance(value, str) and value.strip() for value in delegated_domains):
                raise ValueError("Delegated domain assignments must be a list of strings.")
            if not isinstance(expires_at, str) or not isinstance(acting_for, str) or not acting_for.strip():
                raise ValueError("A delegation needs an acting_for reference and expiry.")
            assignment_expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if assignment_expires_at.tzinfo is None:
                raise ValueError("Delegation expiry must include a timezone.")
            assignment_expires_at = assignment_expires_at.astimezone(timezone.utc)
            if assignment_expires_at <= datetime.now(timezone.utc) or assignment_expires_at > datetime.now(timezone.utc) + timedelta(days=90):
                raise ValueError("Delegation is expired or exceeds the maximum 90-day duration.")
            if delegated_role == Role.SUBJECT:
                raise ValueError("Subject access cannot be delegated.")
            role, domain_ids = delegated_role, delegated_domains

        identity = UserIdentity(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            subject_id=subject_claim_value if isinstance(subject_claim_value, str) else None,
            domain_ids=domain_ids,
            acting_for=acting_for,
            assignment_expires_at=assignment_expires_at,
        )
        bind_authenticated_tenant(identity.tenant_id)
        return identity
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is missing required IRE identity claims.",
        )


def require_role(allowed_roles: list[Role]):
    def role_checker(user: UserIdentity = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of roles: {[r.value for r in allowed_roles]}"
            )
        return user
    return role_checker


def get_current_provider_user(auth: HTTPAuthorizationCredentials = Depends(security)) -> ProviderIdentity:
    payload = _decode_provider_token(auth.credentials)
    role_claim = os.environ.get("IRE_PROVIDER_ROLE_CLAIM", "platform_role")
    user_id = payload.get("sub")
    try:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("sub must be a non-empty string.")
        identity = ProviderIdentity(user_id=user_id, role=ProviderRole(str(payload[role_claim])))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Provider token is missing required platform identity claims.") from exc
    bind_provider_access()
    return identity


def require_provider_role(allowed_roles: list[ProviderRole]):
    def role_checker(user: ProviderIdentity = Depends(get_current_provider_user)):
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Provider operation is not permitted for this account.")
        return user
    return role_checker


def ensure_domain_access(user: UserIdentity, domain_id: str) -> None:
    """Enforce domain assignments while retaining tenant-admin break-glass access."""
    if user.role == Role.TENANT_ADMIN:
        return
    if domain_id not in user.domain_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Identity is not assigned to domain {domain_id}.",
        )


def ensure_subject_access(user: UserIdentity, subject_id: str) -> None:
    """Subjects may access only evidence and traces assigned to their identity."""
    if user.role != Role.SUBJECT:
        return
    if not user.subject_id or user.subject_id != subject_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A subject can access only their own institutional record.",
        )
