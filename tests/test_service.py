from service import BotService
from storage import Store


class FakeXClient:
    def __init__(self):
        self.replies = []

    def search_recent(self, query, max_results):
        return [
            {"id": "1", "text": "What time is the Haney main event tonight?", "reply_settings": "everyone"},
            {"id": "2", "text": "Haney is ready for tonight", "reply_settings": "everyone"},
        ]

    def reply_to_tweet(self, tweet_id, text):
        self.replies.append((tweet_id, text))
        return {"id": "55"}

    def get_connected_user(self):
        return {"id": "42", "username": "fightbotuser"}


class FakeSlackClient:
    def __init__(self):
        self.sent = []
        self.updated = []
        self.updated_retry = []

    def send_match(self, tweet, reply_templates):
        self.sent.append((tweet, reply_templates))
        return {"channel": "C1", "ts": "123.456"}

    def update_status(self, channel_id, message_ts, tweet, status_text):
        self.updated.append((channel_id, message_ts, tweet["tweet_id"], status_text))
        return {"ok": True}

    def update_match(self, channel_id, message_ts, tweet, reply_templates, status_text):
        self.updated_retry.append(
            (channel_id, message_ts, tweet["tweet_id"], status_text, reply_templates["a"], reply_templates["b"])
        )
        return {"ok": True}


class FailingStore(Store):
    def mark_replied(self, tweet_id, template_key, reply_text, x_reply_id):
        raise RuntimeError("db write failed")


def settings():
    return {
        "search": {
            "max_results": 10,
            "poll_interval_seconds": 300,
        },
        "matcher": {
            "timing_phrases": ["what time", "what time does", "when is", "when does"],
            "fighter_names": ["Haney"],
            "target_terms": ["main event", "ring walk"],
        },
        "reply_templates": {
            "a": "Template A",
            "b": "Template B",
        },
        "limits": {
            "daily_cost_cap_usd": 15,
            "search_request_cost_usd": 0.2,
            "reply_request_cost_usd": 0.3,
            "min_reply_gap_seconds": 0,
        },
        "slack": {
            "bot_token": "x",
            "signing_secret": "y",
            "channel_id": "C1",
        },
    }


def test_poll_once_sends_only_matching_tweet(tmp_path):
    store = Store(tmp_path / "state.db")
    slack_client = FakeSlackClient()
    service = BotService(settings(), store, FakeXClient(), slack_client)
    result = service.poll_once()
    assert result["status"] == "ok"
    assert len(result["matches"]) == 1
    usage = store.get_daily_usage()
    assert usage["search_calls"] == 1
    assert slack_client.sent[0][0]["warning_text"].startswith("Warning: X API may reject this reply")


def test_poll_once_skips_reply_thread_matches(tmp_path):
    store = Store(tmp_path / "state.db")

    class ReplyThreadXClient(FakeXClient):
        def search_recent(self, query, max_results):
            return [
                {
                    "id": "1",
                    "text": "@ufc When is the main event?",
                    "reply_settings": "everyone",
                    "in_reply_to_user_id": "999",
                },
                {
                    "id": "2",
                    "text": "What time is the Haney main event tonight?",
                    "reply_settings": "everyone",
                },
            ]

    slack_client = FakeSlackClient()
    service = BotService(settings(), store, ReplyThreadXClient(), slack_client)
    result = service.poll_once()
    assert result["status"] == "ok"
    assert len(result["matches"]) == 1
    assert result["matches"][0]["tweet_id"] == "2"


def test_poll_once_does_not_warn_when_account_is_mentioned(tmp_path):
    store = Store(tmp_path / "state.db")

    class MentionedXClient(FakeXClient):
        def search_recent(self, query, max_results):
            return [
                {
                    "id": "1",
                    "text": "@fightbotuser what time is the Haney main event tonight?",
                    "reply_settings": "everyone",
                    "entities": {"mentions": [{"username": "fightbotuser"}]},
                    "author_id": "999",
                }
            ]

    slack_client = FakeSlackClient()
    service = BotService(settings(), store, MentionedXClient(), slack_client)
    result = service.poll_once()
    assert result["status"] == "ok"
    assert len(result["matches"]) == 1
    assert slack_client.sent[0][0]["warning_text"] == ""


def test_handle_action_replies_once(tmp_path):
    store = Store(tmp_path / "state.db")
    x_client = FakeXClient()
    slack_client = FakeSlackClient()
    service = BotService(settings(), store, x_client, slack_client)
    service.poll_once()
    result, code = service.handle_action("reply_a", "1")
    assert code == 200
    assert result["text"] == "Reply sent."
    result2, code2 = service.handle_action("reply_a", "1")
    assert code2 == 200
    assert result2["text"] == "Reply already sent."
    assert len(x_client.replies) == 1


def test_ignore_during_replying_is_blocked(tmp_path):
    store = Store(tmp_path / "state.db")
    slack_client = FakeSlackClient()
    service = BotService(settings(), store, FakeXClient(), slack_client)
    service.poll_once()
    assert store.claim_reply("1")
    result, code = service.handle_action("ignore", "1")
    assert code == 200
    assert result["text"] == "Reply is already being processed."
    row = store.get_tweet("1")
    assert row["status"] == "replying"


def test_reply_not_released_after_x_send_if_state_write_fails(tmp_path):
    store = FailingStore(tmp_path / "state.db")
    x_client = FakeXClient()
    slack_client = FakeSlackClient()
    service = BotService(settings(), store, x_client, slack_client)
    service.poll_once()
    try:
        service.handle_action("reply_a", "1")
    except RuntimeError:
        pass
    row = store.get_tweet("1")
    assert row["status"] == "replying"
    result, code = service.handle_action("reply_a", "1")
    assert code == 200
    assert result["text"] == "Tweet is already being processed."
    assert len(x_client.replies) == 1


def test_unknown_action_is_rejected(tmp_path):
    store = Store(tmp_path / "state.db")
    x_client = FakeXClient()
    service = BotService(settings(), store, x_client, FakeSlackClient())
    service.poll_once()
    result, code = service.handle_action("reply_c", "1")
    assert code == 400
    assert result["text"] == "Unknown action."
    assert x_client.replies == []


def test_failed_reply_keeps_buttons_for_retry(tmp_path):
    store = Store(tmp_path / "state.db")
    slack_client = FakeSlackClient()

    class BrokenXClient(FakeXClient):
        def reply_to_tweet(self, tweet_id, text):
            raise RuntimeError("temporary x error")

    service = BotService(settings(), store, BrokenXClient(), slack_client)
    service.poll_once()
    result, code = service.run_action("reply_a", "1")
    assert code == 500
    row = store.get_tweet("1")
    assert row["status"] == "alerted"
    usage = store.get_daily_usage()
    assert usage["reply_calls"] == 1
    assert slack_client.updated_retry
    assert "temporary x error" in slack_client.updated_retry[-1][3]
