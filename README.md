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

## State Files

- `python -m yeonsu_monitor login` writes the authenticated Playwright session to `.codex-state/storage_state.json`.
- Vacancy change detection stores the last sent snapshot in `.codex-state/snapshot.json`.
- These files are reused between runs, so existing local state is preserved unless you delete them manually.

## Troubleshooting

### Login failed with `ReferenceError: login is not defined`

- Cause: the old login flow tried to run `page.evaluate("login()")`, but the Yeonsu page does not expose a global `login()` function.
- Fix: the login flow now opens `/loginLayer` directly and submits credentials through the real `/loginProcAjax` endpoint.
- Result: the authenticated cookies are saved into `.codex-state/storage_state.json`, so later runs reuse the existing session instead of starting from scratch.

### Login page opened but no request was sent

- Cause: the site login flow depends on front-end behavior that is brittle in headless automation.
- Fix: the session helper now performs the login request with `requests`, then stores the returned cookies in Playwright storage state.
- Result: the login step no longer depends on JavaScript click handlers or NetFunnel timing.

## Notes

- The vacancy check sends Telegram only when the result changes.
- The daily summary always sends the current status once a day.
- GitHub Actions schedules are best effort and can run a few minutes late.
