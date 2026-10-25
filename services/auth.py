"""Authentication & Role-Based Access Control (RBAC) Service."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional, List
from fastapi import Request, HTTPException, Depends, Header

JWT_SECRET = os.environ.get("JWT_SECRET", "resolvex-enterprise-auth-key-2026-production")
TOKEN_EXPIRY_SECONDS = 86400 * 7  # 7 days


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Generates a PBKDF2-SHA256 salted password hash."""
    if not salt:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return pwd_hash, salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verifies candidate password against stored salt and PBKDF2 hash."""
    pwd_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(pwd_hash, expected_hash)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data_str: str) -> bytes:
    padding = "=" * (4 - len(data_str) % 4) if len(data_str) % 4 else ""
    return base64.urlsafe_b64decode(data_str + padding)


def create_access_token(user: dict, expires_in: int = TOKEN_EXPIRY_SECONDS) -> str:
    """Creates a signed HMAC-SHA256 token encoding user identity and role."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.get("email"),
        "role": user.get("role", "customer"),
        "name": user.get("name", user.get("email")),
        "exp": time.time() + expires_in,
        "iat": time.time(),
    }
    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    msg = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(JWT_SECRET.encode("utf-8"), msg, hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_access_token(token: str) -> Optional[dict]:
    """Validates signature and expiry for signed token."""
    if not token or token.count(".") != 2:
        return None
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        msg = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), msg, hashlib.sha256).digest()
        provided_sig = _b64decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def get_token_from_request(request: Request, authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extracts bearer token from Authorization header, query param, or cookie."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    # Check query param (convenient for SSE or direct links)
    query_token = request.query_params.get("token")
    if query_token:
        return query_token
    # Check custom X-Auth-Token header
    custom_header = request.headers.get("X-Auth-Token")
    if custom_header:
        return custom_header
    return None


def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    """Dependency ensuring caller provides a valid authenticated token."""
    token = get_token_from_request(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Please provide a Bearer token.")
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return payload


def get_optional_user(request: Request, authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Dependency returning authenticated user if token is present, else guest dict."""
    token = get_token_from_request(request, authorization)
    if token:
        payload = verify_access_token(token)
        if payload:
            return payload
    return {"sub": "guest@example.com", "role": "customer", "name": "Guest Customer"}


def require_role(allowed_roles: List[str]):
    """Returns a dependency ensuring caller has one of the specified roles."""
    def _role_checker(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access forbidden: role '{role}' insufficient. Required one of: {allowed_roles}"
            )
        return user
    return _role_checker
