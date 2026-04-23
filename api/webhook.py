from http.server import BaseHTTPRequestHandler
from collections import defaultdict
from datetime import date
import calendar
import json
import os

import requests as req
from playwright.sync_api import sync_playwright

RESORT_NAMES = {
    "00003002": "문학수련관",
    "00003003": "청소년수련관",
    "00003004": "선학캠핑장",
    "00003005": "송도수련관",
    "00003006": "영종복합문화센터",
    "00003008": "경인수련관",
    "00003009": "남동청소년수련관",
    "00003010": "부평아트센터",
    "00003011": "계양아라온",
    "00003012": "서구문화회관",
}
WEEKDAY_KR = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
BASE_URL = "https://yeonsu.eseoul.go.kr"
ROOM_FIELDS = {
    "A": "atye_room_num",
    "B": "btye_room_num",
    "C": "ctye_room_num",
    "O": "otye_room_num",
}
REQUEST_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def _current_months() -> list[str]:
    today = date.today()
    months = []
    for delta in (0, 1):
        m = today.month + delta
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        months.append(f"{y}.{m:02d}")
    return months


def _target_days(year_month: str) -> list[str]:
    year, month = map(int, year_month.split("."))
    today = date.today().isoformat()
    days = []
    for week in calendar.monthcalendar(year, month):
        for wd in (calendar.FRIDAY, calendar.SATURDAY, calendar.SUNDAY):
            day = week[wd]
            if day != 0:
                d = f"{year}-{month:02d}-{day:02d}"
                if d >= today:
                    days.append(d)
    return days


def _fetch(request_context, gbn: str, ym: str) -> tuple[str, str, dict]:
    response = request_context.post(
        "/onlineRsv/rsvRoomList",
        headers=REQUEST_HEADERS,
        form={"parameter": gbn, "year_month": ym},
        timeout=15000,
    )
    body = response.text()
    if body.strip().startswith("<script>location.href='/main';</script>"):
        raise RuntimeError("로그인 세션이 만료되었습니다.")
    try:
        return gbn, ym, json.loads(body)
    except json.JSONDecodeError as e:
        snippet = body.strip().replace("\n", " ")[:200]
        raise RuntimeError(f"예상치 못한 응답 ({response.status}): {snippet}") from e


def check_availability() -> dict[str, list[str]]:
    raw = os.environ.get("STORAGE_STATE", "")
    if not raw:
        raise RuntimeError("STORAGE_STATE 환경변수 없음")

    state = json.loads(raw)
    months = _current_months()
    resorts = list(RESORT_NAMES.keys())
    tasks = [(r, m) for r in resorts for m in months]

    data_map: dict[tuple[str, str], dict] = {}
    errors: list[str] = []
    with sync_playwright() as p:
        request_context = p.request.new_context(
            base_url=BASE_URL,
            storage_state=state,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        try:
            for gbn, ym in tasks:
                try:
                    key_gbn, key_ym, data = _fetch(request_context, gbn, ym)
                    data_map[(key_gbn, key_ym)] = data
                except Exception as e:
                    errors.append(f"{gbn}/{ym}: {e}")
        finally:
            request_context.dispose()

    if errors and not data_map:
        raise RuntimeError("빈자리 조회 실패: " + "; ".join(errors[:3]))

    resort_dates: dict[str, list[str]] = defaultdict(list)
    for gbn in resorts:
        for ym in months:
            data = data_map.get((gbn, ym), {})
            for day in _target_days(ym):
                for item in data.get("rsvPsblList", []):
                    if str(item.get("rming_dt", ""))[:10] == day:
                        for field in ROOM_FIELDS.values():
                            if int(item.get(field, 0) or 0) > 0:
                                name = RESORT_NAMES[gbn]
                                if day not in resort_dates[name]:
                                    resort_dates[name].append(day)
                                break

    if errors and not resort_dates:
        raise RuntimeError("조회는 됐지만 일부 요청이 실패했습니다: " + "; ".join(errors[:3]))

    return dict(resort_dates)


def _date_label(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.month}/{dt.day}({WEEKDAY_KR[dt.weekday()]})"


def _build_message(resort_dates: dict[str, list[str]]) -> str:
    if resort_dates:
        lines = ["빈자리 현황", ""]
        for name, dates in resort_dates.items():
            lines.append(f"- {name}: {', '.join(_date_label(d) for d in sorted(dates))}")
        lines.append("")
        lines.append("https://yeonsu.eseoul.go.kr/onlineRsv/list")
        return "\n".join(lines)
    return "빈자리 없음"


def _send(token: str, chat_id: str, text: str) -> None:
    req.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        message = body.get("message", {})
        text = (message.get("text") or "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

        result = b'{"ok":true}'

        if token and chat_id and text == "/check":
            try:
                resort_dates = check_availability()
                msg = _build_message(resort_dates)
            except Exception as e:
                msg = f"조회 오류: {e}"
            try:
                _send(token, chat_id, msg)
            except Exception:
                pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(result)

    def log_message(self, *args):
        pass
