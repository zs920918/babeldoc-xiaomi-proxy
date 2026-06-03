import argparse
import json
import logging
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("xiaomi_proxy")

TARGET_BASE_URL = ""
TARGET_API_KEY = ""
PROXY_PORT = 8899


class ConcurrencyAutoTuner:
    """Auto-tune concurrency by gradually increasing and backing off on errors."""

    def __init__(self, start_concurrency=1, max_concurrency=32):
        self.concurrency = start_concurrency
        self.max_concurrency = max_concurrency
        self.lock = threading.Lock()
        self.semaphore = threading.Semaphore(start_concurrency)

        self.total_requests = 0
        self.total_success = 0
        self.total_errors = 0
        self.consecutive_success = 0
        self.consecutive_errors = 0
        self.last_increase_time = time.monotonic()

        self.window_success = 0
        self.window_total = 0
        self.window_start = time.monotonic()
        self.window_duration = 10  # check every 10 seconds

    def acquire(self):
        self.semaphore.acquire()

    def release(self):
        self.semaphore.release()

    def report_success(self):
        with self.lock:
            self.total_requests += 1
            self.total_success += 1
            self.consecutive_success += 1
            self.consecutive_errors = 0
            self.window_success += 1
            self.window_total += 1
            self._maybe_increase()

    def report_error(self, is_rate_limit=False):
        with self.lock:
            self.total_requests += 1
            self.total_errors += 1
            self.consecutive_errors += 1
            self.consecutive_success = 0
            self.window_total += 1

            if is_rate_limit or self.consecutive_errors >= 2:
                self._decrease()

    def _maybe_increase(self):
        now = time.monotonic()
        if now - self.window_start < self.window_duration:
            return

        success_rate = self.window_success / max(self.window_total, 1)
        elapsed = now - self.last_increase_time

        if success_rate >= 0.95 and elapsed >= 10 and self.concurrency < self.max_concurrency:
            old = self.concurrency
            self.concurrency = min(self.concurrency + 1, self.max_concurrency)
            self.semaphore = threading.Semaphore(self.concurrency)
            self.last_increase_time = now
            if old != self.concurrency:
                logger.info(f"[AutoTune] Concurrency: {old} -> {self.concurrency}")

        self.window_success = 0
        self.window_total = 0
        self.window_start = now

    def _decrease(self):
        old = self.concurrency
        self.concurrency = max(1, self.concurrency - 1)
        self.semaphore = threading.Semaphore(self.concurrency)
        self.last_increase_time = time.monotonic()
        self.consecutive_errors = 0
        if old != self.concurrency:
            logger.warning(f"[AutoTune] Concurrency: {old} -> {self.concurrency} (errors)")

    def status(self):
        with self.lock:
            return {
                "concurrency": self.concurrency,
                "total": self.total_requests,
                "success": self.total_success,
                "errors": self.total_errors,
            }


auto_tuner = ConcurrencyAutoTuner()


def convert_messages_to_responses_input(messages: list) -> tuple:
    instructions = None
    input_items = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            instructions = content
        elif role == "user":
            input_items.append({
                "type": "message",
                "role": "user",
                "content": content,
            })
        elif role == "assistant":
            input_items.append({
                "type": "message",
                "role": "assistant",
                "content": content,
            })

    if not input_items:
        input_items = messages

    return instructions, input_items


