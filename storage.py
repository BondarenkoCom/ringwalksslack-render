import sqlite3
import threading
import time
from datetime import datetime, timezone
import json
from pathlib import Path


class Store:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.setup()

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def setup(self):
        with self.lock, self.connect() as conn:
            conn.executescript(
                """
                create table if not exists tweets (
                    tweet_id text primary key,
                    tweet_text text not null,
                    tweet_url text not null,
                    reply_warning text,
                    status text not null,
                    slack_channel text,
                    slack_ts text,
                    reply_template text,
                    reply_text text,
                    x_reply_id text,
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists daily_usage (
                    day text primary key,
                    search_calls integer not null default 0,
                    reply_calls integer not null default 0,
                    estimated_cost real not null default 0,
                    updated_at text not null default current_timestamp
                );

                create table if not exists app_state (
                    key text primary key,
                    value text not null,
                    updated_at text not null default current_timestamp
                );
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("pragma table_info(tweets)").fetchall()
            }
            if "reply_warning" not in columns:
                conn.execute("alter table tweets add column reply_warning text")

    def utc_day(self):
        return datetime.now(timezone.utc).date().isoformat()

    def get_tweet(self, tweet_id):
        with self.lock, self.connect() as conn:
            return conn.execute(
                "select * from tweets where tweet_id = ?",
                (str(tweet_id),),
            ).fetchone()

    def should_skip(self, tweet_id):
        row = self.get_tweet(tweet_id)
        if not row:
            return False
        return row["status"] in {"pending_alert", "alerted", "replied", "ignored", "replying"}

    def claim_pending_alert(self, tweet_id, tweet_text, tweet_url, reply_warning=""):
        with self.lock, self.connect() as conn:
            cur = conn.execute(
                """
                insert into tweets (tweet_id, tweet_text, tweet_url, reply_warning, status)
                values (?, ?, ?, ?, 'pending_alert')
                on conflict(tweet_id) do nothing
                """,
                (str(tweet_id), tweet_text, tweet_url, reply_warning),
            )
            return cur.rowcount == 1

    def save_pending_tweet(self, tweet_id, tweet_text, tweet_url, reply_warning=""):
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                insert into tweets (tweet_id, tweet_text, tweet_url, reply_warning, status)
                values (?, ?, ?, ?, 'pending_alert')
                on conflict(tweet_id) do update set
                    tweet_text = excluded.tweet_text,
                    tweet_url = excluded.tweet_url,
                    reply_warning = excluded.reply_warning,
                    updated_at = current_timestamp
                """,
                (str(tweet_id), tweet_text, tweet_url, reply_warning),
            )

    def drop_pending_alert(self, tweet_id):
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                delete from tweets
                where tweet_id = ? and status = 'pending_alert'
                """,
                (str(tweet_id),),
            )

    def mark_alerted(self, tweet_id, channel_id, message_ts):
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                update tweets
                set status = 'alerted',
                    slack_channel = ?,
                    slack_ts = ?,
                    updated_at = current_timestamp
                where tweet_id = ?
                """,
                (channel_id, message_ts, str(tweet_id)),
            )

    def claim_reply(self, tweet_id):
        with self.lock, self.connect() as conn:
            cur = conn.execute(
                """
                update tweets
                set status = 'replying',
                    updated_at = current_timestamp
                where tweet_id = ? and status = 'alerted'
                """,
                (str(tweet_id),),
            )
            return cur.rowcount == 1

    def release_reply(self, tweet_id):
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                update tweets
                set status = 'alerted',
                    updated_at = current_timestamp
                where tweet_id = ? and status = 'replying'
                """,
                (str(tweet_id),),
            )

    def mark_replied(self, tweet_id, template_key, reply_text, x_reply_id):
        with self.lock, self.connect() as conn:
            cur = conn.execute(
                """
                update tweets
                set status = 'replied',
                    reply_template = ?,
                    reply_text = ?,
                    x_reply_id = ?,
                    updated_at = current_timestamp
                where tweet_id = ? and status = 'replying'
                """,
                (template_key, reply_text, x_reply_id, str(tweet_id)),
            )
            if cur.rowcount != 1:
                return False
            conn.execute(
                """
                insert into app_state (key, value)
                values ('last_reply_at', ?)
                on conflict(key) do update set
                    value = excluded.value,
                    updated_at = current_timestamp
                """,
                (str(time.time()),),
            )
            conn.execute("delete from app_state where key = 'reply_inflight_at'")
            return True

    def mark_ignored(self, tweet_id):
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                update tweets
                set status = 'ignored',
                    updated_at = current_timestamp
                where tweet_id = ? and status in ('alerted', 'replying')
                """,
                (str(tweet_id),),
            )

    def get_daily_usage(self, day=None):
        day = day or self.utc_day()
        with self.lock, self.connect() as conn:
            row = conn.execute(
                "select * from daily_usage where day = ?",
                (day,),
            ).fetchone()
        if row:
            return dict(row)
        return {
            "day": day,
            "search_calls": 0,
            "reply_calls": 0,
            "estimated_cost": 0.0,
        }

    def list_tweets(self, limit=20):
        with self.lock, self.connect() as conn:
            rows = conn.execute(
                """
                select tweet_id, tweet_text, tweet_url, reply_warning, status, slack_channel, slack_ts,
                       reply_template, reply_text, x_reply_id, created_at, updated_at
                from tweets
                order by updated_at desc, created_at desc
                limit ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_search_call(self, cost):
        self._add_usage("search_calls", cost)

    def add_reply_call(self, cost):
        self._add_usage("reply_calls", cost)

    def _add_usage(self, field, cost):
        day = self.utc_day()
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                insert into daily_usage (day, search_calls, reply_calls, estimated_cost)
                values (?, 0, 0, 0)
                on conflict(day) do nothing
                """,
                (day,),
            )
            conn.execute(
                f"""
                update daily_usage
                set {field} = {field} + 1,
                    estimated_cost = estimated_cost + ?,
                    updated_at = current_timestamp
                where day = ?
                """,
                (float(cost), day),
            )

    def will_exceed_cap(self, cap, next_cost):
        usage = self.get_daily_usage()
        return usage["estimated_cost"] + float(next_cost) > float(cap)

    def reply_wait_seconds(self, min_gap_seconds):
        with self.lock, self.connect() as conn:
            row = conn.execute(
                "select value from app_state where key = 'last_reply_at'"
            ).fetchone()
        if not row:
            return 0
        wait = float(min_gap_seconds) - (time.time() - float(row["value"]))
        return max(0, int(wait))

    def claim_reply_slot(self, min_gap_seconds, hold_seconds=120):
        now = time.time()
        with self.lock, self.connect() as conn:
            inflight = conn.execute(
                "select value from app_state where key = 'reply_inflight_at'"
            ).fetchone()
            if inflight:
                try:
                    active_for = now - float(inflight["value"])
                    if active_for < float(hold_seconds):
                        return False, max(1, int(float(hold_seconds) - active_for))
                except ValueError:
                    pass
            last_reply = conn.execute(
                "select value from app_state where key = 'last_reply_at'"
            ).fetchone()
            if last_reply:
                wait = float(min_gap_seconds) - (now - float(last_reply["value"]))
                if wait > 0:
                    return False, max(1, int(wait))
            conn.execute(
                """
                insert into app_state (key, value)
                values ('reply_inflight_at', ?)
                on conflict(key) do update set
                    value = excluded.value,
                    updated_at = current_timestamp
                """,
                (str(now),),
            )
            return True, 0

    def release_reply_slot(self):
        with self.lock, self.connect() as conn:
            conn.execute("delete from app_state where key = 'reply_inflight_at'")

    def get_state(self, key, default=None):
        with self.lock, self.connect() as conn:
            row = conn.execute(
                "select value from app_state where key = ?",
                (str(key),),
            ).fetchone()
        if not row:
            return default
        return row["value"]

    def set_state(self, key, value):
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                insert into app_state (key, value)
                values (?, ?)
                on conflict(key) do update set
                    value = excluded.value,
                    updated_at = current_timestamp
                """,
                (str(key), str(value)),
            )

    def delete_state(self, key):
        with self.lock, self.connect() as conn:
            conn.execute(
                "delete from app_state where key = ?",
                (str(key),),
            )

    def get_json_state(self, key, default=None):
        raw = self.get_state(key)
        if not raw:
            return default
        return json.loads(raw)

    def set_json_state(self, key, value):
        self.set_state(key, json.dumps(value))
