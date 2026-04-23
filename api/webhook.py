from http.server import BaseHTTPRequestHandler
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
LOGIN_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE_URL}/loginLayer",
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


def _seed_session_from_state(session: req.Session, raw_state: str) -> None:
    state = json.loads(raw_state)
    for cookie in state.get("cookies", []):
        session.cookies.set(cookie["name"], cookie["value"])


def _login_session(session: req.Session) -> None:
    username = os.environ.get("YEONSU_USERNAME", "")
    password = os.environ.get("YEONSU_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("YEONSU_USERNAME 또는 YEONSU_PASSWORD가 없습니다.")

    session.get(f"{BASE_URL}/loginLayer", timeout=20)
    response = session.post(
        f"{BASE_URL}/loginProcAjax",
        data={"mbmr_id": username, "mbmr_pwd": password},
        headers=LOGIN_HEADERS,
        timeout=20,
    )
    payload = response.json()
    if payload.get("result") not in {"success", "pwdNextChange"}:
        raise RuntimeError(f"로그인 실패: {payload.get('result', 'unknown')}")


def _ensure_authenticated_session() -> req.Session:
    session = req.Session()
    raw_state = os.environ.get("STORAGE_STATE", "")
    if raw_state:
        try:
            _seed_session_from_state(session, raw_state)
        except Exception:
            session.cookies.clear()

    try:
        _fetch(session, "00003002", _current_months()[0])
    except RuntimeError as e:
        if "로그인 세션이 만료되었습니다." not in str(e):
            raise
        session = req.Session()
        _login_session(session)

    return session


def _fetch(session: req.Session, gbn: str, ym: str) -> tuple[str, str, dict]:
    response = session.post(
        f"{BASE_URL}/onlineRsv/rsvRoomList",
        headers=REQUEST_HEADERS,
        data={"parameter": gbn, "year_month": ym},
        timeout=15,
    )
    body = response.text
    if body.strip().startswith("<script>location.href='/main';</script>"):
        raise RuntimeError("로그인 세션이 만료되었습니다.")
    try:
        return gbn, ym, json.loads(body)
    except json.JSONDecodeError as e:
        snippet = body.strip().replace("\n", " ")[:200]
        raise RuntimeError(f"예상치 못한 응답 ({response.status_code}): {snippet}") from e


def check_availability() -> dict[str, list[str]]:
    months = _current_months()
    resorts = list(RESORT_NAMES.keys())
    tasks = [(r, m) for r in resorts for m in months]

    data_map: dict[tuple[str, str], dict] = {}
    errors: list[str] = []
    session = _ensure_authenticated_session()
    for gbn, ym in tasks:
        try:
            key_gbn, key_ym, data = _fetch(session, gbn, ym)
            data_map[(key_gbn, key_ym)] = data
        except Exception as e:
            errors.append(f"{gbn}/{ym}: {e}")

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
