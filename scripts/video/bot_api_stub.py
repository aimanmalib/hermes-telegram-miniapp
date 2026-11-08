"""A loopback stand-in for the Telegram Bot API, so the demo rig can show Ask end to end without a bot.

Hermes's Telegram adapter accepts a custom ``base_url`` (meant for a self-hosted telegram-bot-api server).
rig.sh points it here: the real gateway connects, the real cron ticker runs the Ask job, and the real
delivery lane calls ``sendMessage`` on this server, which writes the message to a JSON-lines file instead
of sending it anywhere. record.py reads the delivered text from that file for the mock chat screen.

    BOT_API_PORT=9180 BOT_API_LOG=messages.jsonl python3 scripts/video/bot_api_stub.py

Loopback only. It answers the handful of methods the adapter calls at start-up and when sending; any
other method gets ``{"ok": true, "result": true}``. getUpdates waits and returns nothing (no inbound chat).
"""
import json
import os
import threading
import time
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

PORT = int(os.environ.get("BOT_API_PORT", "9180"))
LOG = os.environ.get("BOT_API_LOG", "bot-api-messages.jsonl")
POLL_WAIT = float(os.environ.get("BOT_API_POLL_WAIT", "10"))
BOT = {"id": 100000000, "is_bot": True, "first_name": "Hermes", "username": "hermes_rig_bot",
       "can_join_groups": False, "can_read_all_group_messages": False, "supports_inline_queries": False}
send_methods = {"sendMessage", "editMessageText"}
_lock = threading.Lock()
_next_id = [1]


def parse_body(content_type: str, raw: bytes) -> dict:
    """Bot API parameters from a JSON, form-encoded or multipart body (values may be JSON-encoded)."""
    if not raw:
        return {}
    if content_type.startswith("application/json"):
        return json.loads(raw)
    if content_type.startswith("multipart/form-data"):
        msg = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + raw)
        return {part.get_param("name", header="content-disposition"): part.get_content()
                for part in msg.iter_parts()}
    return dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))


def result_for(method: str, params: dict):
    if method == "getMe":
        return BOT
    if method == "getUpdates":
        time.sleep(min(float(params.get("timeout") or 0), POLL_WAIT))
        return []
    if method == "getChat":
        return {"id": int(params.get("chat_id", 0)), "type": "private"}
    if method in send_methods:
        with _lock:
            message_id, _next_id[0] = _next_id[0], _next_id[0] + 1
            record = {"method": method, "chat_id": str(params.get("chat_id", "")), "text": params.get("text", ""),
                      "message_id": message_id, "ts": time.time()}
            with open(LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"message_id": message_id, "date": int(time.time()), "from": BOT, "text": params.get("text", ""),
                "chat": {"id": int(params.get("chat_id") or 0), "type": "private"}}
    return True


class Handler(BaseHTTPRequestHandler):
    def _answer(self):
        path = urlsplit(self.path).path
        method = path.rsplit("/", 1)[-1]
        if not path.startswith("/bot") or path.count("/") < 2:
            self.send_error(404)
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            params = parse_body(self.headers.get("Content-Type", ""), raw)
            body = {"ok": True, "result": result_for(method, params)}
        except Exception as exc:  # a malformed request should not take the stand-in down
            body = {"ok": False, "error_code": 400, "description": f"Bad Request: {exc}"}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = _answer

    def log_message(self, fmt, *args):  # quiet: the message file is the record
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    print(f"bot api stand-in on 127.0.0.1:{PORT}, messages -> {LOG}", flush=True)
    server.serve_forever()
