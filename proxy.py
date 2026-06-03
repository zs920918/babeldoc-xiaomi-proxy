import argparse
import json
import logging
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
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


def convert_messages_to_responses_input(messages: list) -> tuple:
    """Chat Completions messages -> Responses API input format."""
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
    """Responses API response -> Chat Completions format."""
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
            self._send_json({"status": "ok"})
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

            logger.info(f"Proxying: model={model}, messages={len(messages)}")

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

            if resp.status_code != 200:
                logger.error(f"Target API error: {resp.status_code} {resp.text[:500]}")
                self._send_error(resp.status_code, resp.text)
                return

            responses_data = resp.json()
            chat_response = convert_responses_to_chat_completion(responses_data, model)
            self._send_json(chat_response)

        except Exception as e:
            logger.exception("Error handling request")
            self._send_error(500, str(e))

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
    parser.add_argument("--target-url", required=True, help="Target API base URL, e.g. http://model.mify.ai.srv/v1")
    parser.add_argument("--api-key", default="", help="Default API key")
    args = parser.parse_args()

    PROXY_PORT = args.port
    TARGET_BASE_URL = args.target_url.rstrip("/")
    TARGET_API_KEY = args.api_key

    server = HTTPServer(("127.0.0.1", PROXY_PORT), ProxyHandler)
    logger.info(f"Proxy started on http://127.0.0.1:{PROXY_PORT}")
    logger.info(f"Target: {TARGET_BASE_URL}/responses")
    logger.info(f"Route:  /v1/chat/completions -> {TARGET_BASE_URL}/responses")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
