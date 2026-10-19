"""
Simple Windows control panel for the iPad second screen.

- Pick which monitor to stream (auto-detected list).
- Start / Stop the streaming server with a button.
- Shows the exact address to open on the iPad (fixed hostname + IP).
- Live log from the server.

Run:  python launcher.py     (or double-click start_launcher.bat)

Uses only the standard library (tkinter) plus this project's own modules,
so no extra install is needed.
"""

import queue
import socket
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import mss

import config
import vdd_control


def list_monitors():
    """Return a list of (index, label) for real monitors."""
    out = []
    with mss.MSS() as sct:
        for i, m in enumerate(sct.monitors[1:], start=1):
            label = f"{i}:  {m['width']}x{m['height']}  at ({m['left']},{m['top']})"
            out.append((i, label))
    return out


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def get_tailscale_name():
    """Full Tailscale MagicDNS name (permanent, any-network address), or None."""
    import json
    ts = r"C:\Program Files\Tailscale\tailscale.exe"
    try:
        out = subprocess.run(
            [ts, "status", "--json"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        data = json.loads(out.stdout)
        name = (data.get("Self") or {}).get("DNSName", "")
        return name.rstrip(".") or None
    except Exception:
        return None


class App:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.log_q = queue.Queue()

        root.title("iPad Second Screen")
        root.geometry("820x760")
        root.minsize(720, 680)

        # Scale up all default fonts so everything is easier to read.
        BASE = 14
        try:
            import tkinter.font as tkfont
            for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont",
                         "TkMenuFont", "TkFixedFont", "TkIconFont",
                         "TkTooltipFont", "TkSmallCaptionFont"):
                try:
                    tkfont.nametofont(name).configure(size=BASE)
                except Exception:
                    pass
        except Exception:
            pass

        # ttk widgets use their own styles, not the default font, so set them
        # explicitly or the combobox / labels / frame titles stay tiny.
        try:
            style = ttk.Style()
            style.configure(".", font=("Segoe UI", BASE))
            style.configure("TLabel", font=("Segoe UI", BASE))
            style.configure("TButton", font=("Segoe UI", BASE))
            style.configure("TCombobox", font=("Segoe UI", BASE))
            style.configure("TLabelframe.Label", font=("Segoe UI", BASE, "bold"))
            # The dropdown list popup is a separate option-database setting.
            root.option_add("*TCombobox*Listbox.font", ("Segoe UI", BASE))
        except Exception:
            pass

        pad = {"padx": 20, "pady": 10}

        title = ttk.Label(root, text="iPad Second Screen",
                          font=("Segoe UI", 24, "bold"))
        title.pack(anchor="w", **pad)

        # --- Monitor picker ---
        mframe = ttk.LabelFrame(root, text="1. Choose the monitor to stream")
        mframe.pack(fill="x", **pad)

        self.monitors = list_monitors()
        self.monitor_var = tk.StringVar()
        self.combo = ttk.Combobox(mframe, state="readonly", width=52,
                                  font=("Segoe UI", 13),
                                  values=[lbl for _, lbl in self.monitors])
        self.combo.pack(side="left", padx=10, pady=12)
        # Preselect the configured monitor if present, else the last one.
        default_i = 0
        for pos, (idx, _) in enumerate(self.monitors):
            if idx == config.MONITOR_INDEX:
                default_i = pos
        if self.monitors:
            self.combo.current(default_i)

        ttk.Button(mframe, text="Refresh", command=self.refresh_monitors)\
            .pack(side="left", padx=6)

        # --- Virtual display control ---
        vframe = ttk.LabelFrame(root, text="Virtual iPad display")
        vframe.pack(fill="x", **pad)

        vrow = ttk.Frame(vframe)
        vrow.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(vrow, text="Status:").pack(side="left")
        self.vdd_status = ttk.Label(vrow, text="checking...",
                                    font=("Segoe UI", 13, "bold"))
        self.vdd_status.pack(side="left", padx=(6, 16))
        self.vdd_btn = ttk.Button(vrow, text="Turn ON",
                                  command=self.toggle_vdd)
        self.vdd_btn.pack(side="left")

        self.auto_vdd = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            vframe,
            text="Automatically turn the display ON when streaming starts "
                 "and OFF when it stops",
            variable=self.auto_vdd,
        ).pack(anchor="w", padx=10, pady=(0, 8))

        # --- Address ---
        aframe = ttk.LabelFrame(root, text="2. Open this on your iPad (Safari)")
        aframe.pack(fill="x", **pad)

        ts_name = get_tailscale_name()
        if ts_name:
            self.url_host = f"http://{ts_name}:{config.PORT}"
            primary_caption = "Permanent address (any WiFi) - add this to Home Screen:"
        else:
            self.url_host = f"http://{socket.gethostname().lower()}:{config.PORT}"
            primary_caption = "Hostname address:"
        self.url_ip = f"http://{get_local_ip()}:{config.PORT}"

        ttk.Label(aframe, text=primary_caption,
                  foreground="#444").pack(anchor="w", padx=10, pady=(8, 0))
        self.addr_label = ttk.Label(aframe, text=self.url_host,
                                    font=("Consolas", 18, "bold"),
                                    foreground="#1565c0")
        self.addr_label.pack(anchor="w", padx=10, pady=(0, 4))
        ttk.Label(aframe, text=f"or local IP (same WiFi only):  {self.url_ip}",
                  font=("Consolas", 12),
                  foreground="#666").pack(anchor="w", padx=10, pady=(0, 6))
        ttk.Button(aframe, text="Copy address",
                   command=self.copy_addr).pack(anchor="w", padx=8, pady=(0, 8))

        # --- Start / Stop ---
        try:
            ttk.Style().configure("Big.TButton", font=("Segoe UI", 14, "bold"),
                                   padding=(16, 10))
        except Exception:
            pass
        bframe = ttk.Frame(root)
        bframe.pack(fill="x", **pad)
        self.start_btn = ttk.Button(bframe, text="Start streaming",
                                    style="Big.TButton", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(bframe, text="Stop", style="Big.TButton",
                                   command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        self.status = ttk.Label(bframe, text="Stopped",
                                font=("Segoe UI", 13, "bold"),
                                foreground="#b00")
        self.status.pack(side="left", padx=12)

        # --- Log ---
        lframe = ttk.LabelFrame(root, text="Server log")
        lframe.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(lframe, height=10, wrap="word",
                           font=("Consolas", 11),
                           bg="#111", fg="#ddd", insertbackground="#ddd")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)
        self.log.configure(state="disabled")

        hint = ("Tip: on the iPad, use Safari's Share -> Add to Home Screen to "
                "get a full-screen app icon.")
        ttk.Label(root, text=hint, foreground="#666", wraplength=520)\
            .pack(anchor="w", padx=14, pady=(0, 10))

        self._vdd_state = None
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(150, self.drain_log)
        self.refresh_vdd_status()

    def refresh_monitors(self):
        self.monitors = list_monitors()
        self.combo["values"] = [lbl for _, lbl in self.monitors]
        if self.monitors:
            self.combo.current(len(self.monitors) - 1)

    # ---- Virtual display state ----
    def refresh_vdd_status(self):
        """Query the driver state in a thread and update the label."""
        def worker():
            state = vdd_control.get_state()
            self.root.after(0, lambda: self._apply_vdd_status(state))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_vdd_status(self, state):
        if state == "enabled":
            self.vdd_status.config(text="ON", foreground="#080")
            self.vdd_btn.config(text="Turn OFF", state="normal")
        elif state == "disabled":
            self.vdd_status.config(text="OFF", foreground="#b00")
            self.vdd_btn.config(text="Turn ON", state="normal")
        else:
            self.vdd_status.config(text="not installed", foreground="#b00")
            self.vdd_btn.config(text="Turn ON", state="disabled")
        self._vdd_state = state

    def toggle_vdd(self):
        state = getattr(self, "_vdd_state", "disabled")
        turning_on = state != "enabled"
        self.vdd_btn.config(state="disabled")
        self.vdd_status.config(text="working... (approve the admin prompt)",
                               foreground="#a60")

        def worker():
            ok = vdd_control.enable() if turning_on else vdd_control.disable()
            def done():
                if not ok:
                    self.append_log(
                        "Could not change the virtual display. Make sure you "
                        "approved the admin (UAC) prompt.\n")
                self.refresh_vdd_status()
                if turning_on and ok:
                    # Windows needs a moment to attach the monitor.
                    self.root.after(1500, self.refresh_monitors)
            self.root.after(0, done)
        threading.Thread(target=worker, daemon=True).start()

    def copy_addr(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.url_host)
        self.append_log(f"Copied: {self.url_host}\n")

    def selected_index(self):
        pos = self.combo.current()
        if pos < 0 or pos >= len(self.monitors):
            return config.MONITOR_INDEX
        return self.monitors[pos][0]

    def start(self):
        if self.proc:
            return
        # If auto-manage is on and the display is off, turn it on first,
        # then start streaming once it's ready.
        if self.auto_vdd.get() and getattr(self, "_vdd_state", None) == "disabled":
            self.append_log("Turning on the virtual display "
                            "(approve the admin prompt)...\n")
            self.start_btn.config(state="disabled")

            def worker():
                ok = vdd_control.enable()
                def done():
                    self.refresh_vdd_status()
                    self.start_btn.config(state="normal")
                    if ok:
                        # Give Windows a moment to attach the monitor, then stream.
                        self.root.after(1800, self._begin_stream)
                    else:
                        self.append_log("Display did not turn on; not streaming.\n")
                self.root.after(0, done)
            threading.Thread(target=worker, daemon=True).start()
            return

        self._begin_stream()

    def _free_ports(self):
        """Kill any stale process still holding our HTTP/WS ports."""
        ports = f"{config.PORT},{config.PORT + 1}"
        ps = (
            f"Get-NetTCPConnection -LocalPort {ports} -State Listen "
            f"-ErrorAction SilentlyContinue | "
            f"Select-Object -ExpandProperty OwningProcess -Unique | "
            f"ForEach-Object {{ Stop-Process -Id $_ -Force "
            f"-ErrorAction SilentlyContinue }}"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    def _begin_stream(self):
        if self.proc:
            return
        self._free_ports()
        self.refresh_monitors()
        idx = self.selected_index()
        # Launch server.py with MONITOR_INDEX overridden via an env var.
        import os
        env = dict(os.environ)
        env["SECONDSCREEN_MONITOR_INDEX"] = str(idx)

        try:
            self.proc = subprocess.Popen(
                [sys.executable, "server.py"],
                cwd=str(__import__("pathlib").Path(__file__).parent),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            messagebox.showerror("Failed to start", str(e))
            self.proc = None
            return

        threading.Thread(target=self._reader, daemon=True).start()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.combo.config(state="disabled")
        self.status.config(text=f"Running (monitor {idx})", foreground="#080")
        self.append_log(f"Started, streaming monitor {idx}.\n")

    def _reader(self):
        for line in self.proc.stdout:
            self.log_q.put(line)
        self.log_q.put("[server process ended]\n")

    def stop(self):
        if not self.proc:
            return
        try:
            self.proc.terminate()
        except Exception:
            pass
        self.proc = None
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.combo.config(state="readonly")
        self.status.config(text="Stopped", foreground="#b00")
        self.append_log("Stopped.\n")

        # Auto-turn-off the virtual display so no phantom screen is left behind.
        if self.auto_vdd.get() and getattr(self, "_vdd_state", None) == "enabled":
            self.append_log("Turning off the virtual display "
                            "(approve the admin prompt)...\n")

            def worker():
                vdd_control.disable()
                self.root.after(0, self.refresh_vdd_status)
            threading.Thread(target=worker, daemon=True).start()

    def drain_log(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                self.append_log(line)
        except queue.Empty:
            pass
        self.root.after(150, self.drain_log)

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_close(self):
        # Stop the server process directly.
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None
        # If auto-manage is on and the display is on, disable it synchronously
        # so we don't leave a phantom screen after the window is gone.
        if self.auto_vdd.get() and getattr(self, "_vdd_state", None) == "enabled":
            try:
                vdd_control.disable()
            except Exception:
                pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()
