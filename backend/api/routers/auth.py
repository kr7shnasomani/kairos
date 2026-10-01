"""
Auth router — Supabase Auth JWT exchange and user profile.
"""

import asyncio
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase import create_client

from api.dependencies import CurrentUserDep, SettingsDep, SupabaseDep, _auth_cache_drop, bearer_scheme

log = structlog.get_logger(__name__)

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for JWT")
async def login(payload: LoginRequest, settings: SettingsDep) -> TokenResponse:
    # Use a fresh anon client for sign-in to avoid contaminating the global service-role client session
    auth_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    try:
        result = await asyncio.to_thread(
            lambda: auth_client.auth.sign_in_with_password(
                {"email": payload.email, "password": payload.password}
            )
        )
    except Exception as e:
        # The upstream text distinguishes "no such user" from "wrong password", which lets a caller
        # enumerate accounts. Log it, answer the same thing every time.
        log.info("auth.login_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not result.session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(
        access_token=result.session.access_token,
        refresh_token=result.session.refresh_token,
        user_id=str(result.user.id),
    )


@router.post("/refresh", response_model=TokenResponse, summary="Refresh an expired JWT")
async def refresh(payload: RefreshRequest, settings: SettingsDep) -> TokenResponse:
    auth_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    try:
        result = await asyncio.to_thread(
            lambda: auth_client.auth.refresh_session(payload.refresh_token)
        )
    except Exception as e:
        log.info("auth.refresh_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if not result.session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    return TokenResponse(
        access_token=result.session.access_token,
        refresh_token=result.session.refresh_token,
        user_id=str(result.user.id),
    )


@router.post("/logout", summary="Revoke the caller's Supabase session")
async def logout(
    supabase: SupabaseDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> dict:
    """Best-effort server-side sign-out: deletes the session behind this access token, which also
    kills its refresh token. Before this existed, "sign out" only cleared browser storage, so a
    copied refresh token kept working. Always `ok` once a token is presented — an expired token
    has nothing left to revoke and the client still has to be able to finish signing out."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    _auth_cache_drop(token)  # else the verified-token cache keeps honouring it for up to its TTL
    try:
        # scope="local": this device's session only, so signing out of one browser does not
        # sign the shared demo account out of every other one.
        await asyncio.to_thread(lambda: supabase.auth.admin.sign_out(token, "local"))
    except Exception as e:  # noqa: BLE001 — best effort, the caller is leaving anyway
        log.info("auth.logout_revoke_failed", error=str(e))
    return {"status": "ok"}


@router.get("/me", summary="Get current user profile from JWT claims")
async def get_me(current_user: CurrentUserDep) -> dict:
    return current_user
