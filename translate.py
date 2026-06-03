"""
PDF translation script using BabelDOC + Xiaomi MiMo API.

Auto-installs BabelDOC on first run via uv. Starts proxy automatically.

Usage:
    python translate.py input.pdf --api-key "your-key"
    python translate.py input.pdf --pages 7-10 --api-key "your-key"
"""

import argparse
import os
import subprocess
import sys
import socket
import time


def run_cmd(cmd, check=True):
    """Run command, print it, return result."""
    print(f"  > {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def ensure_uv():
    """Install uv if not available."""
    if subprocess.run(["uv", "--version"], capture_output=True).returncode == 0:
        print("[*] uv is already installed.")
        return
    print("[*] Installing uv...")
    run_cmd([sys.executable, "-m", "pip", "install", "uv"])


def ensure_babeldoc():
    """Install BabelDOC via uv tool if not already installed."""
    result = subprocess.run(
        ["uv", "tool", "list"], capture_output=True, text=True
    )
    if "babeldoc" in result.stdout.lower():
        print("[*] BabelDOC is already installed.")
        return
    print("[*] Installing BabelDOC (this may take a few minutes on first run)...")
    run_cmd(["uv", "tool", "install", "--python", "3.12", "BabelDOC"])


def get_babeldoc_cmd():
    """Return the command to run babeldoc."""
    # uv tool run (uvx) handles finding the binary automatically
    return ["uv", "tool", "run", "babeldoc"]


def is_port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def wait_for_port(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Translate PDF with Xiaomi MiMo + BabelDOC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python translate.py paper.pdf --api-key sk-xxxxx
  python translate.py paper.pdf --pages 7-10 --api-key sk-xxxxx
  python translate.py paper.pdf --lang-in en --lang-out ja --api-key sk-xxxxx
        """,
    )
    parser.add_argument("input", help="Input PDF file path")
    parser.add_argument("--api-key", default="", help="Xiaomi MiMo API key (required)")
    parser.add_argument("--target-url", default="http://model.mify.ai.srv/v1", help="API base URL (default: http://model.mify.ai.srv/v1)")
    parser.add_argument("--model", default="xiaomi/mimo-v2.5-pro", help="Model name (default: xiaomi/mimo-v2.5-pro)")
    parser.add_argument("--lang-in", default="en", help="Source language (default: en)")
    parser.add_argument("--lang-out", default="zh", help="Target language (default: zh)")
    parser.add_argument("--proxy-port", type=int, default=8899, help="Proxy port (default: 8899)")
    parser.add_argument("--output", "-o", default=".", help="Output directory (default: current dir)")
    parser.add_argument("--qps", type=int, default=4, help="QPS limit (default: 4)")
    parser.add_argument("--pages", default=None, help="Pages to translate, e.g. '1,2,3-5'")
    parser.add_argument("--no-mono", action="store_true", help="Skip monolingual PDF output")
    parser.add_argument("--no-dual", action="store_true", help="Skip bilingual PDF output")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: file not found: {args.input}")
        sys.exit(1)

    # Step 1: Install dependencies
    print("=" * 50)
    print("[Step 1/3] Checking dependencies...")
    print("=" * 50)
    ensure_uv()
    ensure_babeldoc()

    # Step 2: Start proxy
    print("=" * 50)
    print("[Step 2/3] Starting API proxy...")
    print("=" * 50)

    proxy_process = None
    proxy_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.py")

    try:
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
                print("Error: proxy failed to start. Check if port is available.")
                proxy_process.terminate()
                sys.exit(1)
            print(f"[*] Proxy ready on http://127.0.0.1:{args.proxy_port}")
        else:
            print(f"[*] Port {args.proxy_port} in use, assuming proxy is running.")

        # Step 3: Run BabelDOC
        print("=" * 50)
        print(f"[Step 3/3] Translating {os.path.basename(args.input)}...")
        print("=" * 50)

        cmd = get_babeldoc_cmd() + [
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

        result = subprocess.run(cmd)
        if result.returncode == 0:
            print("=" * 50)
            print("[Done] Translation complete!")
            print(f"[*] Output: {os.path.abspath(args.output)}")
            print("=" * 50)
        sys.exit(result.returncode)

    except KeyboardInterrupt:
        print("\n[*] Interrupted by user.")
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
