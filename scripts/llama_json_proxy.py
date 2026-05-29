from __future__ import annotations

import argparse
import atexit
import json
import os
import threading
import time
import uuid
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _now_ms() -> int:
    return int(time.time() * 1000)


def _timestamp_slug() -> str:
    return time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())


def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _extract_response_payload(body: bytes) -> tuple[str, str | None, dict | None]:
    text = body.decode("utf-8", errors="replace")
    assistant_content = ""
    model_name: str | None = None
    timings: dict | None = None

    if text.lstrip().startswith("data:"):
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue

            model_name = chunk.get("model", model_name)
            timings = chunk.get("timings", timings)
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or choice.get("message") or {}

            if isinstance(delta, dict):
                assistant_content += _text_from_content(delta.get("content"))
                assistant_content += _text_from_content(delta.get("reasoning_content"))
            elif isinstance(choice.get("text"), str):
                assistant_content += choice["text"]

        return assistant_content, model_name, timings

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text, None, None

    model_name = payload.get("model")
    timings = payload.get("timings")
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}

    if isinstance(message, dict):
        assistant_content = _text_from_content(message.get("content"))
        assistant_content += _text_from_content(message.get("reasoning_content"))
    elif isinstance(choice.get("text"), str):
        assistant_content = choice["text"]

    return assistant_content, model_name, timings


class ConversationExporter:
    def __init__(self, logs_dir: Path, node_prefix: str) -> None:
        self.logs_dir = logs_dir
        self.node_prefix = node_prefix
        self.lock = threading.Lock()
        self.current_conv_id: str | None = None
        self.current_conv_name = ""
        self.current_file: Path | None = None

    def _ensure_conversation(self, first_user_message: str, *, reset: bool) -> None:
        if self.current_conv_id is None or reset:
            self.current_conv_id = uuid.uuid4().hex[:12]
            self.current_conv_name = first_user_message
            self.current_file = self.logs_dir / f"{_timestamp_slug()}_conv_{self.current_conv_id}__{self.node_prefix}.json"

    def record(self, request_json: dict, response_body: bytes) -> None:
        messages = request_json.get("messages")
        if not isinstance(messages, list) or not messages:
            return

        first_user_message = ""
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "user":
                first_user_message = _text_from_content(message.get("content"))
                if first_user_message:
                    break

        assistant_content, model_name, timings = _extract_response_payload(response_body)
        reset = len(messages) == 1 and bool(first_user_message)
        now_ms = _now_ms()

        with self.lock:
            self._ensure_conversation(first_user_message or "Conversation", reset=reset)

            exported_messages: list[dict] = []
            previous_id = "root"
            for index, message in enumerate(messages):
                if not isinstance(message, dict):
                    continue

                message_id = f"m{index}_{uuid.uuid4().hex[:10]}"
                exported_messages.append(
                    {
                        "convId": self.current_conv_id,
                        "role": message.get("role", "user"),
                        "content": _text_from_content(message.get("content")),
                        "type": "text",
                        "timestamp": now_ms,
                        "toolCalls": "",
                        "children": [],
                        "extra": [],
                        "id": message_id,
                        "parent": previous_id,
                    }
                )
                previous_id = message_id

            assistant_id = uuid.uuid4().hex[:11]
            assistant_message = {
                "convId": self.current_conv_id,
                "type": "text",
                "role": "assistant",
                "content": assistant_content,
                "timestamp": now_ms,
                "toolCalls": "",
                "children": [],
                "model": model_name or request_json.get("model") or "",
                "id": assistant_id,
                "parent": previous_id,
            }
            if timings:
                assistant_message["timings"] = timings

            exported_messages.append(assistant_message)

            payload = {
                "conv": {
                    "id": self.current_conv_id,
                    "name": self.current_conv_name,
                    "lastModified": now_ms,
                    "currNode": assistant_id,
                },
                "messages": exported_messages,
            }

            if self.current_file is not None:
                self.current_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream_host = "127.0.0.1"
    upstream_port = 18010
    exporter: ConversationExporter | None = None

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def do_OPTIONS(self) -> None:
        self._proxy()

    def _proxy(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        request_body = self.rfile.read(content_length) if content_length else b""

        upstream_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        upstream_headers["Host"] = f"{self.upstream_host}:{self.upstream_port}"

        connection = HTTPConnection(self.upstream_host, self.upstream_port, timeout=600)
        connection.request(self.command, self.path, body=request_body, headers=upstream_headers)
        response = connection.getresponse()
        response_body = response.read()

        self.send_response(response.status, response.reason)
        for header, value in response.getheaders():
            if header.lower() in {"connection", "content-length", "transfer-encoding"}:
                continue
            self.send_header(header, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        if response_body:
            self.wfile.write(response_body)

        if self.command == "POST" and self.exporter is not None:
            try:
                request_json = json.loads(request_body.decode("utf-8"))
            except json.JSONDecodeError:
                request_json = None

            if isinstance(request_json, dict) and isinstance(request_json.get("messages"), list):
                self.exporter.record(request_json, response_body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", required=True)
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--upstream-host", required=True)
    parser.add_argument("--upstream-port", type=int, required=True)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--node-prefix", required=True)
    parser.add_argument("--pid-file")
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()), encoding="utf-8")

        def _cleanup_pid() -> None:
            try:
                Path(args.pid_file).unlink(missing_ok=True)
            except OSError:
                pass

        atexit.register(_cleanup_pid)

    ProxyHandler.upstream_host = args.upstream_host
    ProxyHandler.upstream_port = args.upstream_port
    ProxyHandler.exporter = ConversationExporter(logs_dir=logs_dir, node_prefix=args.node_prefix)

    server = ThreadingHTTPServer((args.listen_host, args.listen_port), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())