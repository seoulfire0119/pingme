from __future__ import annotations

import time

import requests

from .config import Config
from .monitor import _poll_once_local, _send_resort_summary
from .telegram import send_telegram


def _get_updates(token: str, offset: int) -> list[dict]:
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": offset, "timeout": 30},
            timeout=35,
        )
        return r.json().get("result", [])
    except Exception:
        return []


def run_bot(config: Config) -> None:
    """텔레그램 long-polling 봇 — /check 명령 수신 시 현황 조회 후 전송."""
    print("봇 시작. 텔레그램에서 /check 를 보내면 현황을 조회합니다.", flush=True)
    send_telegram(config.telegram_bot_token, config.telegram_chat_id, "✅ 봇 시작됨. /check 로 현황 조회")

    offset = 0
    while True:
        updates = _get_updates(config.telegram_bot_token, offset)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            text = (message.get("text") or "").strip()
            chat_id = str(message.get("chat", {}).get("id", ""))

            if text == "/check":
                send_telegram(config.telegram_bot_token, chat_id, "🔍 조회 중...")
                try:
                    resort_dates = _poll_once_local(config)
                    _send_resort_summary(config, resort_dates, test_mode=False)
                except Exception as e:
                    send_telegram(config.telegram_bot_token, chat_id, f"⚠️ 오류: {e}")

        time.sleep(1)
