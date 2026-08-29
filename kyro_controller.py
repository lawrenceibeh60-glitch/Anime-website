#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KYRO ULTIMATE CONTROLLER v4.0
Single file - Password protected - Owner & Staff modes

FEATURES:
- Password login (5 attempts max)
- "Send unlock code to admin" when locked out
- Admin receives unlock codes, can unlock + set new password
- OWNER mode: Full control + AI superpowers
- STAFF mode: View only + limited controls
- All previous features merged

SETUP:
1. Set KYRO_PASSWORD env var on Render (default: "kyro2026")
2. Set KYRO_OWNER_KEY and KYRO_STAFF_KEY env vars
3. Run: python kyro_controller.py
4. Enter app URL, password, then choose Owner or Staff mode
"""

import requests
import json
import time
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
from datetime import datetime

# ==================== CONFIG ====================
APP_URL = "https://anime-website-sjz2.onrender.com"
OWNER_KEY = ""
STAFF_KEY = ""
USER_MODE = ""  # "owner" or "staff"
LOGGED_IN = False
# ================================================

# Colors
BG = "#050714"
CARD = "#0a0f2e"
BORDER = "#1a237e"
BLUE = "#2962ff"
GREEN = "#00d26a"
RED = "#ef5350"
YELLOW = "#ffd600"
TEXT = "#e3f2fd"
DIM = "#90a4ae"
MAGENTA = "#d500f9"
CYAN = "#00bcd4"
ORANGE = "#ff9800"


class PasswordScreen:
    """Password login screen with 5-attempt limit and unlock request"""
    def __init__(self, root, on_success):
        self.root = root
        self.on_success = on_success
        self.attempts = 0
        self.max_attempts = 5
        self.locked = False

        self.window = tk.Toplevel(root)
        self.window.title("KYRO - Secure Login")
        self.window.geometry("500x400")
        self.window.configure(bg=BG)
        self.window.resizable(False, False)
        self.window.transient(root)
        self.window.grab_set()

        self.build_ui()
        self.check_remaining()

    def build_ui(self):
        # Title
        tk.Label(self.window, text="KYRO", font=("Segoe UI", 32, "bold"),
                 fg=BLUE, bg=BG).pack(pady=(30, 0))
        tk.Label(self.window, text="SECURE LOGIN", font=("Segoe UI", 14),
                 fg=YELLOW, bg=BG).pack()

        # Password entry
        frame = tk.Frame(self.window, bg=BG)
        frame.pack(pady=30)

        tk.Label(frame, text="Enter Password:", font=("Segoe UI", 12),
                 fg=TEXT, bg=BG).pack(anchor=tk.W)

        self.entry_pwd = tk.Entry(frame, font=("Segoe UI", 16), width=25,
                                   bg=CARD, fg=TEXT, insertbackground=TEXT,
                                   show="*", justify="center")
        self.entry_pwd.pack(pady=10)
        self.entry_pwd.bind("<Return>", lambda e: self.check_password())
        self.entry_pwd.focus()

        # Attempts counter
        self.lbl_attempts = tk.Label(frame, text="Attempts remaining: 5",
                                      font=("Segoe UI", 10), fg=GREEN, bg=BG)
        self.lbl_attempts.pack()

        # Login button
        self.btn_login = tk.Button(frame, text="LOGIN", font=("Segoe UI", 14, "bold"),
                                    bg=BLUE, fg="white", width=20,
                                    command=self.check_password, cursor="hand2",
                                    relief=tk.FLAT, activebackground="#1a5fd1")
        self.btn_login.pack(pady=15)

        # Status message
        self.lbl_status = tk.Label(frame, text="", font=("Segoe UI", 10),
                                    fg=RED, bg=BG)
        self.lbl_status.pack()

        # Unlock request section (hidden by default)
        self.unlock_frame = tk.Frame(self.window, bg=BG)

        tk.Label(self.unlock_frame, text="Account Locked", font=("Segoe UI", 14, "bold"),
                 fg=RED, bg=BG).pack(pady=(10, 5))

        tk.Label(self.unlock_frame, text="Too many failed attempts.",
                 font=("Segoe UI", 10), fg=DIM, bg=BG).pack()

        self.btn_unlock = tk.Button(self.unlock_frame, text="Send Unlock Request to Admin",
                                     font=("Segoe UI", 11, "bold"),
                                     bg=ORANGE, fg="white", width=30,
                                     command=self.send_unlock_request, cursor="hand2",
                                     relief=tk.FLAT)
        self.btn_unlock.pack(pady=15)

        self.lbl_unlock_status = tk.Label(self.unlock_frame, text="",
                                           font=("Segoe UI", 10), fg=GREEN, bg=BG)
        self.lbl_unlock_status.pack()

    def check_remaining(self):
        """Check remaining attempts from server"""
        def do_check():
            try:
                r = requests.get(f"{APP_URL}/api/password/remaining", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    remaining = data.get("remaining", 5)
                    locked = data.get("locked", False)
                    self.attempts = 5 - remaining
                    self.update_attempts_display(remaining)
                    if locked:
                        self.show_locked()
            except:
                pass
        threading.Thread(target=do_check, daemon=True).start()

    def update_attempts_display(self, remaining):
        color = GREEN if remaining > 2 else YELLOW if remaining > 0 else RED
        self.lbl_attempts.config(text=f"Attempts remaining: {remaining}", fg=color)

    def check_password(self):
        if self.locked:
            return

        pwd = self.entry_pwd.get().strip()
        if not pwd:
            self.lbl_status.config(text="Enter a password!")
            return

        self.btn_login.config(text="Checking...", state=tk.DISABLED)
        self.window.update()

        def do_check():
            try:
                r = requests.post(f"{APP_URL}/api/password/check",
                                  json={"password": pwd}, timeout=10)
                data = r.json()

                if data.get("success"):
                    self.window.after(0, self.login_success)
                else:
                    remaining = data.get("remaining", 0)
                    locked = data.get("locked", False)
                    self.window.after(0, lambda: self.login_failed(remaining, locked))
            except Exception as e:
                self.window.after(0, lambda: self.show_error(str(e)))

        threading.Thread(target=do_check, daemon=True).start()

    def login_success(self):
        global LOGGED_IN
        LOGGED_IN = True
        self.window.destroy()
        self.on_success()

    def login_failed(self, remaining, locked):
        self.attempts = 5 - remaining
        self.update_attempts_display(remaining)
        self.lbl_status.config(text="Wrong password!")
        self.entry_pwd.delete(0, tk.END)
        self.btn_login.config(text="LOGIN", state=tk.NORMAL)

        if locked:
            self.show_locked()

    def show_locked(self):
        self.locked = True
        self.entry_pwd.config(state=tk.DISABLED)
        self.btn_login.config(state=tk.DISABLED, text="LOCKED")
        self.lbl_status.config(text="ACCOUNT LOCKED")
        self.unlock_frame.pack(pady=10)

    def show_error(self, msg):
        self.lbl_status.config(text=f"Error: {msg}")
        self.btn_login.config(text="LOGIN", state=tk.NORMAL)

    def send_unlock_request(self):
        self.btn_unlock.config(text="Sending...", state=tk.DISABLED)

        def do_send():
            try:
                r = requests.post(f"{APP_URL}/api/password/unlock-request",
                                  json={"device": "KYRO Controller"}, timeout=10)
                data = r.json()
                self.window.after(0, lambda: self.unlock_sent(data))
            except Exception as e:
                self.window.after(0, lambda: self.unlock_error(str(e)))

        threading.Thread(target=do_send, daemon=True).start()

    def unlock_sent(self, data):
        self.btn_unlock.config(text="Request Sent!", bg=GREEN)
        self.lbl_unlock_status.config(text="Admin has been notified.\nWait for admin to unlock you.")

    def unlock_error(self, msg):
        self.btn_unlock.config(text="Send Unlock Request to Admin", state=tk.NORMAL)
        self.lbl_unlock_status.config(text=f"Failed: {msg}", fg=RED)


class ModeSelector:
    """Choose Owner or Staff mode after password login"""
    def __init__(self, root, on_select):
        self.root = root
        self.on_select = on_select

        self.window = tk.Toplevel(root)
        self.window.title("KYRO - Select Mode")
        self.window.geometry("500x350")
        self.window.configure(bg=BG)
        self.window.resizable(False, False)
        self.window.transient(root)
        self.window.grab_set()

        tk.Label(self.window, text="KYRO", font=("Segoe UI", 28, "bold"),
                 fg=BLUE, bg=BG).pack(pady=(30, 0))
        tk.Label(self.window, text="SELECT YOUR MODE", font=("Segoe UI", 12),
                 fg=DIM, bg=BG).pack()

        # Owner button
        owner_frame = tk.Frame(self.window, bg=CARD, bd=2, relief=tk.SOLID)
        owner_frame.pack(fill=tk.X, padx=40, pady=15)

        tk.Label(owner_frame, text="OWNER", font=("Segoe UI", 18, "bold"),
                 fg=YELLOW, bg=CARD).pack(pady=(10, 0))
        tk.Label(owner_frame, text="Full Control + AI Superpowers",
                 font=("Segoe UI", 10), fg=DIM, bg=CARD).pack()
        tk.Label(owner_frame, text="Server control, AI diagnostics, code fix, assistant",
                 font=("Segoe UI", 9), fg=DIM, bg=CARD).pack(pady=(0, 10))

        tk.Button(owner_frame, text="ENTER AS OWNER", font=("Segoe UI", 12, "bold"),
                  bg=BLUE, fg="white", command=lambda: self.select("owner"),
                  cursor="hand2", relief=tk.FLAT).pack(fill=tk.X, padx=20, pady=10)

        # Staff button
        staff_frame = tk.Frame(self.window, bg=CARD, bd=2, relief=tk.SOLID)
        staff_frame.pack(fill=tk.X, padx=40, pady=5)

        tk.Label(staff_frame, text="STAFF", font=("Segoe UI", 18, "bold"),
                 fg=GREEN, bg=CARD).pack(pady=(10, 0))
        tk.Label(staff_frame, text="View Only + Limited Controls",
                 font=("Segoe UI", 10), fg=DIM, bg=CARD).pack()
        tk.Label(staff_frame, text="View visitors, analytics, broadcasts (no server control)",
                 font=("Segoe UI", 9), fg=DIM, bg=CARD).pack(pady=(0, 10))

        tk.Button(staff_frame, text="ENTER AS STAFF", font=("Segoe UI", 12, "bold"),
                  bg=GREEN, fg="white", command=lambda: self.select("staff"),
                  cursor="hand2", relief=tk.FLAT).pack(fill=tk.X, padx=20, pady=10)

    def select(self, mode):
        global USER_MODE
        USER_MODE = mode
        self.window.destroy()
        self.on_select(mode)


class KYROController:
    """Main controller - adapts based on owner/staff mode"""
    def __init__(self, root):
        self.root = root
        self.root.title(f"KYRO CONTROLLER - {USER_MODE.upper()}")
        self.root.geometry("1100x800")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self.monitoring = False
        self.server_online = False
        self.is_owner = (USER_MODE == "owner")

        self.setup_ui()
        self.check_connection()

    def setup_ui(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ===== HEADER =====
        header = tk.Frame(main, bg=BG)
        header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(header, text="KYRO", font=("Segoe UI", 26, "bold"),
                 fg=BLUE, bg=BG).pack(side=tk.LEFT)
        tk.Label(header, text=USER_MODE.upper(), font=("Segoe UI", 26, "bold"),
                 fg=YELLOW if self.is_owner else GREEN, bg=BG).pack(side=tk.LEFT, padx=(5, 0))

        if self.is_owner:
            tk.Label(header, text="THE BOSS", font=("Segoe UI", 10),
                     fg=MAGENTA, bg=BG).pack(side=tk.LEFT, padx=(10, 0))
        else:
            tk.Label(header, text="VIEW ONLY", font=("Segoe UI", 10),
                     fg=DIM, bg=BG).pack(side=tk.LEFT, padx=(10, 0))

        self.status_dot = tk.Canvas(header, width=16, height=16, bg=BG, highlightthickness=0)
        self.status_dot.pack(side=tk.RIGHT)
        self.status_circle = self.status_dot.create_oval(2, 2, 14, 14, fill=DIM)
        self.status_label = tk.Label(header, text="Checking...", font=("Segoe UI", 12), fg=DIM, bg=BG)
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # ===== POWER PANEL (OWNER ONLY) =====
        if self.is_owner:
            power = tk.LabelFrame(main, text=" SERVER CONTROLS ", font=("Segoe UI", 12, "bold"),
                                   fg=BLUE, bg=CARD, bd=2)
            power.pack(fill=tk.X, pady=(0, 10))

            p_inner = tk.Frame(power, bg=CARD)
            p_inner.pack(fill=tk.X, padx=10, pady=10)

            self.btn_start = tk.Button(p_inner, text="START\nSERVER", font=("Segoe UI", 14, "bold"),
                                        bg=GREEN, fg="white", width=12, height=2,
                                        command=self.start_server, cursor="hand2",
                                        activebackground="#00b248", relief=tk.FLAT)
            self.btn_start.pack(side=tk.LEFT, padx=5)

            self.btn_stop = tk.Button(p_inner, text="STOP\nSERVER", font=("Segoe UI", 14, "bold"),
                                       bg=RED, fg="white", width=12, height=2,
                                       command=self.stop_server, cursor="hand2",
                                       activebackground="#d32f2f", relief=tk.FLAT)
            self.btn_stop.pack(side=tk.LEFT, padx=5)

            self.btn_restart = tk.Button(p_inner, text="RESTART\nSERVER", font=("Segoe UI", 14, "bold"),
                                          bg=YELLOW, fg="black", width=12, height=2,
                                          command=self.restart_server, cursor="hand2",
                                          activebackground="#fbc02d", relief=tk.FLAT)
            self.btn_restart.pack(side=tk.LEFT, padx=5)

            # Unlock codes button (owner only)
            self.btn_unlocks = tk.Button(p_inner, text="Unlock\nRequests", font=("Segoe UI", 11, "bold"),
                                          bg=ORANGE, fg="white", width=10, height=2,
                                          command=self.show_unlock_codes, cursor="hand2",
                                          relief=tk.FLAT)
            self.btn_unlocks.pack(side=tk.LEFT, padx=5)

            qs = tk.Frame(p_inner, bg=CARD)
            qs.pack(side=tk.RIGHT, padx=20)

            self.lbl_visitors = tk.Label(qs, text="Total: 0", font=("Segoe UI", 14), fg=TEXT, bg=CARD)
            self.lbl_visitors.pack(anchor=tk.E)
            self.lbl_online = tk.Label(qs, text="Online: 0", font=("Segoe UI", 14), fg=GREEN, bg=CARD)
            self.lbl_online.pack(anchor=tk.E)
            self.lbl_errors = tk.Label(qs, text="Errors: 0", font=("Segoe UI", 14), fg=RED, bg=CARD)
            self.lbl_errors.pack(anchor=tk.E)
        else:
            # Staff stats bar
            stats = tk.Frame(main, bg=CARD, bd=1, relief=tk.SOLID)
            stats.pack(fill=tk.X, pady=(0, 10))

            self.lbl_visitors = tk.Label(stats, text="Total: 0", font=("Segoe UI", 14), fg=TEXT, bg=CARD)
            self.lbl_visitors.pack(side=tk.LEFT, padx=20, pady=10)
            self.lbl_online = tk.Label(stats, text="Online: 0", font=("Segoe UI", 14), fg=GREEN, bg=CARD)
            self.lbl_online.pack(side=tk.LEFT, padx=20, pady=10)
            self.lbl_errors = tk.Label(stats, text="Errors: 0", font=("Segoe UI", 14), fg=RED, bg=CARD)
            self.lbl_errors.pack(side=tk.LEFT, padx=20, pady=10)

        # ===== NOTEBOOK =====
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"),
                        background=CARD, foreground=DIM, padding=10)
        style.map("TNotebook.Tab", background=[("selected", BLUE)],
                  foreground=[("selected", "white")])
        style.configure("TFrame", background=BG)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Visitors (both)
        self.tab_visitors = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_visitors, text="  Visitors  ")
        self.setup_visitors_tab()

        # Tab 2: AI Diagnostics (both, but owner can trigger)
        self.tab_ai = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_ai, text="  AI Diagnostics  ")
        self.setup_ai_tab()

        # Tab 3: AI Code Fix (OWNER ONLY)
        if self.is_owner:
            self.tab_code = tk.Frame(self.notebook, bg=BG)
            self.notebook.add(self.tab_code, text="  AI Code Fix  ")
            self.setup_code_tab()

        # Tab 4: AI Assistant (OWNER ONLY)
        if self.is_owner:
            self.tab_assistant = tk.Frame(self.notebook, bg=BG)
            self.notebook.add(self.tab_assistant, text="  AI Assistant  ")
            self.setup_assistant_tab()

        # Tab 5: Analytics (both)
        self.tab_analytics = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_analytics, text="  Analytics  ")
        self.setup_analytics_tab()

        # Tab 6: Broadcast (both)
        self.tab_broadcast = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_broadcast, text="  Broadcast  ")
        self.setup_broadcast_tab()

        # Tab 7: Logs (OWNER ONLY)
        if self.is_owner:
            self.tab_logs = tk.Frame(self.notebook, bg=BG)
            self.notebook.add(self.tab_logs, text="  Logs  ")
            self.setup_logs_tab()

        # Bottom bar
        bottom = tk.Frame(main, bg=BG)
        bottom.pack(fill=tk.X, pady=(10, 0))

        self.lbl_last_update = tk.Label(bottom, text="Last update: Never",
                                         font=("Segoe UI", 9), fg=DIM, bg=BG)
        self.lbl_last_update.pack(side=tk.LEFT)

        self.btn_monitor = tk.Button(bottom, text="Start Live Monitor", font=("Segoe UI", 10),
                                      bg=CARD, fg=TEXT, command=self.toggle_monitor,
                                      cursor="hand2", relief=tk.FLAT)
        self.btn_monitor.pack(side=tk.RIGHT, padx=5)

        tk.Button(bottom, text="Refresh All", font=("Segoe UI", 10),
                  bg=BLUE, fg="white", command=self.refresh_all,
                  cursor="hand2", relief=tk.FLAT).pack(side=tk.RIGHT)

    def setup_visitors_tab(self):
        toolbar = tk.Frame(self.tab_visitors, bg=BG)
        toolbar.pack(fill=tk.X, pady=(0, 5))

        tk.Label(toolbar, text="Filter:", font=("Segoe UI", 10), fg=DIM, bg=BG).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar(value="all")
        for text, val in [("All", "all"), ("Search", "search"), ("Watch", "watch"),
                          ("Download", "download"), ("Chat", "chat")]:
            tk.Radiobutton(toolbar, text=text, variable=self.filter_var, value=val,
                           font=("Segoe UI", 9), fg=TEXT, bg=BG,
                           selectcolor=BLUE, command=self.refresh_visitors).pack(side=tk.LEFT, padx=5)

        columns = ("time", "ip", "device", "type", "action", "details")
        self.tree_visitors = ttk.Treeview(self.tab_visitors, columns=columns,
                                           show="headings", height=20)
        for c in columns:
            self.tree_visitors.heading(c, text=c.title())
        self.tree_visitors.column("time", width=70)
        self.tree_visitors.column("ip", width=120)
        self.tree_visitors.column("device", width=150)
        self.tree_visitors.column("type", width=70)
        self.tree_visitors.column("action", width=80)
        self.tree_visitors.column("details", width=350)

        sb = ttk.Scrollbar(self.tab_visitors, orient=tk.VERTICAL, command=self.tree_visitors.yview)
        self.tree_visitors.configure(yscrollcommand=sb.set)
        self.tree_visitors.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        style = ttk.Style()
        style.configure("Treeview", background=CARD, foreground=TEXT,
                        fieldbackground=CARD, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=BORDER, foreground=TEXT,
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", BLUE)])

    def setup_ai_tab(self):
        if self.is_owner:
            # Owner can trigger AI analysis
            btn_frame = tk.Frame(self.tab_ai, bg=BG)
            btn_frame.pack(fill=tk.X, pady=5)

            tk.Button(btn_frame, text="Analyze Errors with AI", font=("Segoe UI", 11, "bold"),
                      bg=MAGENTA, fg="white", command=self.analyze_errors_ai,
                      cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

            tk.Button(btn_frame, text="AI Site Diagnosis", font=("Segoe UI", 11, "bold"),
                      bg=CYAN, fg="white", command=self.ai_site_diagnosis,
                      cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

            tk.Button(btn_frame, text="Refresh", font=("Segoe UI", 10),
                      bg=CARD, fg=TEXT, command=self.refresh_errors,
                      cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)
        else:
            tk.Label(self.tab_ai, text="AI Error Analysis (View Only)",
                     font=("Segoe UI", 14, "bold"), fg=MAGENTA, bg=BG).pack(pady=10)
            tk.Label(self.tab_ai, text="Owner must trigger AI analysis. You can view results.",
                     font=("Segoe UI", 10), fg=DIM, bg=BG).pack()
            tk.Button(self.tab_ai, text="Refresh Errors", font=("Segoe UI", 10),
                      bg=CARD, fg=TEXT, command=self.refresh_errors,
                      cursor="hand2", relief=tk.FLAT).pack(pady=5)

        # Error list
        err_frame = tk.LabelFrame(self.tab_ai, text=" CAUGHT ERRORS ",
                                   font=("Segoe UI", 11, "bold"),
                                   fg=RED, bg=CARD, bd=2)
        err_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.txt_errors = scrolledtext.ScrolledText(
            err_frame, bg=CARD, fg=TEXT, font=("Consolas", 10),
            wrap=tk.WORD, state=tk.DISABLED, height=8
        )
        self.txt_errors.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # AI Results
        result_frame = tk.LabelFrame(self.tab_ai, text=" AI ANALYSIS ",
                                      font=("Segoe UI", 11, "bold"),
                                      fg=GREEN, bg=CARD, bd=2)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.txt_ai_results = scrolledtext.ScrolledText(
            result_frame, bg=CARD, fg=TEXT, font=("Consolas", 10),
            wrap=tk.WORD, state=tk.DISABLED, height=8
        )
        self.txt_ai_results.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_code_tab(self):
        input_frame = tk.LabelFrame(self.tab_code, text=" PASTE YOUR CODE ",
                                     font=("Segoe UI", 11, "bold"),
                                     fg=YELLOW, bg=CARD, bd=2)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.txt_code_input = scrolledtext.ScrolledText(
            input_frame, bg=CARD, fg=TEXT, font=("Consolas", 11),
            wrap=tk.NONE, height=10
        )
        self.txt_code_input.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        ctrl = tk.Frame(self.tab_code, bg=BG)
        ctrl.pack(fill=tk.X, pady=5)

        tk.Label(ctrl, text="Issue (optional):", font=("Segoe UI", 10), fg=DIM, bg=BG).pack(side=tk.LEFT)
        self.entry_issue = tk.Entry(ctrl, font=("Segoe UI", 10), width=40,
                                     bg=CARD, fg=TEXT, insertbackground=TEXT)
        self.entry_issue.pack(side=tk.LEFT, padx=5)

        tk.Button(ctrl, text="AI FIX MY CODE", font=("Segoe UI", 12, "bold"),
                  bg=MAGENTA, fg="white", command=self.ai_fix_code,
                  cursor="hand2", relief=tk.FLAT).pack(side=tk.RIGHT, padx=5)

        output_frame = tk.LabelFrame(self.tab_code, text=" AI FIXED CODE ",
                                      font=("Segoe UI", 11, "bold"),
                                      fg=GREEN, bg=CARD, bd=2)
        output_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.txt_code_output = scrolledtext.ScrolledText(
            output_frame, bg=CARD, fg=TEXT, font=("Consolas", 11),
            wrap=tk.NONE, state=tk.DISABLED, height=10
        )
        self.txt_code_output.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_assistant_tab(self):
        chat_frame = tk.Frame(self.tab_assistant, bg=BG)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.txt_chat = scrolledtext.ScrolledText(
            chat_frame, bg=CARD, fg=TEXT, font=("Segoe UI", 11),
            wrap=tk.WORD, state=tk.DISABLED, height=18
        )
        self.txt_chat.pack(fill=tk.BOTH, expand=True)

        input_frame = tk.Frame(self.tab_assistant, bg=BG)
        input_frame.pack(fill=tk.X, pady=5)

        self.entry_chat = tk.Entry(input_frame, font=("Segoe UI", 12), width=70,
                                    bg=CARD, fg=TEXT, insertbackground=TEXT)
        self.entry_chat.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.entry_chat.bind("<Return>", lambda e: self.ask_ai())

        tk.Button(input_frame, text="ASK AI", font=("Segoe UI", 12, "bold"),
                  bg=MAGENTA, fg="white", command=self.ask_ai,
                  cursor="hand2", relief=tk.FLAT).pack(side=tk.RIGHT, padx=5)

        quick = tk.Frame(self.tab_assistant, bg=BG)
        quick.pack(fill=tk.X, pady=5)

        questions = [
            "How is my site doing?",
            "What are people searching?",
            "Any errors I should fix?",
            "How to get more visitors?",
            "Is AnimeHeaven working?"
        ]
        for q in questions:
            tk.Button(quick, text=q, font=("Segoe UI", 9),
                      bg=CARD, fg=DIM, command=lambda x=q: self.quick_ask(x),
                      cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=3)

    def setup_analytics_tab(self):
        cards = tk.Frame(self.tab_analytics, bg=BG)
        cards.pack(fill=tk.X, pady=10)

        self.analytics_cards = {}
        for title, val, color in [("Visits", "0", BLUE), ("Searches", "0", YELLOW),
                                   ("Watches", "0", GREEN), ("Downloads", "0", RED)]:
            card = tk.Frame(cards, bg=CARD, bd=1, relief=tk.SOLID)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
            tk.Label(card, text=title, font=("Segoe UI", 10), fg=DIM, bg=CARD).pack(pady=(10, 0))
            lbl = tk.Label(card, text=val, font=("Segoe UI", 28, "bold"), fg=color, bg=CARD)
            lbl.pack(pady=(0, 10))
            self.analytics_cards[title] = lbl

        searches_frame = tk.LabelFrame(self.tab_analytics, text=" TOP SEARCHES ",
                                        font=("Segoe UI", 11, "bold"),
                                        fg=YELLOW, bg=CARD, bd=2)
        searches_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.txt_top_searches = scrolledtext.ScrolledText(
            searches_frame, bg=CARD, fg=TEXT, font=("Segoe UI", 10),
            wrap=tk.WORD, state=tk.DISABLED, height=10
        )
        self.txt_top_searches.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        devices_frame = tk.LabelFrame(self.tab_analytics, text=" DEVICES ",
                                       font=("Segoe UI", 11, "bold"),
                                       fg=BLUE, bg=CARD, bd=2)
        devices_frame.pack(fill=tk.X, pady=(0, 10))

        self.txt_devices = scrolledtext.ScrolledText(
            devices_frame, bg=CARD, fg=TEXT, font=("Segoe UI", 10),
            wrap=tk.WORD, state=tk.DISABLED, height=6
        )
        self.txt_devices.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_broadcast_tab(self):
        input_frame = tk.Frame(self.tab_broadcast, bg=BG)
        input_frame.pack(fill=tk.X, pady=10)

        tk.Label(input_frame, text="Message to ALL visitors:", font=("Segoe UI", 12, "bold"),
                 fg=YELLOW, bg=BG).pack(anchor=tk.W)

        self.entry_broadcast = tk.Entry(input_frame, font=("Segoe UI", 14), width=60,
                                         bg=CARD, fg=TEXT, insertbackground=TEXT)
        self.entry_broadcast.pack(fill=tk.X, pady=5)
        self.entry_broadcast.bind("<Return>", lambda e: self.send_broadcast())

        tk.Button(input_frame, text="SEND BROADCAST", font=("Segoe UI", 14, "bold"),
                  bg=YELLOW, fg="black", command=self.send_broadcast,
                  cursor="hand2", relief=tk.FLAT).pack(anchor=tk.E, pady=5)

        history_frame = tk.LabelFrame(self.tab_broadcast, text=" SENT MESSAGES ",
                                       font=("Segoe UI", 11, "bold"),
                                       fg=BLUE, bg=CARD, bd=2)
        history_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.txt_broadcast_history = scrolledtext.ScrolledText(
            history_frame, bg=CARD, fg=TEXT, font=("Segoe UI", 10),
            wrap=tk.WORD, state=tk.DISABLED
        )
        self.txt_broadcast_history.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_logs_tab(self):
        self.txt_logs = scrolledtext.ScrolledText(
            self.tab_logs, bg=CARD, fg=TEXT, font=("Consolas", 10),
            wrap=tk.WORD
        )
        self.txt_logs.pack(fill=tk.BOTH, expand=True, pady=10)

        btn_frame = tk.Frame(self.tab_logs, bg=BG)
        btn_frame.pack(fill=tk.X)

        tk.Button(btn_frame, text="Export Logs", font=("Segoe UI", 10),
                  bg=BLUE, fg="white", command=self.export_logs,
                  cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

        tk.Button(btn_frame, text="Export Errors", font=("Segoe UI", 10),
                  bg=RED, fg="white", command=self.export_errors,
                  cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

        tk.Button(btn_frame, text="Change Password", font=("Segoe UI", 10),
                  bg=ORANGE, fg="white", command=self.change_password,
                  cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

        tk.Button(btn_frame, text="Clear", font=("Segoe UI", 10),
                  bg=CARD, fg=TEXT, command=self.clear_logs,
                  cursor="hand2", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

        self.log("KYRO ULTIMATE CONTROLLER v4.0")
        self.log(f"Logged in as: {USER_MODE.upper()}")

    def log(self, msg):
        if not self.is_owner:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt_logs.configure(state=tk.NORMAL)
        self.txt_logs.insert(tk.END, f"[{ts}] {msg}\n")
        self.txt_logs.see(tk.END)
        self.txt_logs.configure(state=tk.DISABLED)

    def clear_logs(self):
        if not self.is_owner:
            return
        self.txt_logs.configure(state=tk.NORMAL)
        self.txt_logs.delete(1.0, tk.END)
        self.txt_logs.configure(state=tk.DISABLED)

    def get_admin_key(self):
        return OWNER_KEY if self.is_owner else STAFF_KEY

    def api_get(self, endpoint, params=None):
        headers = {"X-Admin-Key": self.get_admin_key()}
        try:
            r = requests.get(f"{APP_URL}{endpoint}", headers=headers, params=params, timeout=15)
            return r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def api_post(self, endpoint, data=None):
        headers = {"X-Admin-Key": self.get_admin_key(), "Content-Type": "application/json"}
        try:
            r = requests.post(f"{APP_URL}{endpoint}", headers=headers, json=data, timeout=30)
            return r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def check_connection(self):
        def check():
            result = self.api_get("/admin/api/status")
            if "error" not in result:
                self.server_online = True
                self.update_status(True)
                if self.is_owner:
                    self.log("Connected as OWNER.")
            else:
                self.server_online = False
                self.update_status(False)
        threading.Thread(target=check, daemon=True).start()

    def update_status(self, online):
        color = GREEN if online else RED
        text = "ONLINE" if online else "OFFLINE"
        self.status_dot.itemconfig(self.status_circle, fill=color)
        self.status_label.config(text=text, fg=color)

    # ===== SERVER CONTROL (OWNER ONLY) =====
    def start_server(self):
        if not self.is_owner:
            return
        self.log("Starting server...")
        result = self.api_post("/admin/api/start")
        if "error" in result:
            messagebox.showerror("Error", result["error"])
            self.log("START failed: " + result["error"])
        else:
            messagebox.showinfo("Success", "Server is ONLINE!")
            self.log("Server started.")
            self.server_online = True
            self.update_status(True)

    def stop_server(self):
        if not self.is_owner:
            return
        if not messagebox.askyesno("STOP SERVER?", "All visitors will be disconnected.\nShow maintenance page."):
            return
        self.log("Stopping server...")
        result = self.api_post("/admin/api/stop")
        if "error" in result:
            messagebox.showerror("Error", result["error"])
        else:
            messagebox.showinfo("Stopped", "Server is now in maintenance mode.")
            self.log("Server stopped.")
            self.server_online = False
            self.update_status(False)

    def restart_server(self):
        if not self.is_owner:
            return
        if not messagebox.askyesno("RESTART?", "Restart the server?"):
            return
        self.log("Restarting server...")
        result = self.api_post("/admin/api/restart")
        if "error" in result:
            messagebox.showerror("Error", result["error"])
        else:
            messagebox.showinfo("Restarting", "Server restart initiated!")
            self.log("Server restarting...")

    # ===== UNLOCK CODES (OWNER ONLY) =====
    def show_unlock_codes(self):
        if not self.is_owner:
            return
        self.log("Fetching unlock codes...")
        result = self.api_get("/admin/api/unlock-codes")
        if "error" in result:
            messagebox.showerror("Error", result["error"])
            return

        codes = result.get("codes", [])
        if not codes:
            messagebox.showinfo("Unlock Codes", "No pending unlock requests.")
            return

        # Build dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Unlock Requests")
        dialog.geometry("500x400")
        dialog.configure(bg=BG)

        tk.Label(dialog, text="Pending Unlock Requests", font=("Segoe UI", 14, "bold"),
                 fg=YELLOW, bg=BG).pack(pady=10)

        txt = scrolledtext.ScrolledText(dialog, bg=CARD, fg=TEXT, font=("Consolas", 10),
                                         wrap=tk.WORD, height=10)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        for c in codes:
            txt.insert(tk.END, f"Code: {c.get('code')} | IP: {c.get('ip')} | Device: {c.get('device')}\n")
            txt.insert(tk.END, f"Time: {c.get('timestamp')}\n\n")
        txt.configure(state=tk.DISABLED)

        # Unlock form
        frm = tk.Frame(dialog, bg=BG)
        frm.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(frm, text="Enter code to unlock:", font=("Segoe UI", 10), fg=TEXT, bg=BG).pack(side=tk.LEFT)
        entry_code = tk.Entry(frm, font=("Segoe UI", 11), width=15, bg=CARD, fg=TEXT)
        entry_code.pack(side=tk.LEFT, padx=5)

        tk.Label(frm, text="New password (optional):", font=("Segoe UI", 10), fg=TEXT, bg=BG).pack(side=tk.LEFT, padx=(20, 0))
        entry_pwd = tk.Entry(frm, font=("Segoe UI", 11), width=15, bg=CARD, fg=TEXT)
        entry_pwd.pack(side=tk.LEFT, padx=5)

        def do_unlock():
            code = entry_code.get().strip()
            pwd = entry_pwd.get().strip()
            if not code:
                messagebox.showwarning("Input", "Enter unlock code")
                return
            result = self.api_post("/admin/api/unlock", {"code": code, "new_password": pwd})
            if "error" in result:
                messagebox.showerror("Error", result["error"])
            else:
                msg = result.get("message", "User unlocked")
                messagebox.showinfo("Success", msg)
                self.log(f"Unlocked user with code {code}")
                dialog.destroy()

        tk.Button(dialog, text="UNLOCK USER", font=("Segoe UI", 12, "bold"),
                  bg=GREEN, fg="white", command=do_unlock,
                  cursor="hand2", relief=tk.FLAT).pack(pady=10)

    def change_password(self):
        if not self.is_owner:
            return
        new_pwd = simpledialog.askstring("Change Password", "Enter new password (min 4 chars):",
                                          show="*", parent=self.root)
        if not new_pwd or len(new_pwd) < 4:
            messagebox.showwarning("Invalid", "Password must be at least 4 characters")
            return
        result = self.api_post("/admin/api/change-password", {"new_password": new_pwd})
        if "error" in result:
            messagebox.showerror("Error", result["error"])
        else:
            messagebox.showinfo("Success", "Password changed! Tell your staff the new password.")
            self.log("Password changed by admin.")

    # ===== REFRESH METHODS =====
    def refresh_all(self):
        self.refresh_visitors()
        self.refresh_analytics()
        self.refresh_errors()
        self.lbl_last_update.config(text="Updated: " + datetime.now().strftime("%H:%M:%S"))

    def refresh_visitors(self):
        result = self.api_get("/admin/api/live")
        if "error" in result:
            return
        visitors = result.get("recent", [])
        total = result.get("total", 0)
        active = result.get("active_now", 0)
        self.lbl_visitors.config(text=f"Total: {total}")
        self.lbl_online.config(text=f"Online: {active}")

        filt = self.filter_var.get()
        if filt != "all":
            visitors = [e for e in visitors if e.get("action") == filt]

        for item in self.tree_visitors.get_children():
            self.tree_visitors.delete(item)

        for entry in reversed(visitors[-50:]):
            ts = entry.get("timestamp", "")[11:19] if len(entry.get("timestamp", "")) > 10 else "--:--"
            ip = (entry.get("ip", "") or "---")[:15]
            device = entry.get("device", "Unknown") or "Unknown"
            if entry.get("brand") and entry.get("model") and entry.get("brand") != "Unknown":
                device = entry.get("brand") + " " + entry.get("model")
            dev_type = "Mobile" if entry.get("is_mobile") else "PC" if entry.get("is_pc") else "Other"
            action = entry.get("action", "unknown")
            details = entry.get("details", "")[:40]
            self.tree_visitors.insert("", tk.END, values=(ts, ip, device, dev_type, action, details))

    def refresh_errors(self):
        result = self.api_get("/admin/api/errors")
        if "error" in result:
            return
        errors = result.get("errors", [])
        unanalyzed = result.get("unanalyzed", 0)
        self.lbl_errors.config(text=f"Errors: {len(errors)} ({unanalyzed} new)")

        self.txt_errors.configure(state=tk.NORMAL)
        self.txt_errors.delete(1.0, tk.END)
        for e in errors:
            ts = e.get("timestamp", "")[11:19] if len(e.get("timestamp", "")) > 10 else "--:--"
            analyzed = "[AI DONE]" if e.get("analyzed") else "[NEW]"
            self.txt_errors.insert(tk.END, f"{analyzed} {ts} | {e.get('type','')} | {e.get('message','')[:60]}\n")
            if e.get("ai_diagnosis"):
                self.txt_errors.insert(tk.END, f"    AI: {e.get('ai_diagnosis','')[:80]}\n")
        self.txt_errors.configure(state=tk.DISABLED)

        # Show AI results
        self.txt_ai_results.configure(state=tk.NORMAL)
        self.txt_ai_results.delete(1.0, tk.END)
        analyzed_errors = [e for e in errors if e.get("analyzed")]
        if analyzed_errors:
            for e in analyzed_errors[-5:]:
                self.txt_ai_results.insert(tk.END, f"=== {e.get('type','')} ===\n")
                self.txt_ai_results.insert(tk.END, f"DIAGNOSIS: {e.get('ai_diagnosis','N/A')[:200]}\n")
                self.txt_ai_results.insert(tk.END, f"FIX: {e.get('ai_fix','N/A')[:200]}\n\n")
        else:
            self.txt_ai_results.insert(tk.END, "No AI analysis yet.\n")
            if not self.is_owner:
                self.txt_ai_results.insert(tk.END, "(Owner must trigger analysis)\n")
        self.txt_ai_results.configure(state=tk.DISABLED)

    def refresh_analytics(self):
        result = self.api_get("/admin/api/status")
        if "error" in result:
            return
        stats = result.get("stats", {})
        self.analytics_cards["Visits"].config(text=str(result.get("total_visits", 0)))
        self.analytics_cards["Searches"].config(text=str(stats.get("searches", 0)))
        self.analytics_cards["Watches"].config(text=str(stats.get("watches", 0)))
        self.analytics_cards["Downloads"].config(text=str(stats.get("downloads", 0)))

        top = result.get("top_searches", [])
        self.txt_top_searches.configure(state=tk.NORMAL)
        self.txt_top_searches.delete(1.0, tk.END)
        for i, (q, c) in enumerate(top[:15], 1):
            bar = "█" * min(c, 25)
            self.txt_top_searches.insert(tk.END, f"{i:2}. {q:35} {c:4} {bar}\n")
        self.txt_top_searches.configure(state=tk.DISABLED)

        devices = result.get("device_breakdown", {})
        self.txt_devices.configure(state=tk.NORMAL)
        self.txt_devices.delete(1.0, tk.END)
        for d, c in sorted(devices.items(), key=lambda x: -x[1]):
            pct = round(c / max(result.get("total_visits", 1), 1) * 100)
            self.txt_devices.insert(tk.END, f"{d:15} {c:5} visits ({pct}%)\n")
        self.txt_devices.configure(state=tk.DISABLED)

    # ===== AI METHODS (OWNER ONLY) =====
    def analyze_errors_ai(self):
        if not self.is_owner:
            return
        self.log("Sending errors to AI...")
        self.txt_ai_results.configure(state=tk.NORMAL)
        self.txt_ai_results.delete(1.0, tk.END)
        self.txt_ai_results.insert(tk.END, "Analyzing with AI... please wait...\n")
        self.txt_ai_results.configure(state=tk.DISABLED)
        self.root.update()

        def do_analyze():
            result = self.api_post("/admin/api/errors/analyze")
            if "error" in result:
                self.txt_ai_results.configure(state=tk.NORMAL)
                self.txt_ai_results.delete(1.0, tk.END)
                self.txt_ai_results.insert(tk.END, f"Error: {result['error']}\n")
                self.txt_ai_results.configure(state=tk.DISABLED)
                return

            results = result.get("results", [])
            self.txt_ai_results.configure(state=tk.NORMAL)
            self.txt_ai_results.delete(1.0, tk.END)

            if not results:
                self.txt_ai_results.insert(tk.END, "No new errors! Your site is clean.\n")
            else:
                for r in results:
                    self.txt_ai_results.insert(tk.END, f"=== {r['type']} ===\n")
                    self.txt_ai_results.insert(tk.END, f"Time: {r['timestamp']}\n")
                    self.txt_ai_results.insert(tk.END, f"Error: {r['message']}\n\n")
                    self.txt_ai_results.insert(tk.END, f"DIAGNOSIS:\n{r['diagnosis']}\n\n")
                    self.txt_ai_results.insert(tk.END, f"FIX:\n{r['fix']}\n\n")
                    self.txt_ai_results.insert(tk.END, "-" * 50 + "\n\n")

                remaining = result.get("remaining", 0)
                self.txt_ai_results.insert(tk.END, f"Remaining unanalyzed: {remaining}\n")

            self.txt_ai_results.configure(state=tk.DISABLED)
            self.log(f"AI analyzed {len(results)} errors.")
            self.refresh_errors()

        threading.Thread(target=do_analyze, daemon=True).start()

    def ai_site_diagnosis(self):
        if not self.is_owner:
            return
        self.log("Running AI site diagnosis...")
        self.txt_ai_results.configure(state=tk.NORMAL)
        self.txt_ai_results.delete(1.0, tk.END)
        self.txt_ai_results.insert(tk.END, "AI diagnosing site... please wait...\n")
        self.txt_ai_results.configure(state=tk.DISABLED)
        self.root.update()

        def do_diagnose():
            result = self.api_post("/admin/api/ai/diagnose-site")
            if "error" in result:
                self.txt_ai_results.configure(state=tk.NORMAL)
                self.txt_ai_results.delete(1.0, tk.END)
                self.txt_ai_results.insert(tk.END, f"Error: {result['error']}\n")
                self.txt_ai_results.configure(state=tk.DISABLED)
                return

            self.txt_ai_results.configure(state=tk.NORMAL)
            self.txt_ai_results.delete(1.0, tk.END)
            self.txt_ai_results.insert(tk.END, result.get("diagnosis", "No response"))
            self.txt_ai_results.configure(state=tk.DISABLED)
            self.log("AI site diagnosis complete.")

        threading.Thread(target=do_diagnose, daemon=True).start()

    def ai_fix_code(self):
        if not self.is_owner:
            return
        code = self.txt_code_input.get(1.0, tk.END).strip()
        issue = self.entry_issue.get().strip()

        if not code and not issue:
            messagebox.showwarning("Input Required", "Paste code or describe an issue.")
            return

        self.log("Sending code to AI...")
        self.txt_code_output.configure(state=tk.NORMAL)
        self.txt_code_output.delete(1.0, tk.END)
        self.txt_code_output.insert(tk.END, "AI reviewing code... please wait...\n")
        self.txt_code_output.configure(state=tk.DISABLED)
        self.root.update()

        def do_fix():
            result = self.api_post("/admin/api/ai/code-review", {"code": code, "issue": issue})
            if "error" in result:
                self.txt_code_output.configure(state=tk.NORMAL)
                self.txt_code_output.delete(1.0, tk.END)
                self.txt_code_output.insert(tk.END, f"Error: {result['error']}\n")
                self.txt_code_output.configure(state=tk.DISABLED)
                return

            self.txt_code_output.configure(state=tk.NORMAL)
            self.txt_code_output.delete(1.0, tk.END)
            self.txt_code_output.insert(tk.END, result.get("review", "No response"))
            self.txt_code_output.configure(state=tk.DISABLED)
            self.log("AI code review complete.")

        threading.Thread(target=do_fix, daemon=True).start()

    def ask_ai(self):
        if not self.is_owner:
            return
        question = self.entry_chat.get().strip()
        if not question:
            return
        self.entry_chat.delete(0, tk.END)

        self.txt_chat.configure(state=tk.NORMAL)
        self.txt_chat.insert(tk.END, f"\nYOU: {question}\n")
        self.txt_chat.insert(tk.END, "AI: Thinking...\n")
        self.txt_chat.see(tk.END)
        self.txt_chat.configure(state=tk.DISABLED)
        self.root.update()

        def do_ask():
            result = self.api_post("/admin/api/ai/ask", {"question": question})
            self.txt_chat.configure(state=tk.NORMAL)
            text = self.txt_chat.get(1.0, tk.END)
            text = text.replace("AI: Thinking...\n", "")
            self.txt_chat.delete(1.0, tk.END)
            self.txt_chat.insert(tk.END, text)

            if "error" in result:
                self.txt_chat.insert(tk.END, f"AI: Sorry, {result['error']}\n")
            else:
                answer = result.get("answer", "No response")
                self.txt_chat.insert(tk.END, f"AI: {answer}\n")

            self.txt_chat.see(tk.END)
            self.txt_chat.configure(state=tk.DISABLED)

        threading.Thread(target=do_ask, daemon=True).start()

    def quick_ask(self, question):
        if not self.is_owner:
            return
        self.entry_chat.delete(0, tk.END)
        self.entry_chat.insert(0, question)
        self.ask_ai()

    # ===== BROADCAST =====
    def send_broadcast(self):
        msg = self.entry_broadcast.get().strip()
        if not msg:
            messagebox.showwarning("Input Required", "Enter a message.")
            return
        result = self.api_post("/admin/api/broadcast", {"message": msg})
        if "error" in result:
            messagebox.showerror("Error", result["error"])
        else:
            count = result.get("sent_to", 0)
            messagebox.showinfo("Sent", f"Message sent to {count} visitors!")
            self.txt_broadcast_history.configure(state=tk.NORMAL)
            ts = datetime.now().strftime("%H:%M:%S")
            self.txt_broadcast_history.insert(tk.END, f"[{ts}] {msg}\n")
            self.txt_broadcast_history.see(tk.END)
            self.txt_broadcast_history.configure(state=tk.DISABLED)
            self.entry_broadcast.delete(0, tk.END)

    # ===== EXPORT =====
    def export_logs(self):
        if not self.is_owner:
            return
        result = self.api_get("/admin/logs-json")
        if "error" in result:
            messagebox.showerror("Error", result["error"])
            return
        filename = "kyro_logs_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            messagebox.showinfo("Saved", f"Saved to {filename}")
            self.log(f"Logs exported: {filename}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_errors(self):
        if not self.is_owner:
            return
        result = self.api_get("/admin/api/errors")
        if "error" in result:
            messagebox.showerror("Error", result["error"])
            return
        filename = "kyro_errors_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            messagebox.showinfo("Saved", f"Saved to {filename}")
            self.log(f"Errors exported: {filename}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ===== MONITOR =====
    def toggle_monitor(self):
        if self.monitoring:
            self.monitoring = False
            self.btn_monitor.config(text="Start Live Monitor", bg=CARD)
            if self.is_owner:
                self.log("Monitor stopped.")
        else:
            self.monitoring = True
            self.btn_monitor.config(text="Stop Monitor", bg=RED)
            if self.is_owner:
                self.log("Monitor started.")
            self.monitor_loop()

    def monitor_loop(self):
        if not self.monitoring:
            return
        self.refresh_all()
        self.root.after(3000, self.monitor_loop)


# ===== MAIN ENTRY POINT =====

def show_setup():
    """Initial setup dialog"""
    global APP_URL, OWNER_KEY, STAFF_KEY

    setup = tk.Tk()
    setup.title("KYRO Controller Setup")
    setup.geometry("450x350")
    setup.configure(bg=BG)
    setup.resizable(False, False)

    tk.Label(setup, text="KYRO", font=("Segoe UI", 28, "bold"),
             fg=BLUE, bg=BG).pack(pady=(20, 0))
    tk.Label(setup, text="ULTIMATE CONTROLLER v4.0", font=("Segoe UI", 12),
             fg=YELLOW, bg=BG).pack()

    frm = tk.Frame(setup, bg=BG)
    frm.pack(pady=20, padx=30)

    tk.Label(frm, text="App URL:", font=("Segoe UI", 10), fg=TEXT, bg=BG).pack(anchor=tk.W)
    entry_url = tk.Entry(frm, font=("Segoe UI", 11), width=40, bg=CARD, fg=TEXT)
    entry_url.insert(0, APP_URL)
    entry_url.pack(pady=5)

    tk.Label(frm, text="Owner Key:", font=("Segoe UI", 10), fg=TEXT, bg=BG).pack(anchor=tk.W)
    entry_owner = tk.Entry(frm, font=("Segoe UI", 11), width=40, bg=CARD, fg=TEXT, show="*")
    entry_owner.pack(pady=5)

    tk.Label(frm, text="Staff Key:", font=("Segoe UI", 10), fg=TEXT, bg=BG).pack(anchor=tk.W)
    entry_staff = tk.Entry(frm, font=("Segoe UI", 11), width=40, bg=CARD, fg=TEXT, show="*")
    entry_staff.pack(pady=5)

    def do_setup():
        global APP_URL, OWNER_KEY, STAFF_KEY
        APP_URL = entry_url.get().strip().rstrip("/")
        OWNER_KEY = entry_owner.get().strip()
        STAFF_KEY = entry_staff.get().strip()
        setup.destroy()
        show_login()

    tk.Button(setup, text="CONNECT", font=("Segoe UI", 14, "bold"),
              bg=GREEN, fg="white", command=do_setup,
              cursor="hand2", relief=tk.FLAT).pack(pady=15)

    setup.mainloop()


def show_login():
    """Show password login, then mode selector, then main controller"""
    root = tk.Tk()
    root.withdraw()

    def on_login_success():
        def on_mode_selected(mode):
            global USER_MODE
            USER_MODE = mode
            root.deiconify()
            root.title(f"KYRO CONTROLLER - {mode.upper()}")
            KYROController(root)

        ModeSelector(root, on_mode_selected)

    PasswordScreen(root, on_login_success)
    root.mainloop()


if __name__ == "__main__":
    show_setup()
