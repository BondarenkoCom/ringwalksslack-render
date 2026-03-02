from slack_api import SlackClient


def settings():
    return {
        "slack": {
            "bot_token": "xoxb-test",
            "signing_secret": "secret",
            "channel_id": "C1",
        },
        "limits": {
            "request_timeout_seconds": 5,
            "retry_backoff_seconds": [1],
        },
    }


def test_send_match_includes_actions_block():
    client = SlackClient(settings())
    blocks = client._build_blocks(
        "tweet-1",
        "What time is the main event?",
        "https://x.com/i/web/status/1",
        {"a": "Template A", "b": "Template B"},
        include_actions=True,
    )
    assert any(block["type"] == "actions" for block in blocks)
    actions_block = next(block for block in blocks if block["type"] == "actions")
    assert any(item.get("text", {}).get("text") == "Open X" for item in actions_block["elements"])


def test_update_status_omits_actions_block():
    client = SlackClient(settings())
    blocks = client._build_blocks(
        "tweet-1",
        "What time is the main event?",
        "https://x.com/i/web/status/1",
        None,
        status_text="Ignored in Slack",
        include_actions=False,
    )
    assert all(block["type"] != "actions" for block in blocks)


def test_send_match_includes_warning_text_when_present():
    client = SlackClient(settings())
    blocks = client._build_blocks(
        "tweet-1",
        "What time is the main event?",
        "https://x.com/i/web/status/1",
        {"a": "Template A", "b": "Template B"},
        warning_text="Warning: X API reply is not guaranteed here.",
        include_actions=True,
    )
    context_block = next(block for block in blocks if block["type"] == "context")
    assert any("not guaranteed" in item["text"] for item in context_block["elements"])
