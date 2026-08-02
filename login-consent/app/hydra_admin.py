import httpx


class HydraAdminClient:
    """Thin wrapper around the subset of Hydra's admin API this app needs.

    Path prefix is /admin/oauth2/auth/requests/... (Hydra's v2.x admin API shape).
    """

    def __init__(self, base_url: str, ca_bundle_path: str) -> None:
        self._client = httpx.Client(base_url=base_url, verify=ca_bundle_path)

    def get_login_request(self, challenge: str) -> dict:
        response = self._client.get(
            "/admin/oauth2/auth/requests/login", params={"login_challenge": challenge}
        )
        response.raise_for_status()
        return response.json()

    def accept_login_request(self, challenge: str, subject: str) -> dict:
        response = self._client.put(
            "/admin/oauth2/auth/requests/login/accept",
            params={"login_challenge": challenge},
            json={"subject": subject, "remember": True, "remember_for": 3600},
        )
        response.raise_for_status()
        return response.json()

    def reject_login_request(self, challenge: str) -> dict:
        response = self._client.put(
            "/admin/oauth2/auth/requests/login/reject",
            params={"login_challenge": challenge},
            json={"error": "access_denied", "error_description": "Invalid username or password"},
        )
        response.raise_for_status()
        return response.json()

    def get_consent_request(self, challenge: str) -> dict:
        response = self._client.get(
            "/admin/oauth2/auth/requests/consent", params={"consent_challenge": challenge}
        )
        response.raise_for_status()
        return response.json()

    def accept_consent_request(
        self, challenge: str, grant_scope: list[str], grant_access_token_audience: list[str]
    ) -> dict:
        response = self._client.put(
            "/admin/oauth2/auth/requests/consent/accept",
            params={"consent_challenge": challenge},
            json={
                "grant_scope": grant_scope,
                "grant_access_token_audience": grant_access_token_audience,
                # Lands under claims["ext"]["role"] in the issued JWT (Hydra's fixed
                # nesting for session.access_token) — what service/app/auth.py checks.
                "session": {"access_token": {"role": "admin"}},
            },
        )
        response.raise_for_status()
        return response.json()
