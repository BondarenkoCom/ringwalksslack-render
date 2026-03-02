from config import has_slack_credentials
from matcher import build_query, build_tweet_url, matches_tweet


class BotService:
    def __init__(self, settings, store, x_client, slack_client):
        self.settings = settings
        self.store = store
        self.x_client = x_client
        self.slack_client = slack_client

    def preview_search(self):
        query = build_query(self.settings)
        tweets = self.x_client.search_recent(query, self.settings["search"]["max_results"])
        matches = []
        for tweet in tweets:
            text = tweet.get("text", "")
            if not matches_tweet(text, self.settings):
                continue
            assessment = self.assess_replyability(tweet)
            if assessment["blocked"]:
                continue
            matches.append(
                {
                    "id": tweet["id"],
                    "text": text,
                    "url": build_tweet_url(tweet["id"]),
                    "warning_text": assessment["warning_text"],
                }
            )
        return {
            "query": query,
            "fetched": len(tweets),
            "matches": matches,
        }

    def get_health_snapshot(self):
        usage = self.store.get_daily_usage()
        x_status = self.x_client.get_oauth2_status()
        return {
            "ok": True,
            "slack_ready": self.slack_client.ready(),
            "x_oauth2_connected": x_status.get("connected", False),
            "x_username": x_status.get("username", ""),
            "poll_interval_seconds": self.settings["search"]["poll_interval_seconds"],
            "search_calls": usage["search_calls"],
            "reply_calls": usage["reply_calls"],
            "estimated_cost": usage["estimated_cost"],
        }

    def get_usage_snapshot(self):
        return self.store.get_daily_usage()

    def reply_enabled(self):
        checker = getattr(self.x_client, "oauth2_configured", None)
        if not callable(checker):
            return False
        return bool(checker())

    def poll_once(self):
        if not has_slack_credentials(self.settings):
            raise RuntimeError("Slack credentials are missing")
        search_cost = self.settings["limits"]["search_request_cost_usd"]
        cap = self.settings["limits"]["daily_cost_cap_usd"]
        if self.store.will_exceed_cap(cap, search_cost):
            return {
                "status": "cost_cap_reached",
                "matches": [],
            }
        query = build_query(self.settings)
        self.store.add_search_call(search_cost)
        tweets = self.x_client.search_recent(query, self.settings["search"]["max_results"])
        sent = []
        for tweet in tweets:
            text = tweet.get("text", "")
            tweet_id = str(tweet["id"])
            if not matches_tweet(text, self.settings):
                continue
            assessment = self.assess_replyability(tweet)
            if assessment["blocked"]:
                continue
            tweet_url = build_tweet_url(tweet_id)
            if not self.store.claim_pending_alert(tweet_id, text, tweet_url, assessment["warning_text"]):
                continue
            try:
                sent_msg = self.slack_client.send_match(
                    {
                        "id": tweet_id,
                        "text": text,
                        "url": tweet_url,
                        "warning_text": assessment["warning_text"],
                    },
                    self.settings["reply_templates"] if self.reply_enabled() else None,
                )
                self.store.mark_alerted(tweet_id, sent_msg["channel"], sent_msg["ts"])
                sent.append({"tweet_id": tweet_id, "slack_ts": sent_msg["ts"]})
            except Exception:
                self.store.drop_pending_alert(tweet_id)
                raise
        return {
            "status": "ok",
            "matches": sent,
        }

    def is_replyable_match(self, tweet):
        return not self.assess_replyability(tweet)["blocked"]

    def assess_replyability(self, tweet):
        if tweet.get("in_reply_to_user_id"):
            return {
                "blocked": True,
                "warning_text": "Warning: skipped because this match is already a reply in another conversation.",
            }
        reply_settings = (tweet.get("reply_settings") or "").strip().lower()
        if reply_settings and reply_settings != "everyone":
            return {
                "blocked": True,
                "warning_text": f"Warning: skipped because the author limits replies with reply_settings={reply_settings}.",
            }
        warning_text = self.build_reply_warning(tweet)
        return {
            "blocked": False,
            "warning_text": warning_text,
        }

    def build_reply_warning(self, tweet):
        if not self.reply_enabled():
            return "Detection-only mode: use Open X to review or reply manually in X."
        user = self.x_client.get_connected_user()
        username = (user.get("username") or "").strip().lower()
        user_id = str(user.get("id") or "").strip()
        if not username:
            return "Warning: X OAuth2 user is not connected yet, so API replyability is not verified for this tweet."
        author_id = str(tweet.get("author_id") or "").strip()
        if user_id and author_id and author_id == user_id:
            return ""
        mentions = tweet.get("entities", {}).get("mentions", [])
        mentioned_usernames = {
            (item.get("username") or "").strip().lower()
            for item in mentions
            if isinstance(item, dict)
        }
        if username in mentioned_usernames:
            return ""
        text = (tweet.get("text") or "").lower()
        if f"@{username}" in text:
            return ""
        return (
            "Warning: X API may reject this reply even if the UI allows it. "
            "This account is not mentioned in the tweet, and X may require a prior conversation relationship."
        )

    def handle_action(self, action_id, tweet_id):
        if action_id not in {"reply_a", "reply_b", "ignore"}:
            return {"text": "Unknown action."}, 400
        if action_id in {"reply_a", "reply_b"} and not self.reply_enabled():
            return {"text": "Reply actions are disabled in detection-only mode."}, 200
        tweet = self.store.get_tweet(tweet_id)
        if not tweet:
            return {"text": "Tweet not found."}, 404
        if action_id == "ignore":
            if tweet["status"] == "replying":
                return {"text": "Reply is already being processed."}, 200
            if tweet["status"] == "replied":
                return {"text": "Reply already sent."}, 200
            self.store.mark_ignored(tweet_id)
            updated = self.store.get_tweet(tweet_id)
            self.slack_client.update_status(
                updated["slack_channel"],
                updated["slack_ts"],
                updated,
                "Ignored in Slack",
            )
            return {"text": "Ignored."}, 200
        if tweet["status"] == "replied":
            return {"text": "Reply already sent."}, 200
        if not self.store.claim_reply(tweet_id):
            current = self.store.get_tweet(tweet_id)
            if current and current["status"] == "replied":
                return {"text": "Reply already sent."}, 200
            if current and current["status"] == "ignored":
                return {"text": "Tweet is already ignored."}, 200
            return {"text": "Tweet is already being processed."}, 200
        reply_sent = False
        slot_claimed = False
        try:
            slot_claimed, wait_seconds = self.store.claim_reply_slot(
                self.settings["limits"]["min_reply_gap_seconds"]
            )
            if not slot_claimed:
                self.store.release_reply(tweet_id)
                updated = self.store.get_tweet(tweet_id)
                self.slack_client.update_match(
                    updated["slack_channel"],
                    updated["slack_ts"],
                    updated,
                    self.settings["reply_templates"],
                    f"Reply rate limit active. Try again in {wait_seconds}s.",
                )
                return {"text": f"Reply rate limit active. Try again in {wait_seconds}s."}, 200
            reply_cost = self.settings["limits"]["reply_request_cost_usd"]
            cap = self.settings["limits"]["daily_cost_cap_usd"]
            if self.store.will_exceed_cap(cap, reply_cost):
                self.store.release_reply_slot()
                slot_claimed = False
                self.store.release_reply(tweet_id)
                updated = self.store.get_tweet(tweet_id)
                self.slack_client.update_status(
                    updated["slack_channel"],
                    updated["slack_ts"],
                    updated,
                    "Daily cost cap reached.",
                )
                return {"text": "Daily cost cap reached."}, 200
            template_key = "a" if action_id == "reply_a" else "b"
            reply_text = self.settings["reply_templates"][template_key]
            self.store.add_reply_call(reply_cost)
            reply = self.x_client.reply_to_tweet(tweet_id, reply_text)
            reply_sent = True
            if not self.store.mark_replied(tweet_id, template_key, reply_text, reply.get("id", "")):
                raise RuntimeError("Reply was sent on X but local state was not updated.")
            updated = self.store.get_tweet(tweet_id)
            self.slack_client.update_status(
                updated["slack_channel"],
                updated["slack_ts"],
                updated,
                f"Reply sent with template {template_key.upper()}",
            )
            return {"text": "Reply sent."}, 200
        except Exception:
            if slot_claimed and not reply_sent:
                self.store.release_reply_slot()
            if not reply_sent:
                self.store.release_reply(tweet_id)
            raise

    def run_action(self, action_id, tweet_id):
        try:
            return self.handle_action(action_id, tweet_id)
        except Exception as exc:
            tweet = self.store.get_tweet(tweet_id)
            if tweet and tweet["slack_channel"] and tweet["slack_ts"]:
                if tweet["status"] == "alerted":
                    self.slack_client.update_match(
                        tweet["slack_channel"],
                        tweet["slack_ts"],
                        tweet,
                        self.settings["reply_templates"],
                        f"Action failed: {exc}",
                    )
                else:
                    self.slack_client.update_status(
                        tweet["slack_channel"],
                        tweet["slack_ts"],
                        tweet,
                        f"Action failed: {exc}",
                    )
            return {"text": str(exc)}, 500
