import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR.parents[1]
ENV_PATH = WORKSPACE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.json"
STATE_DB_PATH = BASE_DIR / "data" / "state.db"


def load_settings():
    load_dotenv(ENV_PATH, override=False)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    STATE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return {
        "base_dir": BASE_DIR,
        "workspace_dir": WORKSPACE_DIR,
        "state_db_path": STATE_DB_PATH,
        "x": {
            "bearer_token": os.getenv("X_BEARER_TOKEN", "").strip(),
            "oauth2_client_id": os.getenv("X_OAUTH2_CLIENT_ID", "").strip(),
            "oauth2_client_secret": os.getenv("X_OAUTH2_CLIENT_SECRET", "").strip(),
            "oauth2_redirect_uri": os.getenv("X_OAUTH2_REDIRECT_URI", "").strip(),
            "oauth2_scopes": [
                scope.strip()
                for scope in os.getenv(
                    "X_OAUTH2_SCOPES",
                    "tweet.read tweet.write users.read offline.access",
                ).split()
                if scope.strip()
            ],
        },
        "slack": {
            "bot_token": os.getenv("SLACK_BOT_TOKEN", "").strip(),
            "signing_secret": os.getenv("SLACK_SIGNING_SECRET", "").strip(),
            "channel_id": os.getenv("SLACK_CHANNEL_ID", "").strip(),
        },
        "server": data["server"],
        "search": data["search"],
        "matcher": data["matcher"],
        "reply_templates": data["reply_templates"],
        "limits": data["limits"],
    }


def has_x_credentials(settings):
    return bool(settings["x"]["bearer_token"])


def has_x_oauth2_client_credentials(settings):
    x = settings["x"]
    return all(
        [
            x["oauth2_client_id"],
            x["oauth2_client_secret"],
            x["oauth2_redirect_uri"],
        ]
    )


def has_slack_credentials(settings):
    slack = settings["slack"]
    return all(
        [
            slack["bot_token"],
            slack["signing_secret"],
            slack["channel_id"],
        ]
    )
