"""Unit tests for direct API authentication."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from lifetime_bot.auth import DirectAPIAuthenticator
from lifetime_bot.errors import LifetimeAPIError


def _response(
    payload: dict[str, object], *, ok: bool = True, status_code: int = 200, text: str = ""
) -> MagicMock:
    response = MagicMock()
    response.ok = ok
    response.status_code = status_code
    response.text = text or json.dumps(payload)
    response.json.return_value = payload
    return response


class TestDirectAPIAuthenticator:
    def test_login_returns_authenticated_session(self) -> None:
        session = MagicMock()
        session.post.return_value = _response(
            {
                "message": "Success",
                "status": "0",
                "token": "auth-token",
                "ssoId": "sso-id",
            }
        )
        session.get.return_value = _response(
            {
                "jwt": "profile-jwt",
                "memberDetails": {
                    "memberId": 110137193,
                },
                "partyId": 1,
            }
        )

        result = DirectAPIAuthenticator(
            timeout=10.0,
            session_factory=lambda: session,
        ).login("user", "pass")

        assert result.tokens.jwe == "auth-token"
        assert result.tokens.profile == "profile-jwt"
        assert result.tokens.ssoid == "sso-id"
        assert result.tokens.member_id == 110137193
        assert result.session is session
        session.post.assert_called_once()
        session.get.assert_called_once()

    @pytest.mark.parametrize(
        ("login_payload", "profile_payload", "expected"),
        [
            (
                {"message": "Denied", "status": "1", "token": "auth-token", "ssoId": "sso-id"},
                {"jwt": "profile-jwt", "memberDetails": {"memberId": 110137193}},
                "Direct member login was rejected",
            ),
            (
                {"message": "Success", "status": "0", "token": "", "ssoId": "sso-id"},
                {"jwt": "profile-jwt", "memberDetails": {"memberId": 110137193}},
                "expected token and ssoId",
            ),
            (
                {"message": "Success", "status": "0", "token": "auth-token", "ssoId": ""},
                {"jwt": "profile-jwt", "memberDetails": {"memberId": 110137193}},
                "expected token and ssoId",
            ),
            (
                {"message": "Success", "status": "0", "token": "auth-token", "ssoId": "sso-id"},
                {"jwt": "profile-jwt", "memberDetails": {}},
                "memberDetails.memberId",
            ),
        ],
    )
    def test_login_rejects_bad_payloads(
        self,
        login_payload: dict[str, object],
        profile_payload: dict[str, object],
        expected: str,
    ) -> None:
        session = MagicMock()
        session.post.return_value = _response(login_payload)
        session.get.return_value = _response(profile_payload)

        with pytest.raises(LifetimeAPIError, match=expected):
            DirectAPIAuthenticator(
                timeout=10.0,
                session_factory=lambda: session,
            ).login("user", "pass")

    def test_login_reports_http_error_before_json_parse(self) -> None:
        session = MagicMock()
        response = MagicMock()
        response.ok = False
        response.status_code = 503
        response.text = "<html>upstream error</html>"
        response.json.side_effect = ValueError("no json")
        session.post.return_value = response

        with pytest.raises(LifetimeAPIError, match=r"auth/v2/login returned 503"):
            DirectAPIAuthenticator(
                timeout=10.0,
                session_factory=lambda: session,
            ).login("user", "pass")
