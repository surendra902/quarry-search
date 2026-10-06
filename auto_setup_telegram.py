"""Auto-detect chat ID from Telegram bot updates, configure .env, and test dispatch."""
import os
import sys
import time
from pathlib import Path
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = None  # Loaded at runtime; never store credentials in source control.
BOT_USERNAME = "suri8bot"
ENV_PATH = Path(__file__).resolve().parent / ".env"


def update_env(token: str, chat_id: str):
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    found_token = False
    found_chat = False
    for line in lines:
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            new_lines.append(f"TELEGRAM_BOT_TOKEN={token}")
            found_token = True
        elif line.startswith("TELEGRAM_CHAT_ID="):
            new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
            found_chat = True
        else:
            new_lines.append(line)
    if not found_token:
        new_lines.append(f"TELEGRAM_BOT_TOKEN={token}")
    if not found_chat:
        new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def check_updates():
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    resp = requests.get(url, timeout=10)
    data = resp.json()
    if not data.get("ok"):
        return None
    updates = data.get("result", [])
    if not updates:
        return None
    # Get the latest message
    for upd in reversed(updates):
        msg = upd.get("message") or upd.get("channel_post") or upd.get("my_chat_member")
        if msg and "chat" in msg:
            chat = msg["chat"]
            return {
                "chat_id": str(chat["id"]),
                "type": chat.get("type", "private"),
                "username": chat.get("username", ""),
                "first_name": chat.get("first_name", ""),
                "text": (msg.get("text") or "") if isinstance(msg, dict) else ""
            }
    return None


def main():
    global TOKEN
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not TOKEN and ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "TELEGRAM_BOT_TOKEN":
                TOKEN = value.strip().strip("\"'")
                break
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in the environment or ignored .env file first.")
    print("=" * 65)
    print(f"TELEGRAM AUTO-SETUP FOR @{BOT_USERNAME}")
    print("=" * 65)
    print(f"Bot Link: https://t.me/{BOT_USERNAME}")
    print("Checking for existing messages...")
    
    info = check_updates()
    if not info:
        print("\n[!] No message received yet.")
        print(f"--> Please open Telegram and send /start or any message to: https://t.me/{BOT_USERNAME}")
        print("--> (Or add @suri8bot to your Telegram group and send a message)")
        print("\nWaiting up to 45 seconds for your message...")
        for i in range(45):
            time.sleep(2)
            info = check_updates()
            if info:
                break
            sys.stdout.write(f"\rListening... {i * 2 + 2}s elapsed")
            sys.stdout.flush()
        print()

    if not info:
        print("\n[TIMEOUT] Still waiting for message. Once you send /start to @suri8bot, run:")
        print("    python auto_setup_telegram.py")
        sys.exit(1)

    chat_id = info["chat_id"]
    user_desc = info["username"] or info["first_name"] or "User"
    chat_type = info["type"]

    print("\n" + "=" * 65)
    print(f"SUCCESS! Detected {chat_type} chat from: {user_desc}")
    print(f"Chat ID: {chat_id}")
    print("=" * 65)

    # Update .env
    update_env(TOKEN, chat_id)
    print("[1/2] Saved TELEGRAM_CHAT_ID to .env")

    # Send confirmation test message
    test_msg = (
        "<b>Quarry Telegram delivery test</b>\n\n"
        "This message confirms only this test delivery.\n"
        "Collector scheduling, future delivery and referral redemption are not validated by this test."
    )
    send_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": test_msg,
        "parse_mode": "HTML"
    }
    r = requests.post(send_url, json=payload, timeout=10)
    if r.status_code == 200:
        print("[2/2] Test message dispatched! Check your Telegram chat with @suri8bot.")
    else:
        print("[WARN] Message delivery returned:", r.status_code, r.text)

    print("\nNext step: Run the 24/7 continuous harvester with:")
    print("    python run_harvester.py")


if __name__ == "__main__":
    main()