def convert_responses_to_chat_completion(response_data: dict, model: str) -> dict:
    output_text = ""
    output_items = response_data.get("output", [])

    for item in output_items:
        if item.get("type") == "message":
            content_list = item.get("content", [])
            for content in content_list:
                if content.get("type") == "output_text":
                    output_text += content.get("text", "")
                elif content.get("type") == "refusal":
                    output_text += f"[Refusal: {content.get('refusal', '')}]"

    usage = response_data.get("usage", {})
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    total_tokens = prompt_tokens + completion_tokens

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": output_text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class ProxyHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        logger.info(format % args)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/v1/chat/completions":
            self._handle_chat_completions()
        else:
            self._send_error(404, f"Not found: {parsed.path}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok", **auto_tuner.status()})
        elif parsed.path == "/v1/models":
            self._handle_models()
        else:
            self._send_error(404, "Not found")

    def _handle_models(self):
        self._send_json({
            "object": "list",
            "data": [
                {
                    "id": "xiaomi/mimo-v2.5-pro",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "xiaomi",
                },
                {
                    "id": "xiaomi/mimo-v2-flash",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "xiaomi",
                },
                {
                    "id": "xiaomi/mimo-v2-omni",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "xiaomi",
                },
            ],
        })

    def _handle_chat_completions(self):
        auto_tuner.acquire()
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            request_data = json.loads(body)

            model = request_data.get("model", "xiaomi/mimo-v2.5-pro")
            messages = request_data.get("messages", [])
            temperature = request_data.get("temperature")
            max_tokens = request_data.get("max_tokens")

            instructions, input_items = convert_messages_to_responses_input(messages)

            responses_request = {
                "model": model,
                "input": input_items,
            }
            if instructions:
                responses_request["instructions"] = instructions
            if temperature is not None:
                responses_request["temperature"] = temperature
            if max_tokens is not None:
                responses_request["max_output_tokens"] = max_tokens

            logger.info(f"Proxying: model={model}, concurrency={auto_tuner.concurrency}")

            api_key = self.headers.get("Authorization", "").replace("Bearer ", "")
            if not api_key:
                api_key = TARGET_API_KEY

            target_url = f"{TARGET_BASE_URL}/responses"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            with httpx.Client(timeout=600) as client:
                resp = client.post(target_url, json=responses_request, headers=headers)

            if resp.status_code == 429:
                auto_tuner.report_error(is_rate_limit=True)
                logger.warning(f"Rate limited (429)")
                self._send_error(429, "Rate limited")
                return

            if resp.status_code != 200:
                auto_tuner.report_error(is_rate_limit=False)
                logger.error(f"Target API error: {resp.status_code} {resp.text[:500]}")
                self._send_error(resp.status_code, resp.text)
                return

            responses_data = resp.json()
            chat_response = convert_responses_to_chat_completion(responses_data, model)
            auto_tuner.report_success()
            self._send_json(chat_response)

        except httpx.ConnectError as e:
            auto_tuner.report_error(is_rate_limit=False)
            logger.error(f"Connection error: {e}")
            self._send_error(502, f"Cannot connect to target API: {e}")
        except Exception as e:
            auto_tuner.report_error(is_rate_limit=False)
            logger.exception("Error handling request")
            self._send_error(500, str(e))
        finally:
            auto_tuner.release()

    def _send_json(self, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code: int, message: str):
        body = json.dumps({
            "error": {"message": message, "type": "proxy_error", "code": code}
        }).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    global TARGET_BASE_URL, TARGET_API_KEY, PROXY_PORT

    parser = argparse.ArgumentParser(description="Xiaomi MiMo API Proxy")
    parser.add_argument("--port", type=int, default=8899, help="Proxy listen port")
    parser.add_argument("--target-url", required=True, help="Target API base URL")
    parser.add_argument("--api-key", default="", help="Default API key")
    parser.add_argument("--max-concurrency", type=int, default=32, help="Max concurrency (default: 32)")
    args = parser.parse_args()

    PROXY_PORT = args.port
    TARGET_BASE_URL = args.target_url.rstrip("/")
    TARGET_API_KEY = args.api_key

    global auto_tuner
    auto_tuner = ConcurrencyAutoTuner(start_concurrency=1, max_concurrency=args.max_concurrency)

    server = ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), ProxyHandler)
    logger.info(f"Proxy started on http://127.0.0.1:{PROXY_PORT}")
    logger.info(f"Target: {TARGET_BASE_URL}/responses")
    logger.info(f"Auto-tune: concurrency 1 -> {args.max_concurrency}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
