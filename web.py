import json
import logging
import threading
from time import sleep

from flask import Flask, jsonify, redirect, request


def create_app(service, slack_client):
    app = Flask(__name__)

    def command_response(text):
        return jsonify({"response_type": "ephemeral", "text": text}), 200

    def format_health():
        snapshot = service.get_health_snapshot()
        x_user = snapshot["x_username"] or "not connected"
        return (
            "Bot health: ok\n"
            f"Slack ready: {'yes' if snapshot['slack_ready'] else 'no'}\n"
            f"X OAuth2: {'connected' if snapshot['x_oauth2_connected'] else 'not connected'} ({x_user})\n"
            f"Poll interval: {snapshot['poll_interval_seconds']}s\n"
            f"Search calls today: {snapshot['search_calls']}\n"
            f"Reply calls today: {snapshot['reply_calls']}\n"
            f"Estimated cost today: ${snapshot['estimated_cost']:.2f}"
        )

    def format_usage():
        usage = service.get_usage_snapshot()
        return (
            "Usage today\n"
            f"Search calls: {usage['search_calls']}\n"
            f"Reply calls: {usage['reply_calls']}\n"
            f"Estimated cost: ${usage['estimated_cost']:.2f}"
        )

    @app.get("/health")
    def health():
        return jsonify(service.get_health_snapshot())

    @app.get("/x/connect")
    def x_connect():
        url = service.x_client.build_oauth2_authorize_url()
        return redirect(url, code=302)

    @app.get("/x/status")
    def x_status():
        return jsonify(service.x_client.get_oauth2_status())

    @app.get("/x/callback")
    def x_callback():
        error = request.args.get("error")
        if error:
            message = request.args.get("error_description") or error
            return (
                f"X OAuth2 failed: {message}",
                400,
                {"Content-Type": "text/plain; charset=utf-8"},
            )
        code = request.args.get("code", "")
        state = request.args.get("state", "")
        if not code or not state:
            return (
                "Missing OAuth callback parameters.",
                400,
                {"Content-Type": "text/plain; charset=utf-8"},
            )
        token = service.x_client.exchange_oauth2_code(code, state)
        user = token.get("user", {})
        username = user.get("username", "")
        text = "X OAuth2 connected."
        if username:
            text += f" Logged in as @{username}."
        return text, 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.post("/slack/actions")
    def slack_actions():
        body = request.get_data()
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")
        if not slack_client.verify_signature(timestamp, body, signature):
            return jsonify({"ok": False, "error": "invalid signature"}), 401
        payload = request.form.get("payload", "")
        if not payload:
            return jsonify({"ok": False, "error": "missing payload"}), 400
        data = json.loads(payload)
        action = data["actions"][0]
        threading.Thread(
            target=service.run_action,
            args=(action["action_id"], action["value"]),
            daemon=True,
        ).start()
        return jsonify({"ok": True, "text": "Processing action"}), 200

    @app.post("/slack/command")
    def slack_command():
        body = request.get_data()
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")
        if not slack_client.verify_signature(timestamp, body, signature):
            return jsonify({"ok": False, "error": "invalid signature"}), 401
        text = (request.form.get("text") or "").strip()
        if not text:
            return command_response(
                "Commands: help, health, usage, poll"
            )
        command = text.split()[0].lower()
        if command == "help":
            return command_response("Commands: help, health, usage, poll")
        if command == "health":
            return command_response(format_health())
        if command == "usage":
            return command_response(format_usage())
        if command == "poll":
            try:
                result = service.poll_once()
            except Exception as exc:
                return command_response(f"Poll failed: {exc}")
            if result["status"] != "ok":
                return command_response(f"Poll result: {result['status']}")
            return command_response(
                f"Poll completed. New Slack alerts: {len(result['matches'])}"
            )
        return command_response("Unknown command. Use: help, health, usage, poll")

    @app.post("/poll")
    def poll_now():
        return jsonify(service.poll_once())

    return app


class Poller(threading.Thread):
    def __init__(self, service, interval_seconds):
        super().__init__(daemon=True)
        self.service = service
        self.interval_seconds = interval_seconds
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                self.service.poll_once()
            except Exception as exc:
                logging.exception(str(exc))
            sleep(self.interval_seconds)

    def stop(self):
        self.stop_flag.set()
