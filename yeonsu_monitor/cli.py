from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .monitor import run_check, run_summary
from .session import login_and_save_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yeonsu-monitor")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Save a fresh login session")
    sub.add_parser("check", help="Run the 5-minute vacancy check once")
    sub.add_parser("summary", help="Send the daily 11 AM summary once")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(Path(".env"))

    if args.command == "login":
        login_and_save_session(config)
        return

    if args.command == "check":
        run_check(config)
        return

    if args.command == "summary":
        run_summary(config)
        return
