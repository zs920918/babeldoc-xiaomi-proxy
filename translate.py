"""
PDF translation script using BabelDOC + Xiaomi MiMo API.

Auto-installs BabelDOC on first run. Starts proxy automatically.

Usage:
    python translate.py input.pdf
    python translate.py input.pdf --pages 7-10
    python translate.py input.pdf --lang-in en --lang-out zh
"""

import argparse
import os
import subprocess
import sys
import socket
import time
import signal


def ensure_babeldoc():
    """Auto-install BabelDOC via uv if not already installed."""
    try:
        import babeldoc
        return
    except ImportError:
        pass

    print("[*] BabelDOC not found. Installing via uv...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "uv"])
    subprocess.check_call([sys.executable, "-m", "uv", "tool", "install", "--python", "3.12", "BabelDOC"])
    print("[*] BabelDOC installed.")


def find_babeldoc_bin():
    """Find babeldoc executable."""
    result = subprocess.run(
        [sys.executable, "-m", "uv", "tool", "dir"],
        capture_output=True, text=True
    )
    tool_dir = result.stdout.strip()
    candidates = [
        os.path.join(tool_dir, "babeldoc", "bin", "babeldoc"),
        os.path.join(tool_dir, "babeldoc", "Scripts", "babeldoc.exe"),
        os.path.join(tool_dir, "babeldoc", "bin", "babeldoc.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    for path in os.environ.get("PATH", "").split(os.pathsep):
        for name in ["babeldoc", "babeldoc.exe"]:
            full = os.path.join(path, name)
            if os.path.exists(full):
                return full

    return "babeldoc"


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def wait_for_port(port: int, timeout: int = 15) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser(description="Translate PDF with Xiaomi MiMo + BabelDOC")
    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("--model", default="xiaomi/mimo-v2.5-pro", help="Model name (default: xiaomi/mimo-v2.5-pro)")
    parser.add_argument("--lang-in", default="en", help="Source language (default: en)")
    parser.add_argument("--lang-out", default="zh", help="Target language (default: zh)")
    parser.add_argument("--api-key", default="", help="Xiaomi MiMo API key")
    parser.add_argument("--target-url", default="http://model.mify.ai.srv/v1", help="Target API base URL")
    parser.add_argument("--proxy-port", type=int, default=8899, help="Proxy port (default: 8899)")
    parser.add_argument("--output", "-o", default=".", help="Output directory")
    parser.add_argument("--qps", type=int, default=4, help="QPS limit (default: 4)")
    parser.add_argument("--pages", default=None, help="Pages to translate, e.g. '1,2,3-5'")
    parser.add_argument("--no-mono", action="store_true", help="Skip monolingual output")
    parser.add_argument("--no-dual", action="store_true", help="Skip bilingual output")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: file not found: {args.input}")
        sys.exit(1)

    ensure_babeldoc()

    proxy_process = None
    try:
        proxy_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.py")

        if is_port_available(args.proxy_port):
            print(f"[*] Starting proxy on port {args.proxy_port}...")
            proxy_process = subprocess.Popen(
                [sys.executable, proxy_script,
                 "--port", str(args.proxy_port),
                 "--target-url", args.target_url,
                 "--api-key", args.api_key],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if not wait_for_port(args.proxy_port):
                print("Error: proxy failed to start")
                proxy_process.terminate()
                sys.exit(1)
            print("[*] Proxy ready.")
        else:
            print(f"[*] Port {args.proxy_port} in use, assuming proxy is running.")

        babeldoc_bin = find_babeldoc_bin()
        cmd = [
            babeldoc_bin,
            "--openai",
            "--openai-model", args.model,
            "--openai-base-url", f"http://localhost:{args.proxy_port}/v1",
            "--openai-api-key", args.api_key or "placeholder",
            "--lang-in", args.lang_in,
            "--lang-out", args.lang_out,
            "--qps", str(args.qps),
            "--output", args.output,
            "--files", args.input,
        ]
        if args.pages:
            cmd.extend(["--pages", args.pages])
        if args.no_mono:
            cmd.append("--no-mono")
        if args.no_dual:
            cmd.append("--no-dual")

        print(f"[*] Translating {os.path.basename(args.input)}...")
        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    except KeyboardInterrupt:
        print("\n[*] Interrupted.")
    finally:
        if proxy_process:
            print("[*] Shutting down proxy...")
            proxy_process.terminate()
            try:
                proxy_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proxy_process.kill()


if __name__ == "__main__":
    main()
