"""
JWT authentication dependency for FastAPI.

Modes (auto-detected from env vars, in priority order):
  1. RS256/JWKS  — JWT_JWKS_URL set  (Cognito, Auth0, Okta)
  2. HS256       — JWT_SECRET set    (dev / internal shared secret)
  3. Dev mode    — neither set       — returns anonymous superuser, no HTTP error

Required JWT claims: sub (user_id), email (optional, falls back to sub).
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwk, jwt

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_JWKS_URL = os.getenv("JWT_JWKS_URL", "")
JWT_ISSUER = os.getenv("JWT_ISSUER", "")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "")

_bearer = HTTPBearer(auto_error=False)

# JWKS cache: avoid fetching on every request
_jwks_cache: dict = {"keys": [], "fetched_at": 0.0}
_JWKS_TTL = 3600  # re-fetch after 1 hour


@dataclass
class AuthUser:
    user_id: str
    email: str


def _get_jwks() -> dict:
    now = time.time()
    if now - _jwks_cache["fetched_at"] < _JWKS_TTL and _jwks_cache["keys"]:
        return _jwks_cache
    try:
        resp = requests.get(JWT_JWKS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        _jwks_cache.update({"keys": data.get("keys", []), "fetched_at": now})
        return _jwks_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from {JWT_JWKS_URL}: {e}")
        if _jwks_cache["keys"]:
            return _jwks_cache  # serve stale on transient errors
        raise HTTPException(status_code=503, detail="Auth service unavailable.")


def _decode_rs256(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    jwks = _get_jwks()
    key_data = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
    if key_data is None:
        # Retry once — key may have rotated
        _jwks_cache["fetched_at"] = 0.0
        jwks = _get_jwks()
        key_data = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
    if key_data is None:
        raise JWTError(f"No public key found for kid={kid!r}")
    public_key = jwk.construct(key_data)
    options: dict = {"verify_aud": bool(JWT_AUDIENCE)}
    return jwt.decode(
        token,
        public_key.to_dict(),
        algorithms=["RS256"],
        audience=JWT_AUDIENCE or None,
        issuer=JWT_ISSUER or None,
        options=options,
    )


def _decode_hs256(token: str) -> dict:
    options: dict = {"verify_aud": bool(JWT_AUDIENCE)}
    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=["HS256"],
        audience=JWT_AUDIENCE or None,
        issuer=JWT_ISSUER or None,
        options=options,
    )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> AuthUser:
    # Dev mode: no auth configured → anonymous superuser
    if not JWT_SECRET and not JWT_JWKS_URL:
        return AuthUser(user_id="anonymous", email="anonymous@local")

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header required.")

    token = credentials.credentials
    try:
        if JWT_JWKS_URL:
            payload = _decode_rs256(token)
        else:
            payload = _decode_hs256(token)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim.")

    email: str = payload.get("email") or payload.get("username") or user_id
    return AuthUser(user_id=user_id, email=email)
