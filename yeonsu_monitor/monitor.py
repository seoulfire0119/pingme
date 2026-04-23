from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import date as date_cls, datetime
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


def _load_previous_snapshot(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_snapshot(path: Path, snapshot: dict[str, object]) -> None:
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_room_list(page, base_url: str, yeonsu_gbn: str, year_month: str) -> dict:
    """브라우저 page.evaluate()로 AJAX 호출 — 실제 브라우저 컨텍스트 사용."""
    result = page.evaluate(
        """async ([base, gbn, ym]) => {
            const resp = await fetch(base + '/onlineRsv/rsvRoomList', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json, text/javascript, */*; q=0.01'
                },
                body: 'parameter=' + encodeURIComponent(gbn) + '&year_month=' + encodeURIComponent(ym)
            });
            return await resp.text();
        }""",
        [base_url, yeonsu_gbn, year_month],
    )
    if result.strip().startswith("<script>location.href='/main';</script>"):
        raise RuntimeError("Login session expired or missing.")
    return json.loads(result)




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
    """resort_dates: {연수원명: [가능날짜, ...]} — 가능한 연수원만 포함"""
    prefix = "🔍 [테스트] " if test_mode else ""
    if resort_dates:
        lines = [f"{prefix}✅ 빈자리 현황\n"]
        for resort_name, dates in resort_dates.items():
            date_labels = ", ".join(_date_label(d) for d in sorted(dates))
            lines.append(f"📍 {resort_name}: {date_labels}")
        lines.append("\n👉 https://yeonsu.eseoul.go.kr/onlineRsv/list")
    else:
        lines = [f"{prefix}빈자리 없음"]
    try:
        send_telegram(config.telegram_bot_token, config.telegram_chat_id, "\n".join(lines))
    except Exception as e:
        print(f"[텔레그램 전송 실패] {e}")


def _poll_once(page, config: Config) -> dict[str, list[str]]:
    """API 한 사이클 호출 후 resort_name → [available dates] 반환."""
    groups: dict[tuple[str, str], list[Target]] = {}
    for target in config.targets:
        groups.setdefault((target.yeonsu_gbn, target.year_month), []).append(target)

    resort_dates: dict[str, list[str]] = defaultdict(list)
    for (yeonsu_gbn, year_month), targets in groups.items():
        data = _fetch_room_list(page, config.base_url, yeonsu_gbn, year_month)
        for target in targets:
            if _has_available_slot(data, target):
                resort = _RESORT_NAMES.get(target.yeonsu_gbn, target.yeonsu_gbn)
                resort_dates[resort].append(target.date)

    return dict(resort_dates)


def _poll_once_local(config: Config) -> dict[str, list[str]]:
    """로컬 실행용 — Playwright로 세션 로드 후 조회."""
    from playwright.sync_api import sync_playwright

    state_path = config.storage_dir / "storage_state.json"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        page.goto(f"{config.base_url}/main", wait_until="domcontentloaded", timeout=60000)
        result = _poll_once(page, config)
        browser.close()
    return result


def run_check(config: Config) -> None:
    """현재 현황을 즉시 텔레그램으로 전송하고 종료 (Playwright 기반)."""
    from playwright.sync_api import sync_playwright

    state_path = config.storage_dir / "storage_state.json"
    print("현황 조회 중...", flush=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = browser.new_context(
                storage_state=str(state_path),
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = context.new_page()
            page.goto(f"{config.base_url}/main", wait_until="domcontentloaded", timeout=60000)
            resort_dates = _poll_once(page, config)
            browser.close()
        _send_resort_summary(config, resort_dates, test_mode=False)
        print("전송 완료.")
    except Exception as e:
        print(f"[오류] {e}", flush=True)
        try:
            send_telegram(config.telegram_bot_token, config.telegram_chat_id, f"⚠️ 조회 실패: {e}")
        except Exception:
            pass
        raise


def run_monitor(config: Config, test_mode: bool = False) -> None:
    state_path = config.storage_dir / "storage_state.json"
    snapshot_path = config.storage_dir / "snapshot.json"
    previous = _load_previous_snapshot(snapshot_path)
    last_daily_date: str | None = None

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(
            storage_state=str(state_path) if state_path.exists() else None,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto(f"{config.base_url}/main", wait_until="domcontentloaded", timeout=60000)

        while True:
            now = datetime.now()
            mode = " [테스트모드]" if test_mode else ""
            print(f"[{now.strftime('%H:%M:%S')}] 체크 시작...{mode}", flush=True)

            try:
                resort_dates = _poll_once(page, config)
            except RuntimeError as e:
                if "Login session expired" in str(e):
                    print("[오류] 로그인 세션이 만료됐습니다.")
                    try:
                        send_telegram(
                            config.telegram_bot_token,
                            config.telegram_chat_id,
                            "⚠️ 세션 만료\n로그인 후 storage_state.json을 갱신하고 watch를 다시 실행해주세요.",
                        )
                    except Exception:
                        pass
                    break
                raise

            has_any = bool(resort_dates)
            print(f"  빈자리: {list(resort_dates.keys()) if has_any else '없음'}", flush=True)

            # 빈자리 새로 발생 시 즉시 알림
            if has_any and previous.get("last_vacancy") != resort_dates:
                previous["last_vacancy"] = resort_dates
                _save_snapshot(snapshot_path, previous)
                _send_resort_summary(config, resort_dates, test_mode=False)

            # 테스트 모드: 매 사이클 전송
            if test_mode:
                _send_resort_summary(config, resort_dates, test_mode=True)

            # 매일 오전 11시 정기 요약
            today_str = now.strftime("%Y-%m-%d")
            if now.hour == 11 and last_daily_date != today_str:
                last_daily_date = today_str
                print("[오전 11시 정기 알림 전송]", flush=True)
                _send_resort_summary(config, resort_dates, test_mode=False)

            time.sleep(config.poll_interval_seconds)
