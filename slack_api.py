import hashlib
import hmac
import json
import time

import requests


class SlackApiError(Exception):
    pass


class SlackClient:
    def __init__(self, settings):
        self.bot_token = settings["slack"]["bot_token"]
        self.signing_secret = settings["slack"]["signing_secret"]
        self.channel_id = settings["slack"]["channel_id"]
        self.timeout = settings["limits"].get("request_timeout_seconds", 30)
        self.backoff_seconds = settings["limits"].get("retry_backoff_seconds", [5, 15, 30, 60])

    def ready(self):
        return all([self.bot_token, self.signing_secret, self.channel_id])

    def verify_signature(self, timestamp, body, signature):
        if not self.signing_secret:
            return False
        if not timestamp or not signature:
            return False
        try:
            if abs(time.time() - int(timestamp)) > 60 * 5:
                return False
        except ValueError:
            return False
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        base = f"v0:{timestamp}:{body}"
        digest = "v0=" + hmac.new(
            self.signing_secret.encode("utf-8"),
            base.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(digest, signature)

    def send_match(self, tweet, reply_templates):
        payload = {
            "channel": self.channel_id,
            "text": f"Match found: {tweet['text']}",
            "unfurl_links": False,
            "unfurl_media": False,
            "blocks": self._build_blocks(
                str(tweet["id"]),
                tweet["text"],
                tweet["url"],
                reply_templates,
                warning_text=tweet.get("warning_text", ""),
                include_actions=True,
            ),
        }
        data = self._post("https://slack.com/api/chat.postMessage", payload)
        return {
            "channel": data["channel"],
            "ts": data["ts"],
        }

    def update_status(self, channel_id, message_ts, tweet, status_text):
        payload = {
            "channel": channel_id,
            "ts": message_ts,
            "text": status_text,
            "unfurl_links": False,
            "unfurl_media": False,
            "blocks": self._build_blocks(
                str(tweet["tweet_id"]),
                tweet["tweet_text"],
                tweet["tweet_url"],
                None,
                warning_text=tweet.get("reply_warning", ""),
                status_text=status_text,
                include_actions=False,
            ),
        }
        return self._post("https://slack.com/api/chat.update", payload)

    def update_match(self, channel_id, message_ts, tweet, reply_templates, status_text):
        payload = {
            "channel": channel_id,
            "ts": message_ts,
            "text": status_text or tweet["tweet_text"],
            "unfurl_links": False,
            "unfurl_media": False,
            "blocks": self._build_blocks(
                str(tweet["tweet_id"]),
                tweet["tweet_text"],
                tweet["tweet_url"],
                reply_templates,
                warning_text=tweet.get("reply_warning", ""),
                status_text=status_text,
                include_actions=True,
            ),
        }
        return self._post("https://slack.com/api/chat.update", payload)

    def _build_blocks(
        self,
        tweet_id,
        tweet_text,
        tweet_url,
        reply_templates,
        warning_text="",
        status_text="",
        include_actions=False,
    ):
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Tweet match*\n{tweet_text}\n<{tweet_url}|Open tweet>",
                },
            }
        ]
        context_items = []
        if status_text:
            context_items.append(
                {
                    "type": "mrkdwn",
                    "text": status_text,
                }
            )
        if warning_text:
            context_items.append(
                {
                    "type": "mrkdwn",
                    "text": warning_text,
                }
            )
        if reply_templates:
            context_items.extend(
                [
                    {
                        "type": "mrkdwn",
                        "text": f"Reply A: {reply_templates['a']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"Reply B: {reply_templates['b']}",
                    },
                ]
            )
        if context_items:
            blocks.append(
                {
                    "type": "context",
                    "elements": context_items,
                }
            )
        if include_actions:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open X"},
                            "url": tweet_url,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Reply A"},
                            "style": "primary",
                            "action_id": "reply_a",
                            "value": str(tweet_id),
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Reply B"},
                            "action_id": "reply_b",
                            "value": str(tweet_id),
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Ignore"},
                            "style": "danger",
                            "action_id": "ignore",
                            "value": str(tweet_id),
                        },
                    ],
                }
            )
        return blocks

    def _post(self, url, payload):
        last_error = None
        for attempt in range(len(self.backoff_seconds) + 1):
            try:
                response = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    data=json.dumps(payload),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= len(self.backoff_seconds):
                    raise SlackApiError(str(exc)) from exc
                time.sleep(self.backoff_seconds[attempt])
                continue
            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt >= len(self.backoff_seconds):
                    raise SlackApiError(f"{response.status_code}: {response.text[:500]}")
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        time.sleep(max(1, int(retry_after)))
                        continue
                    except ValueError:
                        pass
                time.sleep(self.backoff_seconds[attempt])
                continue
            if response.status_code >= 400:
                raise SlackApiError(f"{response.status_code}: {response.text[:500]}")
            data = response.json()
            if not data.get("ok"):
                raise SlackApiError(data.get("error", "slack request failed"))
            return data
        raise SlackApiError(str(last_error or "slack request failed"))
