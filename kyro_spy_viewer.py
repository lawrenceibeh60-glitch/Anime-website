#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🕵️  KYRO SPY - LIVE VISITOR MONITOR                                ║
║  Track every visitor to your anime site in real-time                  ║
╚══════════════════════════════════════════════════════════════════════╝

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
import sys

# ═══════════════════════════════════════════════════════════════════════
# CONFIG - CHANGE THIS TO YOUR APP URL
# ═══════════════════════════════════════════════════════════════════════
LOG_URL = "YOUR_APP_URL_HERE/admin/logs-json"
# Example: LOG_URL = "https://kyro-ai-anime.onrender.com/admin/logs-json"

REFRESH_MS = 300  # 300 milliseconds = super fast refresh

# ═══════════════════════════════════════════════════════════════════════
# ASCII ART & STYLES
# ═══════════════════════════════════════════════════════════════════════

BORDER_TOP    = "╔══════════════════════════════════════════════════════════════════════╗"
BORDER_MID    = "╠══════════════════════════════════════════════════════════════════════╣"
BORDER_BOT    = "╚══════════════════════════════════════════════════════════════════════╝"
BORDER_SIDE   = "║"
DIVIDER       = "├──────────────────────────────────────────────────────────────────────┤"

# Color codes for terminals that support them
class Colors:
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

# ═══════════════════════════════════════════════════════════════════════
# DEVICE DETECTION
# ═══════════════════════════════════════════════════════════════════════

def get_device_emoji(device, brand, model, is_mobile, is_tablet, is_pc):
    """Get the perfect emoji for any device"""
    d = (device or "").lower()
    b = (brand or "").lower()
    m = (model or "").lower()

    # iPhones
    if "iphone" in d or "iphone" in m:
        return "📱"
    # iPad
    if "ipad" in d or "ipad" in m:
        return "📱"
    # Samsung
    if "samsung" in b or "galaxy" in m:
        return "📱"
    # Google Pixel
    if "pixel" in m:
        return "📱"
    # Xiaomi
    if "xiaomi" in b or "redmi" in m or "mi " in m:
        return "📱"
    # Huawei
    if "huawei" in b or "honor" in m:
        return "📱"
    # OnePlus
    if "oneplus" in b or "oneplus" in m:
        return "📱"
    # Oppo / Vivo / Realme
    if any(x in b for x in ["oppo", "vivo", "realme"]):
        return "📱"
    # Nokia
    if "nokia" in b:
        return "📱"
    # LG
    if "lg" in b:
        return "📱"
    # Sony
    if "sony" in b or "xperia" in m:
        return "📱"
    # Motorola
    if "motorola" in b or "moto" in m:
        return "📱"

    # Tablets
    if is_tablet or "tablet" in d:
        return "📱"

    # PCs / Laptops
    if is_pc:
        if "mac" in d or "macbook" in m:
            return "💻"
        return "🖥️"

    # Mobile fallback
    if is_mobile:
        return "📱"

    return "❓"

def get_action_emoji(action):
    """Get emoji for each action type"""
    icons = {
        'page_view': '🏠',
        'search': '🔍',
        'view_anime': '👁️',
        'watch': '▶️',
        'download': '⬇️',
        'chat': '💬',
        'unknown': '📝'
    }
    return icons.get(action, '📝')

def get_action_color(action):
    """Get color for action type"""
    colors = {
        'page_view': Colors.CYAN,
        'search': Colors.YELLOW,
        'view_anime': Colors.BLUE,
        'watch': Colors.GREEN,
        'download': Colors.MAGENTA,
        'chat': Colors.WHITE,
        'unknown': Colors.DIM
    }
    return colors.get(action, Colors.DIM)

