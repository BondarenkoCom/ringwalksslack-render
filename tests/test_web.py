from web import create_app


class FakeSlackClient:
    def verify_signature(self, timestamp, body, signature):
        return True


class FakeXClient:
    def build_oauth2_authorize_url(self):
        return "https://example.com/connect"

    def get_oauth2_status(self):
        return {"connected": True, "username": "tester"}

    def exchange_oauth2_code(self, code, state):
        return {"user": {"username": "tester"}}


class FakeStore:
    def get_daily_usage(self):
        return {
            "search_calls": 3,
            "reply_calls": 1,
            "estimated_cost": 0.08,
        }


class FakeService:
    def __init__(self):
        self.store = FakeStore()
        self.x_client = FakeXClient()

    def get_health_snapshot(self):
        return {
            "ok": True,
            "slack_ready": True,
            "x_oauth2_connected": True,
            "x_username": "tester",
            "poll_interval_seconds": 300,
            "search_calls": 3,
            "reply_calls": 1,
            "estimated_cost": 0.08,
        }

    def get_usage_snapshot(self):
        return {
            "search_calls": 3,
            "reply_calls": 1,
            "estimated_cost": 0.08,
        }

    def poll_once(self):
        return {"status": "ok", "matches": [{"tweet_id": "1"}]}

    def run_action(self, action_id, tweet_id):
        return {"text": "ok"}, 200


def test_slack_command_usage():
    app = create_app(FakeService(), FakeSlackClient())
    client = app.test_client()
    response = client.post("/slack/command", data={"text": "usage"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["response_type"] == "ephemeral"
    assert "Usage today" in payload["text"]
    assert "Estimated cost: $0.08" in payload["text"]


def test_slack_command_health():
    app = create_app(FakeService(), FakeSlackClient())
    client = app.test_client()
    response = client.post("/slack/command", data={"text": "health"})
    assert response.status_code == 200
    payload = response.get_json()
    assert "Bot health: ok" in payload["text"]
    assert "X OAuth2: connected (tester)" in payload["text"]


def test_slack_command_poll():
    app = create_app(FakeService(), FakeSlackClient())
    client = app.test_client()
    response = client.post("/slack/command", data={"text": "poll"})
    assert response.status_code == 200
    payload = response.get_json()
    assert "Poll completed. New Slack alerts: 1" in payload["text"]
