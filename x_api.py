import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import requests


class XApiError(Exception):
    pass


class XClient:
    def __init__(self, settings, store):
        self.settings = settings
        self.store = store
        self.base_url = "https://api.x.com/2"
        self.oauth2_authorize_url = "https://x.com/i/oauth2/authorize"
        self.oauth2_token_url = "https://api.x.com/2/oauth2/token"
        x = settings["x"]
        self.bearer_token = x["bearer_token"]
        self.oauth2_client_id = x.get("oauth2_client_id", "")
        self.oauth2_client_secret = x.get("oauth2_client_secret", "")
        self.oauth2_redirect_uri = x.get("oauth2_redirect_uri", "")
        self.oauth2_scopes = x.get("oauth2_scopes", [])
        self.backoff_seconds = settings["limits"]["retry_backoff_seconds"]
        self.timeout = settings["limits"].get("request_timeout_seconds", 30)

    def search_recent(self, query, max_results):
        data = self._request(
            "GET",
            f"{self.base_url}/tweets/search/recent",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "application/json",
                "User-Agent": "section9-boxing-bot/1.0",
            },
            params={
                "query": query,
                "max_results": max_results,
                "tweet.fields": "author_id,conversation_id,created_at,entities,in_reply_to_user_id,lang,reply_settings",
            },
        )
        return data.get("data", [])

    def reply_to_tweet(self, tweet_id, text):
        return self.create_post(
            text,
            in_reply_to_tweet_id=str(tweet_id),
        )

    def create_post(self, text, in_reply_to_tweet_id=None):
        payload = {"text": text}
        if in_reply_to_tweet_id:
            payload["reply"] = {
                "in_reply_to_tweet_id": str(in_reply_to_tweet_id),
            }
        if not self.oauth2_configured():
            raise XApiError("X OAuth2 client credentials are missing.")
        return self._create_post_oauth2(payload)

    def oauth2_configured(self):
        return all(
            [
                self.oauth2_client_id,
                self.oauth2_client_secret,
                self.oauth2_redirect_uri,
            ]
        )

    def oauth2_connected(self):
        token = self.store.get_json_state("x_oauth2_token")
        return bool(token and token.get("access_token"))

    def get_oauth2_status(self):
        pending = self.store.get_json_state("x_oauth2_pending", {})
        token = self.store.get_json_state("x_oauth2_token", {})
        expires_at = token.get("expires_at")
        expires_in = None
        if expires_at:
            expires_in = max(0, int(float(expires_at) - time.time()))
        user = token.get("user", {})
        return {
            "configured": self.oauth2_configured(),
            "connected": bool(token.get("access_token")),
            "pending": bool(pending),
            "redirect_uri": self.oauth2_redirect_uri,
            "scopes": self.oauth2_scopes,
            "expires_in_seconds": expires_in,
            "username": user.get("username", ""),
            "user_id": user.get("id", ""),
        }

    def get_connected_user(self):
        token = self.store.get_json_state("x_oauth2_token", {})
        return token.get("user", {}) if token else {}

    def build_oauth2_authorize_url(self):
        if not self.oauth2_configured():
            raise XApiError("X OAuth2 client credentials are missing.")
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(72)[:96]
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("utf-8")).digest()
        ).rstrip(b"=").decode("utf-8")
        self.store.set_json_state(
            "x_oauth2_pending",
            {
                "state": state,
                "code_verifier": verifier,
                "created_at": int(time.time()),
            },
        )
        return self.oauth2_authorize_url + "?" + urlencode(
            {
                "response_type": "code",
                "client_id": self.oauth2_client_id,
                "redirect_uri": self.oauth2_redirect_uri,
                "scope": " ".join(self.oauth2_scopes),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )

    def exchange_oauth2_code(self, code, state):
        pending = self.store.get_json_state("x_oauth2_pending")
        if not pending:
            raise XApiError("X OAuth2 authorization was not started.")
        if pending.get("state") != state:
            raise XApiError("X OAuth2 state mismatch.")
        if int(time.time()) - int(pending.get("created_at", 0)) > 900:
            self.store.delete_state("x_oauth2_pending")
            raise XApiError("X OAuth2 authorization expired. Start again.")
        data = self._oauth2_token_request(
            {
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.oauth2_redirect_uri,
                "code_verifier": pending["code_verifier"],
            }
        )
        token = self._normalize_token(data)
        user = self._oauth2_get_user(token["access_token"])
        token["user"] = user
        self.store.set_json_state("x_oauth2_token", token)
        self.store.delete_state("x_oauth2_pending")
        return token

    def refresh_oauth2_token(self):
        token = self.store.get_json_state("x_oauth2_token")
        if not token:
            raise XApiError("X OAuth2 token is missing.")
        refresh_token = token.get("refresh_token", "")
        if not refresh_token:
            raise XApiError("X OAuth2 refresh token is missing.")
        data = self._oauth2_token_request(
            {
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        )
        refreshed = self._normalize_token(data)
        if not refreshed.get("refresh_token"):
            refreshed["refresh_token"] = refresh_token
        refreshed["user"] = token.get("user", {})
        self.store.set_json_state("x_oauth2_token", refreshed)
        return refreshed

    def _create_post_oauth2(self, payload):
        access_token = self._oauth2_access_token()
        data = self._request(
            "POST",
            f"{self.base_url}/tweets",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": "section9-boxing-bot/1.0",
            },
            json=payload,
        )
        return data.get("data", {})

    def _oauth2_access_token(self):
        token = self.store.get_json_state("x_oauth2_token")
        if not token:
            raise XApiError("X OAuth2 user token is missing. Open /x/connect first.")
        expires_at = float(token.get("expires_at", 0) or 0)
        if expires_at and expires_at <= time.time() + 60:
            token = self.refresh_oauth2_token()
        access_token = token.get("access_token", "")
        if not access_token:
            raise XApiError("X OAuth2 access token is missing.")
        return access_token

    def _oauth2_get_user(self, access_token):
        data = self._request(
            "GET",
            f"{self.base_url}/users/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": "section9-boxing-bot/1.0",
            },
            params={
                "user.fields": "username",
            },
        )
        return data.get("data", {})

    def _oauth2_token_request(self, form_data):
        if not self.oauth2_configured():
            raise XApiError("X OAuth2 client credentials are missing.")
        auth_value = base64.b64encode(
            f"{self.oauth2_client_id}:{self.oauth2_client_secret}".encode("utf-8")
        ).decode("utf-8")
        return self._request(
            "POST",
            self.oauth2_token_url,
            headers={
                "Authorization": f"Basic {auth_value}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "section9-boxing-bot/1.0",
            },
            data=form_data,
        )

    def _normalize_token(self, data):
        expires_in = int(data.get("expires_in", 0) or 0)
        token = {
            "access_token": data.get("access_token", ""),
            "token_type": data.get("token_type", ""),
            "scope": data.get("scope", ""),
            "refresh_token": data.get("refresh_token", ""),
            "expires_in": expires_in,
            "expires_at": int(time.time()) + expires_in if expires_in else 0,
            "created_at": int(time.time()),
        }
        if not token["access_token"]:
            raise XApiError("X OAuth2 token response did not contain access_token.")
        return token

    def _request(
        self,
        method,
        url,
        headers=None,
        params=None,
        json=None,
        data=None,
        auth=None,
    ):
        last_error = None
        for attempt in range(len(self.backoff_seconds) + 1):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                    auth=auth,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= len(self.backoff_seconds):
                    raise XApiError(str(exc)) from exc
                time.sleep(self.backoff_seconds[attempt])
                continue

            if 200 <= response.status_code < 300:
                if not response.content:
                    return {}
                return response.json()

            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt >= len(self.backoff_seconds):
                    raise XApiError(self._error_text(response))
                time.sleep(self._sleep_seconds(response, attempt))
                continue

            raise XApiError(self._error_text(response))

        raise XApiError(str(last_error or "request failed"))

    def _sleep_seconds(self, response, attempt):
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return max(1, int(retry_after))
            except ValueError:
                pass
        reset = response.headers.get("x-rate-limit-reset")
        if reset:
            try:
                return max(1, int(reset) - int(time.time()))
            except ValueError:
                pass
        return self.backoff_seconds[attempt]

    def _error_text(self, response):
        try:
            data = response.json()
            if isinstance(data, dict):
                return data.get("detail") or data.get("title") or str(data)
        except Exception:
            pass
        return f"{response.status_code}: {response.text[:500]}"
