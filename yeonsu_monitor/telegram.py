from __future__ import annotations

import requests


def send_telegram(bot_token: str, chat_id: str, message: str) -> None:
    if not bot_token or not chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=15,
    ).raise_for_status()


def get_chat_ids(bot_token: str) -> list[int]:
    if not bot_token:
        return []

    response = requests.get(
        f"https://api.telegram.org/bot{bot_token}/getUpdates",
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    chat_ids: list[int] = []
    for update in data.get("result", []):
        message = update.get("message") or update.get("channel_post")
        if not message:
            continue
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if isinstance(chat_id, int) and chat_id not in chat_ids:
            chat_ids.append(chat_id)
    return chat_ids
