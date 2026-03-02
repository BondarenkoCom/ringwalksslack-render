from storage import Store


def test_store_tracks_usage_and_tweet_states(tmp_path):
    store = Store(tmp_path / "state.db")
    store.save_pending_tweet("1", "hello", "https://x.com/i/web/status/1")
    assert store.should_skip("1")
    store.mark_alerted("1", "C1", "123.456")
    assert store.should_skip("1")
    assert store.claim_reply("1")
    store.release_reply("1")
    assert store.claim_reply("1")
    store.mark_replied("1", "a", "reply text", "999")
    row = store.get_tweet("1")
    assert row["status"] == "replied"
    store.add_search_call(0.5)
    store.add_reply_call(0.25)
    usage = store.get_daily_usage()
    assert usage["search_calls"] == 1
    assert usage["reply_calls"] == 1
    assert usage["estimated_cost"] == 0.75


def test_claim_pending_alert_is_atomic(tmp_path):
    store = Store(tmp_path / "state.db")
    assert store.claim_pending_alert("1", "hello", "https://x.com/i/web/status/1")
    assert not store.claim_pending_alert("1", "hello", "https://x.com/i/web/status/1")
    row = store.get_tweet("1")
    assert row["status"] == "pending_alert"
    assert store.should_skip("1")
    store.drop_pending_alert("1")
    assert store.get_tweet("1") is None


def test_reply_wait_seconds(tmp_path):
    store = Store(tmp_path / "state.db")
    store.save_pending_tweet("1", "hello", "https://x.com/i/web/status/1")
    store.mark_alerted("1", "C1", "1")
    assert store.claim_reply("1")
    store.mark_replied("1", "a", "reply", "2")
    assert store.reply_wait_seconds(30) > 0


def test_claim_reply_slot_enforces_gap_and_releases(tmp_path):
    store = Store(tmp_path / "state.db")
    ok, wait = store.claim_reply_slot(30)
    assert ok
    assert wait == 0
    ok2, wait2 = store.claim_reply_slot(30)
    assert not ok2
    assert wait2 > 0
    store.release_reply_slot()
    store.set_state("last_reply_at", "0")
    ok3, wait3 = store.claim_reply_slot(30)
    assert ok3
    assert wait3 == 0


def test_store_json_state_roundtrip(tmp_path):
    store = Store(tmp_path / "state.db")
    payload = {"state": "abc", "code_verifier": "xyz"}
    store.set_json_state("x_oauth2_pending", payload)
    assert store.get_json_state("x_oauth2_pending") == payload
    store.delete_state("x_oauth2_pending")
    assert store.get_json_state("x_oauth2_pending") is None
