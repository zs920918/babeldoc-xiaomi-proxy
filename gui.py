"""
PDF Translation GUI - BabelDOC + Xiaomi MiMo API

Double-click to open a window where you can:
- Select one or more PDF files
- Choose an output directory
- Configure API settings
- Click translate and watch progress

Usage:
    python gui.py
"""

import os
import sys
import subprocess
import socket
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


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


class TranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("BabelDOC Xiaomi MiMo PDF Translator")
        self.root.geometry("750x620")
        self.root.resizable(True, True)

        self.proxy_process = None
        self.running = False

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 3}

        # ---- API Settings ----
        frame_api = ttk.LabelFrame(self.root, text="API Settings", padding=8)
        frame_api.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(frame_api, text="API Key:").grid(row=0, column=0, sticky="w", **pad)
        self.var_api_key = tk.StringVar()
        ttk.Entry(frame_api, textvariable=self.var_api_key, width=55, show="*").grid(row=0, column=1, sticky="ew", **pad)

        ttk.Label(frame_api, text="Target URL:").grid(row=1, column=0, sticky="w", **pad)
        self.var_target_url = tk.StringVar(value="http://model.mify.ai.srv/v1")
        ttk.Entry(frame_api, textvariable=self.var_target_url, width=55).grid(row=1, column=1, sticky="ew", **pad)

        ttk.Label(frame_api, text="Model:").grid(row=2, column=0, sticky="w", **pad)
        self.var_model = tk.StringVar(value="xiaomi/mimo-v2.5-pro")
        combo = ttk.Combobox(frame_api, textvariable=self.var_model, width=52, values=[
            "xiaomi/mimo-v2.5-pro",
            "xiaomi/mimo-v2-flash",
            "xiaomi/mimo-v2-omni",
        ])
        combo.grid(row=2, column=1, sticky="ew", **pad)

        frame_api.columnconfigure(1, weight=1)

        # ---- Files ----
        frame_files = ttk.LabelFrame(self.root, text="Files", padding=8)
        frame_files.pack(fill="both", padx=8, pady=4, expand=True)

        btn_row = ttk.Frame(frame_files)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Add PDF Files", command=self._add_files).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Clear List", command=self._clear_files).pack(side="left", padx=4)

        self.file_list = scrolledtext.ScrolledText(frame_files, height=6, state="disabled", wrap="word")
        self.file_list.pack(fill="both", expand=True, pady=(4, 0))

        # ---- Output ----
        frame_out = ttk.LabelFrame(self.root, text="Output", padding=8)
        frame_out.pack(fill="x", padx=8, pady=4)

        ttk.Label(frame_out, text="Output Dir:").grid(row=0, column=0, sticky="w", **pad)
        self.var_output = tk.StringVar(value=os.path.join(os.getcwd(), "output"))
        ttk.Entry(frame_out, textvariable=self.var_output, width=45).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frame_out, text="Browse...", command=self._browse_output).grid(row=0, column=2, **pad)

        frame_out.columnconfigure(1, weight=1)

        # ---- Options ----
        frame_opt = ttk.LabelFrame(self.root, text="Options", padding=8)
        frame_opt.pack(fill="x", padx=8, pady=4)

        ttk.Label(frame_opt, text="Source Lang:").grid(row=0, column=0, sticky="w", **pad)
        self.var_lang_in = tk.StringVar(value="en")
        ttk.Entry(frame_opt, textvariable=self.var_lang_in, width=8).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(frame_opt, text="Target Lang:").grid(row=0, column=2, sticky="w", **pad)
        self.var_lang_out = tk.StringVar(value="zh")
        ttk.Entry(frame_opt, textvariable=self.var_lang_out, width=8).grid(row=0, column=3, sticky="w", **pad)

        ttk.Label(frame_opt, text="QPS:").grid(row=0, column=4, sticky="w", **pad)
        self.var_qps = tk.IntVar(value=4)
        ttk.Entry(frame_opt, textvariable=self.var_qps, width=5).grid(row=0, column=5, sticky="w", **pad)

        self.var_no_mono = tk.BooleanVar()
        ttk.Checkbutton(frame_opt, text="No mono PDF", variable=self.var_no_mono).grid(row=0, column=6, padx=12)

        # ---- Translate Button + Progress ----
        frame_run = ttk.Frame(self.root, padding=8)
        frame_run.pack(fill="x", padx=8, pady=(4, 8))

        self.btn_translate = ttk.Button(frame_run, text="Start Translation", command=self._start_translation)
        self.btn_translate.pack(side="left", padx=4)

        self.progress = ttk.Progressbar(frame_run, mode="indeterminate", length=200)
        self.progress.pack(side="left", padx=8, fill="x", expand=True)

        self.var_status = tk.StringVar(value="Ready")
        ttk.Label(frame_run, textvariable=self.var_status).pack(side="right", padx=4)

        # ---- Log ----
        frame_log = ttk.LabelFrame(self.root, text="Log", padding=8)
        frame_log.pack(fill="both", padx=8, pady=(0, 8), expand=True)

        self.log_text = scrolledtext.ScrolledText(frame_log, height=8, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)

        self.selected_files = []

    def _add_files(self):
        files = filedialog.askopenfilenames(
            title="Select PDF files",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        for f in files:
            if f not in self.selected_files:
                self.selected_files.append(f)
        self._refresh_file_list()

    def _clear_files(self):
        self.selected_files.clear()
        self._refresh_file_list()

    def _refresh_file_list(self):
        self.file_list.config(state="normal")
        self.file_list.delete("1.0", "end")
        for i, f in enumerate(self.selected_files, 1):
            self.file_list.insert("end", f"{i}. {f}\n")
        self.file_list.config(state="disabled")

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select output directory")
        if d:
            self.var_output.set(d)

    def _log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _set_running(self, running):
        self.running = running
        self.btn_translate.config(state="disabled" if running else "normal")
        if running:
            self.progress.start(10)
        else:
            self.progress.stop()

    def _start_translation(self):
        if self.running:
            return
        if not self.selected_files:
            messagebox.showwarning("No files", "Please add at least one PDF file.")
            return
        if not self.var_api_key.get().strip():
            messagebox.showwarning("No API key", "Please enter your API key.")
            return

        self._set_running(True)
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

        thread = threading.Thread(target=self._run_translation, daemon=True)
        thread.start()

    def _run_translation(self):
        proxy_process = None
        try:
            api_key = self.var_api_key.get().strip()
            target_url = self.var_target_url.get().strip()
            model = self.var_model.get().strip()
            output_dir = self.var_output.get().strip()
            lang_in = self.var_lang_in.get().strip()
            lang_out = self.var_lang_out.get().strip()
            qps = self.var_qps.get()
            no_mono = self.var_no_mono.get()
            proxy_port = 8899

            os.makedirs(output_dir, exist_ok=True)

            # Install deps
            self.root.after(0, lambda: self.var_status.set("Checking dependencies..."))
            self._log("[1/3] Checking dependencies...")

            # uv
            uv_ok = subprocess.run(["uv", "--version"], capture_output=True).returncode == 0
            if not uv_ok:
                self._log("  Installing uv...")
                subprocess.run([sys.executable, "-m", "pip", "install", "uv"], check=True)
            self._log("  uv: OK")

            # babeldoc
            bd_check = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True)
            if "babeldoc" not in bd_check.stdout.lower():
                self._log("  Installing BabelDOC (first time, may take a few minutes)...")
                subprocess.run(["uv", "tool", "install", "--python", "3.12", "BabelDOC"], check=True)
            self._log("  BabelDOC: OK")

            # Start proxy
            self.root.after(0, lambda: self.var_status.set("Starting proxy..."))
            self._log("[2/3] Starting proxy...")

            proxy_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.py")

            if is_port_available(proxy_port):
                proxy_process = subprocess.Popen(
                    [sys.executable, proxy_script,
                     "--port", str(proxy_port),
                     "--target-url", target_url,
                     "--api-key", api_key],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if not wait_for_port(proxy_port):
                    raise RuntimeError("Proxy failed to start")
                self._log(f"  Proxy running on port {proxy_port}")
            else:
                self._log(f"  Port {proxy_port} in use, assuming proxy is running")

            # Translate each file
            self.root.after(0, lambda: self.var_status.set("Translating..."))
            self._log("[3/3] Translating files...\n")

            total = len(self.selected_files)
            for idx, pdf_path in enumerate(self.selected_files, 1):
                filename = os.path.basename(pdf_path)
                self._log(f"{'='*50}")
                self._log(f"[{idx}/{total}] {filename}")
                self._log(f"{'='*50}")

                cmd = [
                    "uv", "tool", "run", "babeldoc",
                    "--openai",
                    "--openai-model", model,
                    "--openai-base-url", f"http://localhost:{proxy_port}/v1",
                    "--openai-api-key", api_key,
                    "--lang-in", lang_in,
                    "--lang-out", lang_out,
                    "--qps", str(qps),
                    "--output", output_dir,
                    "--files", pdf_path,
                ]
                if no_mono:
                    cmd.append("--no-mono")

                self._log(f"  Running: {' '.join(cmd)}")
                self._log("")

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                for line in proc.stdout:
                    self._log(line.rstrip())

                proc.wait()

                if proc.returncode == 0:
                    self._log(f"\n  [OK] {filename} done!\n")
                else:
                    self._log(f"\n  [FAIL] {filename} failed (exit code {proc.returncode})\n")

            self.root.after(0, lambda: self.var_status.set("Done"))
            self._log("=" * 50)
            self._log(f"All done! Output: {output_dir}")
            self._log("=" * 50)
            self.root.after(0, lambda: messagebox.showinfo("Done", f"Translation complete!\n\nOutput: {output_dir}"))

        except Exception as e:
            self._log(f"\n[ERROR] {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            if proxy_process:
                self._log("\n[*] Shutting down proxy...")
                proxy_process.terminate()
                try:
                    proxy_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proxy_process.kill()
            self.root.after(0, lambda: self._set_running(False))


def main():
    root = tk.Tk()
    TranslatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
