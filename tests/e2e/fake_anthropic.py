"""A scripted Anthropic Messages endpoint for driving the real Claude Code CLI.

The first request that carries tools and no tool_result gets a `Write` tool_use
that creates a plan file; every later request gets a plain `end_turn`. Requests
are appended to a log for debugging. Usage: fake_anthropic.py PLAN_PATH PORT_FILE
LOG_FILE. The bound port is written to PORT_FILE once the server listens. The
server exits when its parent process dies or after IDLE_SECONDS without a request.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import time

PLAN_BODY = """---
pentimento:
  status: not-started
  intent: unset
  created: 2026-09-25
---
# End-to-end sample

## Progress
- [x] 1. Write the plan
- [ ] 2. Verify the hook ran
"""

MODEL = "claude-sonnet-5"
IDLE_SECONDS = 120
POLL_SECONDS = 1


def _has_tool_result(messages: list) -> bool:
    for message in messages:
        content = message.get("content")
        if isinstance(content, list) and any(
            isinstance(block, dict) and block.get("type") == "tool_result" for block in content
        ):
            return True
    return False


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _envelope(content_block: dict, stop_reason: str) -> list[bytes]:
    message = {
        "id": "msg_e2e",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    events = [_sse("message_start", {"type": "message_start", "message": message})]
    events.append(
        _sse(
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": content_block["start"]},
        )
    )
    events.append(
        _sse(
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": content_block["delta"]},
        )
    )
    events.append(_sse("content_block_stop", {"type": "content_block_stop", "index": 0}))
    events.append(
        _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
        )
    )
    events.append(_sse("message_stop", {"type": "message_stop"}))
    return events


def _write_block(plan_path: str) -> dict:
    arguments = json.dumps({"file_path": plan_path, "content": PLAN_BODY})
    return {
        "start": {"type": "tool_use", "id": "toolu_e2e", "name": "Write", "input": {}},
        "delta": {"type": "input_json_delta", "partial_json": arguments},
    }


def _text_block(text: str) -> dict:
    return {
        "start": {"type": "text", "text": ""},
        "delta": {"type": "text_delta", "text": text},
    }


def _plain_message(text: str) -> dict:
    return {
        "id": "msg_e2e",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def _exit_when_orphaned_or_idle(last_request: list[float]) -> None:
    parent = os.getppid()
    while True:
        time.sleep(POLL_SECONDS)
        if os.getppid() != parent or time.monotonic() - last_request[0] > IDLE_SECONDS:
            os._exit(0)


def make_handler(plan_path: str, log_path: str, last_request: list[float]):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _reply(self, status: int, content_type: str, payload: bytes):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            last_request[0] = time.monotonic()
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length) or b"{}")
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(json.dumps({"path": self.path, "request": request}) + "\n")
            if not self.path.startswith("/v1/messages") or "count_tokens" in self.path:
                self._reply(404, "application/json", b'{"type": "error"}')
                return
            first_turn = request.get("tools") and not _has_tool_result(request.get("messages", []))
            if not request.get("stream"):
                self._reply(200, "application/json", json.dumps(_plain_message("ok")).encode())
                return
            if first_turn:
                events = _envelope(_write_block(plan_path), "tool_use")
            else:
                events = _envelope(_text_block("Done."), "end_turn")
            self._reply(200, "text/event-stream", b"".join(events))

    return Handler


def main() -> None:
    plan_path, port_file, log_path = sys.argv[1:4]
    last_request = [time.monotonic()]
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(plan_path, log_path, last_request)
    )
    threading.Thread(target=_exit_when_orphaned_or_idle, args=(last_request,), daemon=True).start()
    with open(port_file, "w", encoding="utf-8") as handle:
        handle.write(str(server.server_address[1]))
    server.serve_forever()


if __name__ == "__main__":
    main()
