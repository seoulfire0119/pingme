# Yeonsu Alert Monitor

Free-only setup for Yeonsu resort vacancy alerts.

## What this does

- Checks for new vacancies every 5 minutes with GitHub Actions.
- Sends a daily summary at 11:00 KST with GitHub Actions.
- Keeps working even when your computer is off.

## What this does not do

- It does not provide an always-on Telegram bot.
- A `/check` message will not get an instant reply in the free setup.

## Workflow layout

- `.github/workflows/monitor.yml` runs the 5-minute vacancy check.
- `.github/workflows/daily_summary.yml` runs the daily 11:00 KST summary.

## GitHub secrets

Set these secrets in the repository:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `YEONSU_USERNAME`
- `YEONSU_PASSWORD`

## Local commands

- `python -m yeonsu_monitor login`
- `python -m yeonsu_monitor check`
- `python -m yeonsu_monitor summary`

## Notes

- The vacancy check sends Telegram only when the result changes.
- The daily summary always sends the current status once a day.
- GitHub Actions schedules are best effort and can run a few minutes late.
