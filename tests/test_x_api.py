from storage import Store
from x_api import XClient


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.headers = {}
        self.text = str(payload)
        self.content = b"1"

    def json(self):
        return self._payload


def settings():
    return {
        "x": {
            "bearer_token": "bearer-token",
            "oauth2_client_id": "client-id",
            "oauth2_client_secret": "client-secret",
            "oauth2_redirect_uri": "https://example.com/x/callback",
            "oauth2_scopes": ["tweet.read", "tweet.write", "users.read", "offline.access"],
        },
        "limits": {
            "request_timeout_seconds": 5,
            "retry_backoff_seconds": [1],
        },
    }


def test_build_oauth2_authorize_url_stores_pending_state(tmp_path):
    store = Store(tmp_path / "state.db")
    client = XClient(settings(), store)
    url = client.build_oauth2_authorize_url()
    pending = store.get_json_state("x_oauth2_pending")
    assert url.startswith("https://x.com/i/oauth2/authorize?")
    assert "client_id=client-id" in url
    assert "tweet.write" in url
    assert pending["state"]
    assert pending["code_verifier"]


def test_exchange_oauth2_code_stores_token_and_user(tmp_path, monkeypatch):
    store = Store(tmp_path / "state.db")
    client = XClient(settings(), store)
    client.build_oauth2_authorize_url()
    pending = store.get_json_state("x_oauth2_pending")

    def fake_request(method, url, headers=None, params=None, json=None, data=None, auth=None, timeout=None):
        if url.endswith("/oauth2/token"):
            assert method == "POST"
            assert data["grant_type"] == "authorization_code"
            assert data["code"] == "auth-code"
            return FakeResponse(
                200,
                {
                    "token_type": "bearer",
                    "expires_in": 7200,
                    "access_token": "access-123",
                    "scope": "tweet.read tweet.write users.read offline.access",
                    "refresh_token": "refresh-123",
                },
            )
        if url.endswith("/users/me"):
            assert headers["Authorization"] == "Bearer access-123"
            return FakeResponse(
                200,
                {
                    "data": {
                        "id": "42",
                        "username": "fightbotuser",
                    }
                },
            )
        raise AssertionError(url)

    monkeypatch.setattr("x_api.requests.request", fake_request)
    token = client.exchange_oauth2_code("auth-code", pending["state"])
    saved = store.get_json_state("x_oauth2_token")
    assert token["access_token"] == "access-123"
    assert saved["refresh_token"] == "refresh-123"
    assert saved["user"]["username"] == "fightbotuser"


def test_create_post_uses_oauth2_user_token(tmp_path, monkeypatch):
    store = Store(tmp_path / "state.db")
    store.set_json_state(
        "x_oauth2_token",
        {
            "access_token": "access-123",
            "refresh_token": "refresh-123",
            "expires_at": 9999999999,
            "user": {"id": "42", "username": "fightbotuser"},
        },
    )
    client = XClient(settings(), store)

    def fake_request(method, url, headers=None, params=None, json=None, data=None, auth=None, timeout=None):
        assert method == "POST"
        assert url.endswith("/tweets")
        assert headers["Authorization"] == "Bearer access-123"
        assert json["reply"]["in_reply_to_tweet_id"] == "100"
        return FakeResponse(201, {"data": {"id": "200"}})

    monkeypatch.setattr("x_api.requests.request", fake_request)
    data = client.reply_to_tweet("100", "Template A")
    assert data["id"] == "200"
