import argparse
import json
import sys

from waitress import serve

from config import has_slack_credentials, has_x_credentials, load_settings
from service import BotService
from slack_api import SlackClient
from storage import Store
from web import Poller, create_app
from x_api import XClient


def build_service():
    settings = load_settings()
    if not has_x_credentials(settings):
        raise RuntimeError("X credentials are missing in workspace .env")
    store = Store(settings["state_db_path"])
    x_client = XClient(settings, store)
    slack_client = SlackClient(settings)
    service = BotService(settings, store, x_client, slack_client)
    return settings, service, slack_client


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        default="preview",
        choices=[
            "preview",
            "poll-once",
            "serve",
            "usage",
            "tweets",
            "x-auth-url",
            "x-auth-status",
        ],
    )
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    settings, service, slack_client = build_service()

    if args.command == "preview":
        try:
            result = service.preview_search()
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "poll-once":
        if not has_slack_credentials(settings):
            raise RuntimeError("Slack credentials are missing in workspace .env")
        print(json.dumps(service.poll_once(), ensure_ascii=False, indent=2))
        return

    if args.command == "serve":
        if not has_slack_credentials(settings):
            raise RuntimeError("Slack credentials are missing in workspace .env")
        app = create_app(service, slack_client)
        poller = Poller(service, settings["search"]["poll_interval_seconds"])
        poller.start()
        print(
            json.dumps(
                {
                    "status": "starting",
                    "server_url": f"http://{settings['server']['host']}:{settings['server']['port']}",
                    "poll_interval_seconds": settings["search"]["poll_interval_seconds"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        serve(app, host=settings["server"]["host"], port=settings["server"]["port"])
        return

    if args.command == "usage":
        print(json.dumps(service.store.get_daily_usage(), ensure_ascii=False, indent=2))
        return

    if args.command == "tweets":
        print(json.dumps(service.store.list_tweets(args.limit), ensure_ascii=False, indent=2))
        return

    if args.command == "x-auth-url":
        print(
            json.dumps(
                {
                    "authorize_url": service.x_client.build_oauth2_authorize_url(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.command == "x-auth-status":
        print(json.dumps(service.x_client.get_oauth2_status(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
