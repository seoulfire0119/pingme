from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import date
import calendar
import json
import os

import requests as req

RESORT_NAMES = {
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
WEEKDAY_KR = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
BASE_URL = "https://yeonsu.eseoul.go.kr"
ROOM_FIELDS = {"A": "atye_room_num", "B": "btye_room_num", "C": "ctye_room_num", "O": "otye_room_num"}


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


def _fetch(session, gbn: str, ym: str) -> tuple[str, str, dict]:
    r = session.post(
        f"{BASE_URL}/onlineRsv/rsvRoomList",
        data={"parameter": gbn, "year_month": ym},
        timeout=15,
    )
    if r.text.strip().startswith("<script>location.href='/main';</script>"):
        raise RuntimeError("세션 만료")
    return gbn, ym, r.json()


def check_availability() -> dict[str, list[str]]:
    raw = os.environ.get("STORAGE_STATE", "")
    if not raw:
        raise RuntimeError("STORAGE_STATE 환경변수 없음")

    state = json.loads(raw)
    session = req.Session()
    for c in state.get("cookies", []):
        session.cookies.set(c["name"], c["value"])

    months = _current_months()
    resorts = list(RESORT_NAMES.keys())
    tasks = [(r, m) for r in resorts for m in months]

    data_map: dict[tuple[str, str], dict] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch, session, r, m): (r, m) for r, m in tasks}
        for f in futures:
            try:
                gbn, ym, data = f.result()
                data_map[(gbn, ym)] = data
            except Exception:
                pass

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

    return dict(resort_dates)


def _date_label(d: str) -> str:
    dt = date.fromisoformat(d)
    return f"{dt.month}/{dt.day}({WEEKDAY_KR[dt.weekday()]})"


def _build_message(resort_dates: dict[str, list[str]]) -> str:
    if resort_dates:
        lines = ["✅ 빈자리 현황\n"]
        for name, dates in resort_dates.items():
            lines.append(f"📍 {name}: {', '.join(_date_label(d) for d in sorted(dates))}")
        lines.append("\n👉 https://yeonsu.eseoul.go.kr/onlineRsv/list")
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

        if token and chat_id and text == "/ping":
            try:
                _send(token, chat_id, "pong ✅")
                result = b'{"ok":true,"debug":"sent"}'
            except Exception as e:
                result = json.dumps({"ok": False, "debug": str(e)}).encode()
        elif not token:
            result = b'{"ok":false,"debug":"no_token"}'
        elif not chat_id:
            result = b'{"ok":false,"debug":"no_chat_id"}'
        elif token and chat_id and text == "/check":
            try:
                resort_dates = check_availability()
                msg = _build_message(resort_dates)
            except Exception as e:
                msg = f"⚠️ 오류: {e}"
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