# ═══════════════════════════════════════════════════════════════════════
# DISPLAY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def clear_screen():
    """Clear terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')

def center_text(text, width=70):
    """Center text within a width"""
    padding = (width - len(text)) // 2
    return " " * padding + text

def format_time(timestamp):
    """Format timestamp nicely"""
    if not timestamp:
        return "Unknown"
    # Remove T and milliseconds
    ts = timestamp.replace("T", " ")
    if "." in ts:
        ts = ts.split(".")[0]
    return ts

def truncate(text, max_len=35):
    """Truncate text with ellipsis"""
    if not text:
        return ""
    if len(text) > max_len:
        return text[:max_len-2] + ".."
    return text

# ═══════════════════════════════════════════════════════════════════════
# FETCH DATA
# ═══════════════════════════════════════════════════════════════════════

def fetch_logs():
    """Fetch visitor logs from your deployed app"""
    try:
        response = requests.get(LOG_URL, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("visits", []), data.get("total", 0)
        else:
            return None, 0
    except Exception as e:
        return None, 0

# ═══════════════════════════════════════════════════════════════════════
# LIVE MONITOR (300ms refresh)
# ═══════════════════════════════════════════════════════════════════════

def show_live_monitor():
    """Real-time visitor monitor with 300ms refresh"""
    seen_ids = set()
    last_count = 0

    while True:
        try:
            logs, total = fetch_logs()

            if logs is None:
                clear_screen()
                print(Colors.RED + "❌ Connection lost! Retrying..." + Colors.RESET)
                time.sleep(REFRESH_MS / 1000)
                continue

            # Detect new visits
            new_visits = []
            for log in logs:
                log_id = log.get("timestamp", "") + log.get("ip", "") + log.get("action", "")
                if log_id not in seen_ids:
                    seen_ids.add(log_id)
                    new_visits.append(log)

            # Keep only last 1000 IDs to prevent memory bloat
            if len(seen_ids) > 1000:
                seen_ids = set(list(seen_ids)[-500:])

            clear_screen()

            # Header
            print(Colors.CYAN + BORDER_TOP)
            print(BORDER_SIDE + center_text("🕵️  KYRO SPY - LIVE VISITOR MONITOR", 68) + " " + BORDER_SIDE)
            print(BORDER_SIDE + center_text("Real-time tracking | " + str(REFRESH_MS) + "ms refresh", 68) + " " + BORDER_SIDE)
            print(BORDER_MID)

            # Stats bar
            stats = f"  📊 Total: {total}  |  🆕 New: {len(new_visits)}  |  🔄 Refresh: {REFRESH_MS}ms"
            print(BORDER_SIDE + stats.ljust(68) + " " + BORDER_SIDE)
            print(BORDER_MID)

            # Show last 8 visits (newest first)
            recent = list(reversed(logs[-8:])) if logs else []

            if not recent:
                print(BORDER_SIDE + "  😴 No visitors yet... Waiting for traffic...".ljust(68) + BORDER_SIDE)
            else:
                for i, entry in enumerate(recent):
                    # Determine if this is a NEW visit (flash it)
                    is_new = entry in new_visits
                    flash = Colors.BOLD if is_new else ""

                    device_emoji = get_device_emoji(
                        entry.get("device"),
                        entry.get("brand"),
                        entry.get("model"),
                        entry.get("is_mobile"),
                        entry.get("is_tablet"),
                        entry.get("is_pc")
                    )

                    action_emoji = get_action_emoji(entry.get("action"))
                    action_color = get_action_color(entry.get("action"))

                    # Build device name
                    brand = entry.get("brand", "")
                    model = entry.get("model", "")
                    device = entry.get("device", "Unknown")

                    if brand and model and brand != "Unknown":
                        device_name = f"{brand} {model}"
                    elif device and device != "Unknown":
                        device_name = device
                    else:
                        device_name = "Unknown"

                    # Line 1: Time + Action + IP
                    time_str = format_time(entry.get("timestamp"))
                    action_str = entry.get("action", "unknown").upper()
                    ip = entry.get("ip", "Unknown")

                    line1 = f"  {action_emoji} {action_color}{flash}{action_str:<12}{Colors.RESET} {Colors.DIM}{time_str}{Colors.RESET}"
                    line1_padded = line1.ljust(75) + BORDER_SIDE
                    print(BORDER_SIDE + line1_padded)

                    # Line 2: Device + OS
                    os_str = entry.get("os", "Unknown")
                    line2 = f"     {device_emoji} {device_name}  |  🖥️  {os_str}"
                    line2_padded = Colors.WHITE + line2.ljust(68) + Colors.RESET + BORDER_SIDE
                    print(BORDER_SIDE + line2_padded)

                    # Line 3: Browser + Details
                    browser = entry.get("browser", "Unknown")
                    details = entry.get("details", "")
                    line3 = f"     🌍 {browser}"
                    if details:
                        line3 += f"  |  📝 {truncate(details, 25)}"
                    line3_padded = Colors.DIM + line3.ljust(68) + Colors.RESET + BORDER_SIDE
                    print(BORDER_SIDE + line3_padded)

                    # Divider between entries (except last)
                    if i < len(recent) - 1:
                        print(BORDER_SIDE + DIVIDER[1:-1] + BORDER_SIDE)

            print(BORDER_BOT)
            print(Colors.DIM + "  Press Ctrl+C to exit  |  Watching for visitors..." + Colors.RESET)

            last_count = total
            time.sleep(REFRESH_MS / 1000)

        except KeyboardInterrupt:
            clear_screen()
            print(Colors.YELLOW + "\n👋 Monitor stopped." + Colors.RESET)
            time.sleep(1)
            break
        except Exception as e:
            clear_screen()
            print(Colors.RED + f"❌ Error: {e}" + Colors.RESET)
            time.sleep(1)

# ═══════════════════════════════════════════════════════════════════════
# SUMMARY VIEW
# ═══════════════════════════════════════════════════════════════════════

def show_summary():
    """Show beautiful summary statistics"""
    logs, total = fetch_logs()

    if not logs:
        print(Colors.RED + "❌ No data available!" + Colors.RESET)
        input("\nPress Enter...")
        return

    clear_screen()

    # Calculate stats
    actions = {}
    devices = {}
    brands = {}
    browsers = {}
    os_stats = {}
    mobile_count = 0
    pc_count = 0
    tablet_count = 0

    for entry in logs:
        # Actions
        action = entry.get("action", "unknown")
        actions[action] = actions.get(action, 0) + 1

        # Devices
        brand = entry.get("brand", "Unknown")
        if brand and brand != "Unknown":
            brands[brand] = brands.get(brand, 0) + 1

        device = entry.get("device", "Unknown")
        if device and device != "Unknown":
            devices[device] = devices.get(device, 0) + 1

        # Browsers (just family name)
        browser = entry.get("browser", "Unknown")
        browser_family = browser.split()[0] if browser else "Unknown"
        browsers[browser_family] = browsers.get(browser_family, 0) + 1

        # OS
        os_name = entry.get("os", "Unknown")
        os_family = os_name.split()[0] if os_name else "Unknown"
        os_stats[os_family] = os_stats.get(os_family, 0) + 1

        # Device types
        if entry.get("is_mobile"):
            mobile_count += 1
        elif entry.get("is_pc"):
            pc_count += 1
        elif entry.get("is_tablet"):
            tablet_count += 1

    # Display
    print(Colors.CYAN + BORDER_TOP)
    print(BORDER_SIDE + center_text("📊 KYRO SPY - VISITOR SUMMARY", 68) + " " + BORDER_SIDE)
    print(BORDER_MID)

    # Total stats
    print(BORDER_SIDE + Colors.BOLD + "  📈 OVERALL STATISTICS".ljust(68) + Colors.RESET + BORDER_SIDE)
    print(BORDER_SIDE + f"     Total Visits: {total}".ljust(68) + BORDER_SIDE)
    print(BORDER_SIDE + f"     📱 Mobile: {mobile_count}  |  💻 PC: {pc_count}  |  📱 Tablet: {tablet_count}".ljust(68) + BORDER_SIDE)
    print(BORDER_MID)

    # Top actions
    print(BORDER_SIDE + Colors.YELLOW + "  🔥 TOP ACTIONS".ljust(68) + Colors.RESET + BORDER_SIDE)
    for action, count in sorted(actions.items(), key=lambda x: -x[1])[:5]:
        emoji = get_action_emoji(action)
        bar = "█" * min(count, 20)
        print(BORDER_SIDE + f"     {emoji} {action:<15} {count:>4}  {bar}".ljust(68) + BORDER_SIDE)

    print(BORDER_MID)

    # Top brands
    print(BORDER_SIDE + Colors.GREEN + "  📱 TOP DEVICES".ljust(68) + Colors.RESET + BORDER_SIDE)
    for brand, count in sorted(brands.items(), key=lambda x: -x[1])[:5]:
        bar = "█" * min(count, 20)
        print(BORDER_SIDE + f"     📱 {brand:<20} {count:>4}  {bar}".ljust(68) + BORDER_SIDE)

    print(BORDER_MID)

    # Top browsers
    print(BORDER_SIDE + Colors.BLUE + "  🌍 TOP BROWSERS".ljust(68) + Colors.RESET + BORDER_SIDE)
    for browser, count in sorted(browsers.items(), key=lambda x: -x[1])[:5]:
        bar = "█" * min(count, 20)
        print(BORDER_SIDE + f"     🌐 {browser:<20} {count:>4}  {bar}".ljust(68) + BORDER_SIDE)

    print(BORDER_MID)

    # Top OS
    print(BORDER_SIDE + Colors.MAGENTA + "  💻 TOP OPERATING SYSTEMS".ljust(68) + Colors.RESET + BORDER_SIDE)
    for os_name, count in sorted(os_stats.items(), key=lambda x: -x[1])[:5]:
        bar = "█" * min(count, 20)
        print(BORDER_SIDE + f"     🖥️  {os_name:<20} {count:>4}  {bar}".ljust(68) + BORDER_SIDE)

    print(BORDER_BOT)
    input(Colors.DIM + "\nPress Enter to return..." + Colors.RESET)

# ═══════════════════════════════════════════════════════════════════════
# SEARCH HISTORY
# ═══════════════════════════════════════════════════════════════════════

def show_search_history():
    """Show what people searched for"""
    logs, total = fetch_logs()

    if not logs:
        print(Colors.RED + "❌ No data!" + Colors.RESET)
        input("\nPress Enter...")
        return

    searches = [e for e in logs if e.get("action") == "search"]

    clear_screen()
    print(Colors.YELLOW + BORDER_TOP)
    print(BORDER_SIDE + center_text("🔍 KYRO SPY - SEARCH HISTORY", 68) + " " + BORDER_SIDE)
    print(BORDER_MID)
    print(BORDER_SIDE + f"  Total Searches: {len(searches)}".ljust(68) + BORDER_SIDE)
    print(BORDER_MID)

    if not searches:
        print(BORDER_SIDE + "  😴 No searches yet...".ljust(68) + BORDER_SIDE)
    else:
        for entry in reversed(searches[-15:]):
            ts = format_time(entry.get("timestamp"))
            ip = entry.get("ip", "Unknown")
            details = entry.get("details", "")
            device = get_device_emoji(
                entry.get("device"), entry.get("brand"), entry.get("model"),
                entry.get("is_mobile"), entry.get("is_tablet"), entry.get("is_pc")
            )

            line = f"  [{ts}] {device} {ip}"
            print(BORDER_SIDE + line.ljust(68) + BORDER_SIDE)
            print(BORDER_SIDE + f"     🔍 {details}".ljust(68) + BORDER_SIDE)
            print(BORDER_SIDE + " ".ljust(68) + BORDER_SIDE)

    print(BORDER_BOT)
    input(Colors.DIM + "\nPress Enter to return..." + Colors.RESET)

# ═══════════════════════════════════════════════════════════════════════
# DOWNLOADS VIEW
# ═══════════════════════════════════════════════════════════════════════

def show_downloads():
    """Show what people downloaded"""
    logs, total = fetch_logs()

    if not logs:
        print(Colors.RED + "❌ No data!" + Colors.RESET)
        input("\nPress Enter...")
        return

    downloads = [e for e in logs if e.get("action") == "download"]

    clear_screen()
    print(Colors.MAGENTA + BORDER_TOP)
    print(BORDER_SIDE + center_text("⬇️  KYRO SPY - DOWNLOADS", 68) + " " + BORDER_SIDE)
    print(BORDER_MID)
    print(BORDER_SIDE + f"  Total Downloads: {len(downloads)}".ljust(68) + BORDER_SIDE)
    print(BORDER_MID)

    if not downloads:
        print(BORDER_SIDE + "  😴 No downloads yet...".ljust(68) + BORDER_SIDE)
    else:
        for entry in reversed(downloads[-15:]):
            ts = format_time(entry.get("timestamp"))
            ip = entry.get("ip", "Unknown")
            details = entry.get("details", "")
            device = get_device_emoji(
                entry.get("device"), entry.get("brand"), entry.get("model"),
                entry.get("is_mobile"), entry.get("is_tablet"), entry.get("is_pc")
            )

            line = f"  [{ts}] {device} {ip}"
            print(BORDER_SIDE + line.ljust(68) + BORDER_SIDE)
            print(BORDER_SIDE + f"     ⬇️  {truncate(details, 50)}".ljust(68) + BORDER_SIDE)
            print(BORDER_SIDE + " ".ljust(68) + BORDER_SIDE)

    print(BORDER_BOT)
    input(Colors.DIM + "\nPress Enter to return..." + Colors.RESET)

# ═══════════════════════════════════════════════════════════════════════
# WATCH HISTORY
# ═══════════════════════════════════════════════════════════════════════

def show_watch_history():
    """Show what people watched"""
    logs, total = fetch_logs()

    if not logs:
        print(Colors.RED + "❌ No data!" + Colors.RESET)
        input("\nPress Enter...")
        return

    watches = [e for e in logs if e.get("action") == "watch"]

    clear_screen()
    print(Colors.GREEN + BORDER_TOP)
    print(BORDER_SIDE + center_text("▶️  KYRO SPY - WATCH HISTORY", 68) + " " + BORDER_SIDE)
    print(BORDER_MID)
    print(BORDER_SIDE + f"  Total Watches: {len(watches)}".ljust(68) + BORDER_SIDE)
    print(BORDER_MID)

    if not watches:
        print(BORDER_SIDE + "  😴 No watches yet...".ljust(68) + BORDER_SIDE)
    else:
        for entry in reversed(watches[-15:]):
            ts = format_time(entry.get("timestamp"))
            ip = entry.get("ip", "Unknown")
            details = entry.get("details", "")
            device = get_device_emoji(
                entry.get("device"), entry.get("brand"), entry.get("model"),
                entry.get("is_mobile"), entry.get("is_tablet"), entry.get("is_pc")
            )

            line = f"  [{ts}] {device} {ip}"
            print(BORDER_SIDE + line.ljust(68) + BORDER_SIDE)
            print(BORDER_SIDE + f"     ▶️  {truncate(details, 50)}".ljust(68) + BORDER_SIDE)
            print(BORDER_SIDE + " ".ljust(68) + BORDER_SIDE)

    print(BORDER_BOT)
    input(Colors.DIM + "\nPress Enter to return..." + Colors.RESET)

# ═══════════════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════════

def main_menu():
    """Beautiful main menu"""
    while True:
        clear_screen()

        print(Colors.CYAN + BORDER_TOP)
        print(BORDER_SIDE + center_text("🕵️  KYRO SPY - VISITOR TRACKER", 68) + " " + BORDER_SIDE)
        print(BORDER_SIDE + center_text("Monitor your anime site visitors", 68) + " " + BORDER_SIDE)
        print(BORDER_MID)
        print(BORDER_SIDE + "  📡  1. LIVE MONITOR      - Real-time 300ms refresh".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + "  📊  2. SUMMARY           - Statistics & charts".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + "  🔍  3. SEARCH HISTORY    - What people searched".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + "  ▶️   4. WATCH HISTORY     - What people watched".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + "  ⬇️   5. DOWNLOADS         - What people downloaded".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + "  🚪  6. EXIT".ljust(68) + BORDER_SIDE)
        print(BORDER_BOT)

        choice = input(Colors.BOLD + "\n  Choose: " + Colors.RESET).strip()

        if choice == "1":
            try:
                show_live_monitor()
            except KeyboardInterrupt:
                pass
        elif choice == "2":
            show_summary()
        elif choice == "3":
            show_search_history()
        elif choice == "4":
            show_watch_history()
        elif choice == "5":
            show_downloads()
        elif choice == "6":
            clear_screen()
            print(Colors.GREEN + "\n  👋 Goodbye! Happy spying! 🕵️" + Colors.RESET)
            time.sleep(1)
            break
        else:
            print(Colors.RED + "\n  ❌ Invalid choice!" + Colors.RESET)
            time.sleep(1)

# ═══════════════════════════════════════════════════════════════════════
# START
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "YOUR_APP_URL_HERE" in LOG_URL:
        clear_screen()
        print(Colors.YELLOW + BORDER_TOP)
        print(BORDER_SIDE + center_text("⚠️  SETUP REQUIRED", 68) + " " + BORDER_SIDE)
        print(BORDER_MID)
        print(BORDER_SIDE + "  You need to set your app URL!".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + " ".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + "  Edit this file and change line 22:".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + " ".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + Colors.BOLD + "  LOG_URL = "https://your-app.onrender.com/admin/logs-json"".ljust(68) + Colors.RESET + BORDER_SIDE)
        print(BORDER_SIDE + " ".ljust(68) + BORDER_SIDE)
        print(BORDER_SIDE + "  Replace with your actual deployed app URL.".ljust(68) + BORDER_SIDE)
        print(BORDER_BOT)
        input(Colors.DIM + "\n  Press Enter to exit..." + Colors.RESET)
    else:
        # Test connection first
        clear_screen()
        print(Colors.CYAN + "🔗 Connecting to " + LOG_URL + "..." + Colors.RESET)
        try:
            test = requests.get(LOG_URL, timeout=5)
            if test.status_code == 200:
                print(Colors.GREEN + "✅ Connected! Starting KYRO SPY..." + Colors.RESET)
                time.sleep(1)
                main_menu()
            else:
                print(Colors.RED + f"❌ Server returned {test.status_code}" + Colors.RESET)
                input("\nPress Enter...")
        except Exception as e:
            print(Colors.RED + f"❌ Connection failed: {e}" + Colors.RESET)
            input("\nPress Enter...")
