#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KYRO SPY - VISITOR MONITOR
"""

import requests
import json
import time
import os

# CONFIG
LOG_URL = "https://anime-website-sjz2.onrender.com/admin/logs-json"
REFRESH_MS = 300

# Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"
DIM = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def fmt_time(ts):
    if not ts: return "--:--:--"
    ts = ts.replace("T", " ")
    if "." in ts: ts = ts.split(".")[0]
    return ts[11:19] if len(ts) > 10 else ts

def fmt_ip(ip):
    if not ip or ip == "Unknown": return "---.---.---.---"
    return ip.split(",")[0].strip()[:15]

def fmt_device(entry):
    brand = entry.get("brand", "")
    model = entry.get("model", "")
    device = entry.get("device", "")
    if brand and model and brand != "Unknown":
        return brand + " " + model
    elif device and device != "Unknown":
        return device
    return "Unknown"

def fmt_browser(entry):
    b = entry.get("browser", "Unknown")
    return b.split()[0] if " " in b else b

def fmt_os(entry):
    o = entry.get("os", "Unknown")
    return o.split()[0] if " " in o else o

def fmt_action(entry):
    a = entry.get("action", "unknown")
    d = entry.get("details", "")
    if a == "search": return "SEARCH: " + d.replace("Searched for: ", "")[:25]
    if a == "watch": return "WATCH: " + d.replace("Stream hash: ", "")[:25]
    if a == "download": return "DOWNLOAD: " + d.replace("Downloaded: ", "")[:22]
    if a == "chat": return "CHAT: " + d.replace("Chat message: ", "")[:25]
    if a == "view_anime": return "VIEW: " + d.replace("Viewed anime ID: ", "")[:25]
    if a == "page_view": return "HOME PAGE"
    return a.upper()

def get_type(entry):
    if entry.get("is_mobile"): return "MOBILE"
    if entry.get("is_pc"): return "PC"
    if entry.get("is_tablet"): return "TABLET"
    return "OTHER"

def fetch():
    try:
        r = requests.get(LOG_URL, timeout=5)
        if r.status_code == 200:
            d = r.json()
            return d.get("visits", []), d.get("total", 0)
    except: pass
    return None, 0

def draw_table(headers, rows, widths):
    # Top border
    line = "+"
    for w in widths: line += "-" * (w + 2) + "+"
    print(CYAN + line + RESET)

    # Headers
    hline = "|"
    for i, h in enumerate(headers):
        hline += " " + BOLD + h.center(widths[i]) + RESET + " |"
    print(hline)

    # Separator
    line = "+"
    for w in widths: line += "-" * (w + 2) + "+"
    print(CYAN + line + RESET)

    # Rows
    for row in rows:
        rline = "|"
        for i, cell in enumerate(row):
            rline += " " + str(cell)[:widths[i]].ljust(widths[i]) + " |"
        print(rline)

    # Bottom border
    line = "+"
    for w in widths: line += "-" * (w + 2) + "+"
    print(CYAN + line + RESET)

def live_monitor():
    seen = set()
    while True:
        try:
            logs, total = fetch()
            if logs is None:
                clear()
                print(RED + "Connection lost. Retrying..." + RESET)
                time.sleep(REFRESH_MS / 1000)
                continue

            new = []
            for log in logs:
                lid = log.get("timestamp", "") + log.get("ip", "") + log.get("action", "")
                if lid not in seen:
                    seen.add(lid)
                    new.append(log)
            if len(seen) > 1000:
                seen = set(list(seen)[-500:])

            clear()
            print(BOLD + "KYRO SPY - LIVE VISITOR MONITOR" + RESET)
            print("Total: " + str(total) + " | New: " + str(len(new)) + " | Refresh: " + str(REFRESH_MS) + "ms")
            print()

            headers = ["TIME", "IP ADDRESS", "DEVICE", "TYPE", "BROWSER", "OS", "ACTION"]
            widths = [8, 15, 18, 8, 10, 10, 28]

            rows = []
            for entry in reversed(logs[-12:]):
                rows.append([
                    fmt_time(entry.get("timestamp")),
                    fmt_ip(entry.get("ip")),
                    fmt_device(entry)[:18],
                    get_type(entry),
                    fmt_browser(entry)[:10],
                    fmt_os(entry)[:10],
                    fmt_action(entry)[:28]
                ])

            if not rows:
                print(DIM + "No visitors yet..." + RESET)
            else:
                draw_table(headers, rows, widths)

            print()
            print(DIM + "Press Ctrl+C to exit" + RESET)
            time.sleep(REFRESH_MS / 1000)

        except KeyboardInterrupt:
            clear()
            print("Stopped.")
            break
        except Exception as e:
            clear()
            print(RED + "Error: " + str(e) + RESET)
            time.sleep(1)

def show_summary():
    logs, total = fetch()
    if not logs:
        print(RED + "No data!" + RESET)
        input("Press Enter...")
        return

    actions = {}
    brands = {}
    browsers = {}
    os_stats = {}
    types = {"MOBILE": 0, "PC": 0, "TABLET": 0, "OTHER": 0}

    for entry in logs:
        a = entry.get("action", "unknown")
        actions[a] = actions.get(a, 0) + 1
        b = entry.get("brand", "Unknown")
        if b and b != "Unknown":
            brands[b] = brands.get(b, 0) + 1
        br = fmt_browser(entry)
        browsers[br] = browsers.get(br, 0) + 1
        o = fmt_os(entry)
        os_stats[o] = os_stats.get(o, 0) + 1
        t = get_type(entry)
        types[t] = types.get(t, 0) + 1

    clear()
    print(BOLD + "VISITOR SUMMARY" + RESET)
    print("Total visits: " + str(total))
    print()

    print(BOLD + "Device Types:" + RESET)
    headers = ["TYPE", "COUNT", "BAR"]
    widths = [10, 8, 40]
    rows = []
    for t, c in sorted(types.items(), key=lambda x: -x[1]):
        bar = "#" * min(c, 40)
        rows.append([t, str(c), bar])
    draw_table(headers, rows, widths)
    print()

    print(BOLD + "Top Actions:" + RESET)
    headers = ["ACTION", "COUNT", "BAR"]
    rows = []
    for a, c in sorted(actions.items(), key=lambda x: -x[1])[:5]:
        bar = "#" * min(c, 40)
        rows.append([a, str(c), bar])
    draw_table(headers, rows, widths)
    print()

    print(BOLD + "Top Devices:" + RESET)
    headers = ["BRAND", "COUNT", "BAR"]
    rows = []
    for b, c in sorted(brands.items(), key=lambda x: -x[1])[:5]:
        bar = "#" * min(c, 40)
        rows.append([b[:10], str(c), bar])
    draw_table(headers, rows, widths)
    print()

    print(BOLD + "Top Browsers:" + RESET)
    headers = ["BROWSER", "COUNT", "BAR"]
    rows = []
    for b, c in sorted(browsers.items(), key=lambda x: -x[1])[:5]:
        bar = "#" * min(c, 40)
        rows.append([b[:10], str(c), bar])
    draw_table(headers, rows, widths)
    print()

    print(BOLD + "Top OS:" + RESET)
    headers = ["OS", "COUNT", "BAR"]
    rows = []
    for o, c in sorted(os_stats.items(), key=lambda x: -x[1])[:5]:
        bar = "#" * min(c, 40)
        rows.append([o[:10], str(c), bar])
    draw_table(headers, rows, widths)

    print()
    input(DIM + "Press Enter to return..." + RESET)

def show_list(action_type, title):
    logs, total = fetch()
    if not logs:
        print(RED + "No data!" + RESET)
        input("Press Enter...")
        return

    filtered = [e for e in logs if e.get("action") == action_type]
    clear()
    print(BOLD + title + RESET)
    print("Total: " + str(len(filtered)))
    print()

    headers = ["TIME", "IP", "DEVICE", "DETAILS"]
    widths = [8, 15, 18, 40]
    rows = []
    for entry in reversed(filtered[-15:]):
        rows.append([
            fmt_time(entry.get("timestamp")),
            fmt_ip(entry.get("ip")),
            fmt_device(entry)[:18],
            entry.get("details", "")[:40]
        ])

    if not rows:
        print(DIM + "No entries yet..." + RESET)
    else:
        draw_table(headers, rows, widths)

    print()
    input(DIM + "Press Enter to return..." + RESET)

def menu():
    while True:
        clear()
        print(BOLD + "KYRO SPY - VISITOR TRACKER" + RESET)
        print()
        print("1. Live Monitor     - Real-time 300ms refresh")
        print("2. Summary          - Statistics & charts")
        print("3. Search History   - What people searched")
        print("4. Watch History    - What people watched")
        print("5. Downloads        - What people downloaded")
        print("6. Chat History     - What people asked AI")
        print("7. Exit")
        print()

        choice = input("Choose: ").strip()

        if choice == "1":
            try: live_monitor()
            except KeyboardInterrupt: pass
        elif choice == "2":
            show_summary()
        elif choice == "3":
            show_list("search", "SEARCH HISTORY")
        elif choice == "4":
            show_list("watch", "WATCH HISTORY")
        elif choice == "5":
            show_list("download", "DOWNLOADS")
        elif choice == "6":
            show_list("chat", "CHAT HISTORY")
        elif choice == "7":
            clear()
            print("Goodbye!")
            break
        else:
            print(RED + "Invalid!" + RESET)
            time.sleep(1)

if __name__ == "__main__":
    if "YOUR_APP_URL_HERE" in LOG_URL:
        clear()
        print(YELLOW + "SETUP REQUIRED" + RESET)
        print()
        print("Edit this file and change line 9:")
        print(BOLD + "LOG_URL = https://your-app.onrender.com/admin/logs-json" + RESET)
        print()
        print("Replace with your actual app URL.")
        input("Press Enter...")
    else:
        clear()
        print("Connecting...")
        try:
            test = requests.get(LOG_URL, timeout=5)
            if test.status_code == 200:
                print(GREEN + "Connected!" + RESET)
                time.sleep(1)
                menu()
            else:
                print(RED + "Server error: " + str(test.status_code) + RESET)
                input("Press Enter...")
        except Exception as e:
            print(RED + "Failed: " + str(e) + RESET)
            input("Press Enter...")
