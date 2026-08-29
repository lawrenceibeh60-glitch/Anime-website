#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KYRO SPY - LIVE VISITOR MONITOR
Track every visitor to your anime site in real-time

Setup:
1. Install Pydroid 3 from Play Store
2. pip install requests
3. Change LOG_URL below to your deployed app URL
4. Run this script
"""

import requests
import json
import time
import os

# CONFIG - CHANGE THIS TO YOUR APP URL
LOG_URL = "YOUR_APP_URL_HERE/admin/logs-json"
# Example: LOG_URL = "https://kyro-ai-anime.onrender.com/admin/logs-json"

REFRESH_MS = 300

# Color codes
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
MAGENTA = "\033[95m"
BLUE    = "\033[94m"
WHITE   = "\033[97m"
DIM     = "\033[90m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

BORDER_TOP  = "+======================================================================+"
BORDER_MID  = "+----------------------------------------------------------------------+"
BORDER_BOT  = "+======================================================================+"
BORDER_SIDE = "|"

def clear_screen():
    os.system("clear" if os.name != "nt" else "cls")

def center_text(text, width=70):
    padding = (width - len(text)) // 2
    return " " * padding + text

def get_device_emoji(device, brand, model, is_mobile, is_tablet, is_pc):
    d = (device or "").lower()
    m = (model or "").lower()
    b = (brand or "").lower()
    if "iphone" in d or "iphone" in m: return "[PHONE]"
    if "ipad" in d or "ipad" in m: return "[TABLET]"
    if "samsung" in b or "galaxy" in m: return "[PHONE]"
    if "pixel" in m: return "[PHONE]"
    if "xiaomi" in b or "redmi" in m: return "[PHONE]"
    if "huawei" in b or "honor" in m: return "[PHONE]"
    if "oneplus" in b: return "[PHONE]"
    if "oppo" in b or "vivo" in b or "realme" in b: return "[PHONE]"
    if "nokia" in b: return "[PHONE]"
    if "lg" in b: return "[PHONE]"
    if "sony" in b or "xperia" in m: return "[PHONE]"
    if "motorola" in b or "moto" in m: return "[PHONE]"
    if is_tablet: return "[TABLET]"
    if is_pc:
        if "mac" in d or "macbook" in m: return "[LAPTOP]"
        return "[PC]"
    if is_mobile: return "[PHONE]"
    return "[?]"

def get_action_emoji(action):
    icons = {
        "page_view": "[HOME]",
        "search": "[SEARCH]",
        "view_anime": "[VIEW]",
        "watch": "[PLAY]",
        "download": "[DOWN]",
        "chat": "[CHAT]"
    }
    return icons.get(action, "[?]")

def get_action_color(action):
    colors = {
        "page_view": CYAN,
        "search": YELLOW,
        "view_anime": BLUE,
        "watch": GREEN,
        "download": MAGENTA,
        "chat": WHITE
    }
    return colors.get(action, DIM)

def format_time(timestamp):
    if not timestamp: return "Unknown"
    ts = timestamp.replace("T", " ")
    if "." in ts: ts = ts.split(".")[0]
    return ts

def truncate(text, max_len=35):
    if not text: return ""
    if len(text) > max_len: return text[:max_len-2] + ".."
    return text

def fetch_logs():
    try:
        response = requests.get(LOG_URL, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("visits", []), data.get("total", 0)
        return None, 0
    except:
        return None, 0

def show_live_monitor():
    seen_ids = set()
    while True:
        try:
            logs, total = fetch_logs()
            if logs is None:
                clear_screen()
                print(RED + "Connection lost! Retrying..." + RESET)
                time.sleep(REFRESH_MS / 1000)
                continue

            new_visits = []
            for log in logs:
                log_id = log.get("timestamp", "") + log.get("ip", "") + log.get("action", "")
                if log_id not in seen_ids:
                    seen_ids.add(log_id)
                    new_visits.append(log)
            if len(seen_ids) > 1000:
                seen_ids = set(list(seen_ids)[-500:])

            clear_screen()
            print(CYAN + BORDER_TOP)
            print(BORDER_SIDE + center_text("KYRO SPY - LIVE VISITOR MONITOR", 70) + BORDER_SIDE)
            print(BORDER_SIDE + center_text("Real-time tracking | " + str(REFRESH_MS) + "ms refresh", 70) + BORDER_SIDE)
            print(BORDER_MID)
            stats = "  Total: " + str(total) + "  |  New: " + str(len(new_visits)) + "  |  Refresh: " + str(REFRESH_MS) + "ms"
            print(BORDER_SIDE + stats.ljust(70) + BORDER_SIDE)
            print(BORDER_MID)

            recent = list(reversed(logs[-8:])) if logs else []
            if not recent:
                print(BORDER_SIDE + "  No visitors yet... Waiting...".ljust(70) + BORDER_SIDE)
            else:
                for i, entry in enumerate(recent):
                    is_new = entry in new_visits
                    flash = BOLD if is_new else ""

                    device_emoji = get_device_emoji(
                        entry.get("device"), entry.get("brand"), entry.get("model"),
                        entry.get("is_mobile"), entry.get("is_tablet"), entry.get("is_pc")
                    )
                    action_emoji = get_action_emoji(entry.get("action"))
                    action_color = get_action_color(entry.get("action"))

                    brand = entry.get("brand", "")
                    model = entry.get("model", "")
                    device = entry.get("device", "Unknown")
                    if brand and model and brand != "Unknown":
                        device_name = brand + " " + model
                    elif device and device != "Unknown":
                        device_name = device
                    else:
                        device_name = "Unknown"

                    time_str = format_time(entry.get("timestamp"))
                    action_str = entry.get("action", "unknown").upper()
                    ip = entry.get("ip", "Unknown")

                    line1 = "  " + action_emoji + " " + action_color + flash + action_str
                    line1 = line1.ljust(50) + RESET + DIM + time_str + RESET
                    print(BORDER_SIDE + line1.ljust(78) + BORDER_SIDE)

                    line2 = "     " + device_emoji + " " + device_name + "  |  OS: " + entry.get("os", "Unknown")
                    print(BORDER_SIDE + WHITE + line2.ljust(70) + RESET + BORDER_SIDE)

                    browser = entry.get("browser", "Unknown")
                    details = entry.get("details", "")
                    line3 = "     Browser: " + browser
                    if details:
                        line3 += "  |  " + truncate(details, 25)
                    print(BORDER_SIDE + DIM + line3.ljust(70) + RESET + BORDER_SIDE)

                    if i < len(recent) - 1:
                        print(BORDER_SIDE + "-" * 70 + BORDER_SIDE)

            print(BORDER_BOT)
            print(DIM + "  Press Ctrl+C to exit  |  Watching..." + RESET)
            time.sleep(REFRESH_MS / 1000)

        except KeyboardInterrupt:
            clear_screen()
            print(YELLOW + "Monitor stopped." + RESET)
            time.sleep(1)
            break
        except Exception as e:
            clear_screen()
            print(RED + "Error: " + str(e) + RESET)
            time.sleep(1)

def show_summary():
    logs, total = fetch_logs()
    if not logs:
        print(RED + "No data!" + RESET)
        input("Press Enter...")
        return

    actions = {}
    brands = {}
    browsers = {}
    os_stats = {}
    mobile_count = 0
    pc_count = 0

    for entry in logs:
        action = entry.get("action", "unknown")
        actions[action] = actions.get(action, 0) + 1
        brand = entry.get("brand", "Unknown")
        if brand and brand != "Unknown":
            brands[brand] = brands.get(brand, 0) + 1
        browser = entry.get("browser", "Unknown")
        browser_family = browser.split()[0] if browser else "Unknown"
        browsers[browser_family] = browsers.get(browser_family, 0) + 1
        os_name = entry.get("os", "Unknown")
        os_family = os_name.split()[0] if os_name else "Unknown"
        os_stats[os_family] = os_stats.get(os_family, 0) + 1
        if entry.get("is_mobile"): mobile_count += 1
        elif entry.get("is_pc"): pc_count += 1

    clear_screen()
    print(CYAN + BORDER_TOP)
    print(BORDER_SIDE + center_text("KYRO SPY - VISITOR SUMMARY", 70) + BORDER_SIDE)
    print(BORDER_MID)
    print(BORDER_SIDE + "  OVERALL STATISTICS".ljust(70) + BORDER_SIDE)
    print(BORDER_SIDE + ("     Total Visits: " + str(total)).ljust(70) + BORDER_SIDE)
    print(BORDER_SIDE + ("     Mobile: " + str(mobile_count) + "  |  PC: " + str(pc_count)).ljust(70) + BORDER_SIDE)
    print(BORDER_MID)

    print(BORDER_SIDE + YELLOW + "  TOP ACTIONS".ljust(70) + RESET + BORDER_SIDE)
    for action, count in sorted(actions.items(), key=lambda x: -x[1])[:5]:
        bar = "#" * min(count, 25)
        print(BORDER_SIDE + ("     " + action + ": " + str(count) + " " + bar).ljust(70) + BORDER_SIDE)

    print(BORDER_MID)
    print(BORDER_SIDE + GREEN + "  TOP DEVICES".ljust(70) + RESET + BORDER_SIDE)
    for brand, count in sorted(brands.items(), key=lambda x: -x[1])[:5]:
        bar = "#" * min(count, 25)
        print(BORDER_SIDE + ("     " + brand + ": " + str(count) + " " + bar).ljust(70) + BORDER_SIDE)

    print(BORDER_MID)
    print(BORDER_SIDE + BLUE + "  TOP BROWSERS".ljust(70) + RESET + BORDER_SIDE)
    for browser, count in sorted(browsers.items(), key=lambda x: -x[1])[:5]:
        bar = "#" * min(count, 25)
        print(BORDER_SIDE + ("     " + browser + ": " + str(count) + " " + bar).ljust(70) + BORDER_SIDE)

    print(BORDER_MID)
    print(BORDER_SIDE + MAGENTA + "  TOP OPERATING SYSTEMS".ljust(70) + RESET + BORDER_SIDE)
    for os_name, count in sorted(os_stats.items(), key=lambda x: -x[1])[:5]:
        bar = "#" * min(count, 25)
        print(BORDER_SIDE + ("     " + os_name + ": " + str(count) + " " + bar).ljust(70) + BORDER_SIDE)

    print(BORDER_BOT)
    input(DIM + "Press Enter to return..." + RESET)

def show_history(action_type, title, icon):
    logs, total = fetch_logs()
    if not logs:
        print(RED + "No data!" + RESET)
        input("Press Enter...")
        return

    filtered = [e for e in logs if e.get("action") == action_type]
    clear_screen()
    print(CYAN + BORDER_TOP)
    print(BORDER_SIDE + center_text(title, 70) + BORDER_SIDE)
    print(BORDER_MID)
    print(BORDER_SIDE + ("  Total: " + str(len(filtered))).ljust(70) + BORDER_SIDE)
    print(BORDER_MID)

    if not filtered:
        print(BORDER_SIDE + "  No entries yet...".ljust(70) + BORDER_SIDE)
    else:
        for entry in reversed(filtered[-15:]):
            ts = format_time(entry.get("timestamp"))
            ip = entry.get("ip", "Unknown")
            details = entry.get("details", "")
            print(BORDER_SIDE + ("  [" + ts + "] " + ip).ljust(70) + BORDER_SIDE)
            print(BORDER_SIDE + ("     " + icon + " " + truncate(details, 55)).ljust(70) + BORDER_SIDE)
            print(BORDER_SIDE + " ".ljust(70) + BORDER_SIDE)

    print(BORDER_BOT)
    input(DIM + "Press Enter to return..." + RESET)

def main_menu():
    while True:
        clear_screen()
        print(CYAN + BORDER_TOP)
        print(BORDER_SIDE + center_text("KYRO SPY - VISITOR TRACKER", 70) + BORDER_SIDE)
        print(BORDER_SIDE + center_text("Monitor your anime site visitors", 70) + BORDER_SIDE)
        print(BORDER_MID)
        print(BORDER_SIDE + "  1. LIVE MONITOR      - Real-time 300ms refresh".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + "  2. SUMMARY           - Statistics & charts".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + "  3. SEARCH HISTORY    - What people searched".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + "  4. WATCH HISTORY     - What people watched".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + "  5. DOWNLOADS         - What people downloaded".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + "  6. CHAT HISTORY      - What people asked AI".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + "  7. EXIT".ljust(70) + BORDER_SIDE)
        print(BORDER_BOT)

        choice = input(BOLD + "Choose: " + RESET).strip()

        if choice == "1":
            try: show_live_monitor()
            except KeyboardInterrupt: pass
        elif choice == "2":
            show_summary()
        elif choice == "3":
            show_history("search", "SEARCH HISTORY", "SEARCH:")
        elif choice == "4":
            show_history("watch", "WATCH HISTORY", "PLAY:")
        elif choice == "5":
            show_history("download", "DOWNLOADS", "DOWN:")
        elif choice == "6":
            show_history("chat", "CHAT HISTORY", "CHAT:")
        elif choice == "7":
            clear_screen()
            print(GREEN + "Goodbye!" + RESET)
            time.sleep(1)
            break
        else:
            print(RED + "Invalid choice!" + RESET)
            time.sleep(1)

if __name__ == "__main__":
    if "YOUR_APP_URL_HERE" in LOG_URL:
        clear_screen()
        print(YELLOW + BORDER_TOP)
        print(BORDER_SIDE + center_text("SETUP REQUIRED", 70) + BORDER_SIDE)
        print(BORDER_MID)
        print(BORDER_SIDE + "  You need to set your app URL!".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + " ".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + "  Edit this file and change line 22:".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + " ".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + BOLD + "  LOG_URL = https://your-app.onrender.com/admin/logs-json".ljust(70) + RESET + BORDER_SIDE)
        print(BORDER_SIDE + " ".ljust(70) + BORDER_SIDE)
        print(BORDER_SIDE + "  Replace with your actual deployed app URL.".ljust(70) + BORDER_SIDE)
        print(BORDER_BOT)
        input(DIM + "Press Enter to exit..." + RESET)
    else:
        clear_screen()
        print(CYAN + "Connecting to " + LOG_URL + "..." + RESET)
        try:
            test = requests.get(LOG_URL, timeout=5)
            if test.status_code == 200:
                print(GREEN + "Connected! Starting KYRO SPY..." + RESET)
                time.sleep(1)
                main_menu()
            else:
                print(RED + "Server returned " + str(test.status_code) + RESET)
                input("Press Enter...")
        except Exception as e:
            print(RED + "Connection failed: " + str(e) + RESET)
            input("Press Enter...")
