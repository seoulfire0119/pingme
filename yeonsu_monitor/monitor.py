from __future__ import annotations

import json
from collections import defaultdict
from datetime import date as date_cls
from pathlib import Path

from .config import Config, Target
from .telegram import send_telegram

_RESORT_NAMES = {
    "00003002": "속초연수원",
    "00003003": "서천연수원",
    "00003004": "수안보연수원",
    "00003005": "제주연수원",
    "00003006": "통영마리나연수원",
    "00003008": "경주연수원",
    "00003009": "엘리시안강촌연수원",
    "00003010": "블룸비스타연수원",
    "00003011": "여수히든베이연수원",
    "00003012": "여수베네치아연수원",
}

_WEEKDAY_KR = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}


def _goto_entry_page(page, url: str) -> None:
    # The target site can keep background scripts active for a long time, so
    # only wait for the navigation to commit.
    page.goto(url, wait_until="commit", timeout=120000)


def _load_previous_snapshot(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_snapshot(path: Path, snapshot: dict[str, object]) -> None:
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def _should_send_vacancy_alert(snapshot_path: Path, resort_dates: dict[str, list[str]]) -> bool:
    """Persist the latest vacancy snapshot and return True only when it changed."""
    if not resort_dates:
        return False

    previous = _load_previous_snapshot(snapshot_path)
    if previous.get("last_vacancy") == resort_dates:
        return False

    previous["last_vacancy"] = resort_dates
    _save_snapshot(snapshot_path, previous)
    return True


def _fetch_room_list(page, base_url: str, yeonsu_gbn: str, year_month: str) -> dict:
    response = page.request.post(
        f"{base_url}/onlineRsv/rsvRoomList",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        form={
            "parameter": yeonsu_gbn,
            "year_month": year_month,
        },
        timeout=30000,
    )
    result = response.text()
    if result.strip().startswith("<script>location.href='/main';</script>"):
        raise RuntimeError("Login session expired or missing.")
    try:
        return json.loads(result)
    except json.JSONDecodeError as e:
        snippet = result.strip().replace("\n", " ")[:200]
        raise RuntimeError(f"Unexpected vacancy response ({response.status}): {snippet}") from e


def _matches_target(item: dict, target: Target) -> bool:
    room_fields = {
        "A": "atye_room_num",
        "B": "btye_room_num",
        "C": "ctye_room_num",
        "O": "otye_room_num",
        "18P": "atye_room_num",
        "24P": "ctye_room_num",
    }
    for room_type in target.room_types:
        field = room_fields.get(room_type)
        if field is None:
            continue
        if int(item.get(field, 0) or 0) > 0:
            return True
    return False


def _has_available_slot(data: dict, target: Target) -> bool:
    for item in data.get("rsvPsblList", []):
        if str(item.get("rming_dt", ""))[:10] == target.date:
            if _matches_target(item, target):
                return True
    return False


def _date_label(date_str: str) -> str:
    d = date_cls.fromisoformat(date_str)
    return f"{d.month}/{d.day}({_WEEKDAY_KR[d.weekday()]})"


def _send_resort_summary(config: Config, resort_dates: dict[str, list[str]], test_mode: bool) -> None:
    prefix = "[TEST] " if test_mode else ""
    if resort_dates:
        lines = [f"{prefix}Vacancy summary"]
        for resort_name, dates in resort_dates.items():
            date_labels = ", ".join(_date_label(d) for d in sorted(dates))
            display_name = _RESORT_NAMES.get(resort_name, resort_name)
            lines.append(f"- {display_name}: {date_labels}")
        lines.append("")
        lines.append("https://yeonsu.eseoul.go.kr/onlineRsv/list")
    else:
        lines = [f"{prefix}No vacancies"]
    try:
        send_telegram(config.telegram_bot_token, config.telegram_chat_id, "\n".join(lines))
    except Exception as e:
        print(f"[telegram error] {e}")


def _poll_once(page, config: Config) -> dict[str, list[str]]:
    groups: dict[tuple[str, str], list[Target]] = {}
    for target in config.targets:
        groups.setdefault((target.yeonsu_gbn, target.year_month), []).append(target)

    resort_dates: dict[str, list[str]] = defaultdict(list)
    for (yeonsu_gbn, year_month), targets in groups.items():
        data = _fetch_room_list(page, config.base_url, yeonsu_gbn, year_month)
        for target in targets:
            if _has_available_slot(data, target):
                resort_dates[yeonsu_gbn].append(target.date)

    return dict(resort_dates)


def _poll_once_local(config: Config) -> dict[str, list[str]]:
    from playwright.sync_api import sync_playwright

    state_path = config.storage_dir / "storage_state.json"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        _goto_entry_page(page, f"{config.base_url}/main")
        result = _poll_once(page, config)
        browser.close()
    return result


def run_check(config: Config) -> None:
    """Free-only mode: run once and send a notification only when vacancies changed."""
    from playwright.sync_api import sync_playwright

    state_path = config.storage_dir / "storage_state.json"
    snapshot_path = config.storage_dir / "snapshot.json"
    print("Checking vacancies...", flush=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = browser.new_context(
                storage_state=str(state_path) if state_path.exists() else None,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = context.new_page()
            _goto_entry_page(page, f"{config.base_url}/main")
            resort_dates = _poll_once(page, config)
            browser.close()

        if _should_send_vacancy_alert(snapshot_path, resort_dates):
            _send_resort_summary(config, resort_dates, test_mode=False)
            print("Vacancy alert sent.", flush=True)
        else:
            print("No new vacancy.", flush=True)
    except Exception as e:
        print(f"[error] {e}", flush=True)
        try:
            send_telegram(config.telegram_bot_token, config.telegram_chat_id, f"Check failed: {e}")
        except Exception:
            pass
        raise


def run_summary(config: Config) -> None:
    """Free-only mode: send one daily summary at 11 AM KST."""
    from playwright.sync_api import sync_playwright

    state_path = config.storage_dir / "storage_state.json"
    print("Sending daily summary...", flush=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = browser.new_context(
                storage_state=str(state_path) if state_path.exists() else None,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = context.new_page()
            _goto_entry_page(page, f"{config.base_url}/main")
            resort_dates = _poll_once(page, config)
            browser.close()

        _send_resort_summary(config, resort_dates, test_mode=False)
        print("Daily summary sent.", flush=True)
    except Exception as e:
        print(f"[error] {e}", flush=True)
        try:
            send_telegram(config.telegram_bot_token, config.telegram_chat_id, f"Summary failed: {e}")
        except Exception:
            pass
        raise
