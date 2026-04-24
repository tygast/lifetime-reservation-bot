"""Authentication services for Life Time member login."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from lifetime_bot.api import API_BASE, SUBSCRIPTION_KEY
from lifetime_bot.errors import LifetimeAPIError
from lifetime_bot.models import SessionTokens

DIRECT_LOGIN_URL = f"{API_BASE}/auth/v2/login"
PROFILE_URL = f"{API_BASE}/user-profile/profile"


@dataclass(frozen=True)
class AuthenticatedSession:
    """HTTP session plus the member tokens minted during login."""

    tokens: SessionTokens
    session: requests.Session


class DirectAPIAuthenticator:
    """Authenticate against Life Time's direct member APIs."""

    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def login(self, username: str, password: str) -> AuthenticatedSession:
        session = requests.Session()
        login_response = session.post(
            DIRECT_LOGIN_URL,
            headers=self._direct_auth_headers(),
            json={"username": username, "password": password},
            timeout=self.timeout,
        )
        payload = self._json_or_error(login_response, context="auth/v2/login")
        if str(payload.get("status", "")) != "0" or payload.get("message") != "Success":
            raise LifetimeAPIError(
                "Direct member login was rejected: "
                f"{payload.get('message') or login_response.text[:300]}"
            )

        auth_token = str(payload.get("token") or "").strip()
        ssoid = str(payload.get("ssoId") or payload.get("ssoid") or "").strip()
        if not auth_token or not ssoid:
            raise LifetimeAPIError(
                "Direct member login did not return the expected token and ssoId"
            )

        profile_response = session.get(
            PROFILE_URL,
            headers=self._direct_auth_headers(auth_token=auth_token, ssoid=ssoid),
            timeout=self.timeout,
        )
        profile_payload = self._json_or_error(
            profile_response, context="user-profile/profile"
        )
        member_details = profile_payload.get("memberDetails") or {}
        member_id = member_details.get("memberId")
        if member_id is None:
            raise LifetimeAPIError(
                "Profile API did not return memberDetails.memberId after login"
            )

        print("Authenticated via direct API login.")
        return AuthenticatedSession(
            tokens=SessionTokens(
                jwe=auth_token,
                profile=str(profile_payload.get("jwt") or ""),
                ssoid=ssoid,
                member_id_override=int(member_id),
            ),
            session=session,
        )

    def _direct_auth_headers(
        self, *, auth_token: str | None = None, ssoid: str | None = None
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
            "Origin": "https://my.lifetime.life",
            "Referer": "https://my.lifetime.life/",
            "User-Agent": "Mozilla/5.0",
        }
        if auth_token:
            headers["Authorization"] = auth_token
            headers["X-LTF-JWE"] = auth_token
        if ssoid:
            headers["X-LTF-SSOID"] = ssoid
        return headers

    def _json_or_error(
        self, response: requests.Response, *, context: str
    ) -> dict[str, Any]:
        if not response.ok:
            raise LifetimeAPIError(
                f"{context} returned {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise LifetimeAPIError(
                f"{context} returned non-JSON response: {response.text[:300]}",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise LifetimeAPIError(
                f"{context} returned unexpected payload: {payload!r}",
                status_code=response.status_code,
            )
        return payload
