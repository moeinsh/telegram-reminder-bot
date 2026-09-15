"""Sample project: Telegram reminder bot (python-telegram-bot v21+).

Commands:
    /start                - welcome message + command help
    /remind <min> <text>  - schedule a reminder (e.g. /remind 30 Call the client)
    /list                 - show your upcoming reminders
    /cancel <id>          - cancel a reminder by id

Reminders persist in reminders.json, so they survive bot restarts. A JobQueue
repeating job checks for due reminders every 30 seconds and delivers them.

All parsing / scheduling / persistence logic lives in plain, synchronous
functions below so it can be unit-tested without a bot token (see selftest.py).
The async handlers at the bottom only wire those functions to Telegram.
"""
import json
import os
import time

STORE_PATH = os.environ.get("REMINDER_STORE", "reminders.json")

WELCOME = (
    "Hi! I'm a reminder bot.\n\n"
    "Commands:\n"
    "/remind <minutes> <message> - set a reminder\n"
    "/list - show your upcoming reminders\n"
    "/cancel <id> - cancel a reminder\n\n"
    "Example: /remind 30 Call the client"
)


# ---------------------------------------------------------------------------
# Pure logic (unit-testable, no Telegram needed)
# ---------------------------------------------------------------------------

def new_store():
    """Empty reminder store."""
    return {"next_id": 1, "reminders": []}


def load_store(path=STORE_PATH):
    """Load the JSON store; tolerate a missing or corrupt file."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "reminders" not in data:
            return new_store()
        if "next_id" not in data:
            used = [r.get("id", 0) for r in data["reminders"]]
            data["next_id"] = (max(used) if used else 0) + 1
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return new_store()


def save_store(store, path=STORE_PATH):
    """Write the store atomically (temp file + rename)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def parse_remind_args(text):
    """Parse '<minutes> <message>' from a /remind command.

    Returns (minutes: float, message: str). Raises ValueError with a
    user-friendly message on bad input.
    """
    parts = text.strip().split(None, 1)
    if len(parts) < 2:
        raise ValueError(
            "Usage: /remind <minutes> <message>\nExample: /remind 30 Call the client"
        )
    raw_minutes, message = parts
    try:
        minutes = float(raw_minutes)
    except ValueError:
        raise ValueError(
            f"'{raw_minutes}' is not a number.\n"
            "Usage: /remind <minutes> <message>"
        )
    if minutes <= 0:
        raise ValueError("Minutes must be greater than 0.")
    if not message.strip():
        raise ValueError(
            "Please include a reminder message.\n"
            "Usage: /remind <minutes> <message>"
        )
    return minutes, message.strip()


def add_reminder(store, chat_id, minutes, message, now=None):
    """Schedule a reminder; returns the created reminder dict."""
    now = time.time() if now is None else now
    rid = store.get("next_id", 1)
    reminder = {
        "id": rid,
        "chat_id": chat_id,
        "message": message,
        "due_at": now + minutes * 60,
        "created_at": now,
    }
    store["reminders"].append(reminder)
    store["next_id"] = rid + 1
    return reminder


def list_reminders(store, chat_id, now=None):
    """Upcoming reminders for one chat, soonest first."""
    now = time.time() if now is None else now
    upcoming = [
        r for r in store["reminders"]
        if r["chat_id"] == chat_id and r["due_at"] > now
    ]
    return sorted(upcoming, key=lambda r: r["due_at"])


def cancel_reminder(store, chat_id, reminder_id, now=None):
    """Cancel an upcoming reminder. Returns True if one was removed."""
    now = time.time() if now is None else now
    for r in store["reminders"]:
        if r["id"] == reminder_id and r["chat_id"] == chat_id and r["due_at"] > now:
            store["reminders"].remove(r)
            return True
    return False


def due_reminders(store, now=None):
    """Reminders whose time has come (any chat)."""
    now = time.time() if now is None else now
    return [r for r in store["reminders"] if r["due_at"] <= now]


def remove_reminder(store, reminder_id):
    store["reminders"] = [r for r in store["reminders"] if r["id"] != reminder_id]


def format_reminder(reminder, now=None):
    """One-line human summary, e.g. '#2 in ~25 min — Call the client'."""
    now = time.time() if now is None else now
    mins = max(0, int(round((reminder["due_at"] - now) / 60)))
    return f"#{reminder['id']} in ~{mins} min \u2014 {reminder['message']}"


# ---------------------------------------------------------------------------
# Telegram wiring (thin async handlers)
# ---------------------------------------------------------------------------

def _telegram_handlers():
    """Import telegram lazily so the pure logic stays dependency-free."""
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, ContextTypes,
    )
    return Update, ApplicationBuilder, CommandHandler, ContextTypes


async def start(update, context):
    await update.message.reply_text(WELCOME)


async def remind_cmd(update, context):
    try:
        minutes, message = parse_remind_args(" ".join(context.args))
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    store = load_store()
    reminder = add_reminder(store, update.effective_chat.id, minutes, message)
    save_store(store)
    await update.message.reply_text(
        f"Reminder #{reminder['id']} set \u2014 I'll ping you in {minutes:g} minutes."
    )


async def list_cmd(update, context):
    store = load_store()
    upcoming = list_reminders(store, update.effective_chat.id)
    if not upcoming:
        await update.message.reply_text(
            "No upcoming reminders. Set one with /remind <minutes> <message>."
        )
        return
    lines = ["Your upcoming reminders:"]
    lines += [format_reminder(r) for r in upcoming]
    await update.message.reply_text("\n".join(lines))


async def cancel_cmd(update, context):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /cancel <id>  (see /list for ids)")
        return
    rid = int(context.args[0])
    store = load_store()
    if cancel_reminder(store, update.effective_chat.id, rid):
        save_store(store)
        await update.message.reply_text(f"Reminder #{rid} cancelled.")
    else:
        await update.message.reply_text(
            "No upcoming reminder with that id. See /list."
        )


async def deliver_due(context):
    """JobQueue job: send every due reminder, then drop it from the store."""
    store = load_store()
    changed = False
    for reminder in due_reminders(store):
        try:
            await context.bot.send_message(
                chat_id=reminder["chat_id"],
                text=f"\u23f0 Reminder: {reminder['message']}",
            )
        except Exception as exc:  # e.g. blocked bot / bad chat id
            print(f"Could not deliver reminder #{reminder['id']}: {exc}")
        remove_reminder(store, reminder["id"])
        changed = True
    if changed:
        save_store(store)


def main():
    Update, ApplicationBuilder, CommandHandler, ContextTypes = _telegram_handlers()  # noqa: F841

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set.\n"
            "Create a bot with @BotFather, then run:\n"
            "  export TELEGRAM_BOT_TOKEN='<your token>'\n"
            "  python telegram_reminder_bot.py\n"
            "See README.md for details."
        )

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remind", remind_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.job_queue.run_repeating(deliver_due, interval=30, first=5)

    print("Reminder bot is running (Ctrl+C to stop).")
    app.run_polling()


if __name__ == "__main__":
    main()
