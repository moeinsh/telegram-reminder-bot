"""Self-test for telegram_reminder_bot.py.

Exercises the parsing / scheduling / persistence logic only — no Telegram
bot token or network needed. Run with:

    python selftest.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_reminder_bot import (
    add_reminder,
    cancel_reminder,
    due_reminders,
    format_reminder,
    list_reminders,
    load_store,
    new_store,
    parse_remind_args,
    save_store,
)

passed = 0


def check(name, condition):
    global passed
    assert condition, f"FAILED: {name}"
    passed += 1
    print(f"  PASS  {name}")


def check_raises(name, func, *args):
    global passed
    try:
        func(*args)
    except ValueError:
        passed += 1
        print(f"  PASS  {name}")
        return
    raise AssertionError(f"FAILED (no ValueError raised): {name}")


NOW = 1_700_000_000.0  # fixed clock so the test is deterministic


def main():
    print("parse_remind_args:")
    check("integer minutes", parse_remind_args("30 Call the client") == (30.0, "Call the client"))
    check("fractional minutes", parse_remind_args("1.5 take a break") == (1.5, "take a break"))
    check("extra whitespace tolerated",
          parse_remind_args("  10   stretch your legs  ") == (10.0, "stretch your legs"))
    check_raises("empty input", parse_remind_args, "")
    check_raises("missing message", parse_remind_args, "30")
    check_raises("non-numeric minutes", parse_remind_args, "soon Call me")
    check_raises("zero minutes", parse_remind_args, "0 do it")
    check_raises("negative minutes", parse_remind_args, "-5 do it")

    print("add / list / cancel:")
    store = new_store()
    r1 = add_reminder(store, chat_id=111, minutes=30, message="Call the client", now=NOW)
    r2 = add_reminder(store, chat_id=111, minutes=5, message="Stand up", now=NOW)
    r3 = add_reminder(store, chat_id=222, minutes=10, message="Other chat", now=NOW)
    check("ids increment", (r1["id"], r2["id"], r3["id"]) == (1, 2, 3))
    check("due_at = now + minutes*60",
          r1["due_at"] == NOW + 30 * 60 and r2["due_at"] == NOW + 5 * 60)

    upcoming = list_reminders(store, 111, now=NOW)
    check("lists only own chat", [r["id"] for r in upcoming] == [2, 1])
    check("sorted soonest first", upcoming[0]["due_at"] < upcoming[1]["due_at"])

    check("cancel existing", cancel_reminder(store, 111, 2, now=NOW) is True)
    check("cancelled one is gone",
          [r["id"] for r in list_reminders(store, 111, now=NOW)] == [1])
    check("cancel unknown id", cancel_reminder(store, 111, 99, now=NOW) is False)
    check("cancel other chat's reminder", cancel_reminder(store, 111, 3, now=NOW) is False)

    print("due reminders:")
    store2 = new_store()
    add_reminder(store2, 111, minutes=60, message="later", now=NOW)
    add_reminder(store2, 111, minutes=0.001, message="almost now", now=NOW)
    due = due_reminders(store2, now=NOW + 120)
    check("past-due detected", len(due) == 1 and due[0]["message"] == "almost now")
    check("format_reminder", format_reminder(r1, now=NOW) == "#1 in ~30 min \u2014 Call the client")

    print("persistence (JSON round-trip):")
    store3 = new_store()
    add_reminder(store3, 111, minutes=45, message="Persist me", now=NOW)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "reminders.json")
        save_store(store3, path)
        check("store file written", os.path.exists(path))
        loaded = load_store(path)
        check("reminders survive round-trip",
              len(loaded["reminders"]) == 1
              and loaded["reminders"][0]["message"] == "Persist me"
              and loaded["reminders"][0]["due_at"] == NOW + 45 * 60)
        check("next_id continues", loaded["next_id"] == 2)
        check("missing file -> empty store", load_store(os.path.join(tmp, "nope.json")) == new_store())
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        check("corrupt file -> empty store", load_store(path) == new_store())

    print(f"\nAll {passed} self-test checks passed.")


if __name__ == "__main__":
    main()
