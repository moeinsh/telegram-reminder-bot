# Telegram Reminder Bot (Python + python-telegram-bot) — sample project

A Telegram bot that lets any chat schedule reminders. Set one with
`/remind 30 Call the client`, list upcoming ones with `/list`, cancel with
`/cancel <id>` — the bot delivers each reminder as a Telegram message when
its time comes.

## Highlights

- **Full reminder workflow** — `/start`, `/remind <minutes> <message>`,
  `/list`, `/cancel <id>`, with friendly error messages on bad input
  (non-numeric or non-positive minutes, missing message, unknown id)
- **Persistent storage** — reminders live in `reminders.json` (atomic
  temp-file writes), so nothing is lost when the bot restarts; corrupt or
  missing files fall back to an empty store instead of crashing
- **Async scheduling** — `python-telegram-bot`'s `JobQueue` runs a delivery
  job every 30 seconds that sends due reminders and drops them from the
  store; per-reminder send failures (blocked bot, bad chat id) are caught
  and logged instead of killing the loop
- **Testable core** — all parsing, scheduling and persistence logic is in
  plain synchronous functions; `selftest.py` proves them with 23 checks and
  needs no bot token (see "Verify it" below)

## Command list

| Command | What it does |
|---|---|
| `/start` | Welcome message + command help |
| `/remind <minutes> <message>` | Schedule a reminder (minutes can be fractional, e.g. `1.5`) |
| `/list` | Show your upcoming reminders, soonest first |
| `/cancel <id>` | Cancel an upcoming reminder by its id |

## Run it

1. Create a bot: open Telegram, chat with **@BotFather**, send `/newbot`,
   follow the prompts and copy the token it gives you.
2. Install and run:

```bash
pip install "python-telegram-bot[job-queue]>=21"
export TELEGRAM_BOT_TOKEN='<paste your token here>'
python telegram_reminder_bot.py
```

3. Open your bot in Telegram, send `/remind 1 Test message`, and a minute
   later it replies with your reminder.

## Verify it (no token needed)

```bash
python selftest.py
```

Expected: `All 23 self-test checks passed.` — parsing (valid/invalid
`/remind` input), id assignment, per-chat listing, cancellation rules,
due-reminder detection, and JSON save/load round-trips including corrupt
and missing store files.

**Live-test note:** live Telegram send/receive was not tested in this
sandbox — no BotFather token was available, so only the offline logic
(`selftest.py`, 23 checks) was run. The `deliver_due` send path is
straightforward `python-telegram-bot` usage; verify it with your own token
via the "Try it live" steps above.

## Scope note (honest)

This is a demonstration sample showing my bot-development workflow end to
end — command handlers, background scheduling, persistence, and tested
logic. It is a single-process long-polling bot: a production deployment
for heavy use would add a real database instead of a JSON file, webhook
mode behind HTTPS instead of polling, and per-user rate limiting. No
client, no fake data — the sample `reminders.json` is hand-made demo data
showing the store format (its chat ids are placeholders).

## Files

- `telegram_reminder_bot.py` — the bot (logic + Telegram wiring)
- `selftest.py` — 23-check self-test, token-free
- `reminders.json` — sample store showing the JSON format
- `card-telegram.png` — preview card

---

**Author:** Moein Shahidi — [@moeinsh](https://github.com/moeinsh)

© 2026 Moein Shahidi. Released under the MIT License.
