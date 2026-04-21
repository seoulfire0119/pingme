from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .monitor import run_check, run_monitor
from .session import login_and_save_session
from .telegram import get_chat_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yeonsu-monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="로그인 세션 저장")
    watch_parser = sub.add_parser("watch", help="실시간 감시 시작 (빈자리 즉시 알림 + 매일 오전 11시 요약)")
    watch_parser.add_argument("--test", action="store_true", help="매 사이클마다 전체 현황 텔레그램 전송 (테스트용)")
    sub.add_parser("check", help="지금 즉시 현황 조회 후 텔레그램 전송")
    sub.add_parser("chat-id", help="텔레그램 chat ID 확인")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(Path(".env"))

    if args.command == "login":
        login_and_save_session(config)
        return

    if args.command == "watch":
        run_monitor(config, test_mode=args.test)
        return

    if args.command == "check":
        run_check(config)
        return

    if args.command == "chat-id":
        chat_ids = get_chat_ids(config.telegram_bot_token)
        if not chat_ids:
            print("No chat IDs found. Send /start to the bot first, then try again.")
            return
        for chat_id in chat_ids:
            print(chat_id)
        return
