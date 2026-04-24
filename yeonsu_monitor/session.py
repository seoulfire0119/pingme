from __future__ import annotations

from http.cookiejar import Cookie

import requests

from .config import Config


def _cookie_to_playwright(cookie: Cookie, base_url: str) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain.lstrip(".") if cookie.domain else "",
        "path": cookie.path or "/",
        "httpOnly": bool(cookie._rest.get("HttpOnly")),
        "secure": bool(cookie.secure),
        "sameSite": "Lax",
    }
    if cookie.expires is not None:
        entry["expires"] = cookie.expires
    else:
        entry["expires"] = -1
    if not entry["domain"]:
        entry["url"] = base_url
        entry.pop("domain")
    return entry


def login_and_save_session(config: Config) -> None:
    if not config.username or not config.password:
        raise ValueError("YEONSU_USERNAME and YEONSU_PASSWORD must be set in .env.")

    state_path = config.storage_dir / "storage_state.json"
    base_url = config.base_url.rstrip("/")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{base_url}/loginLayer",
        }
    )

    print("Opening login page...", flush=True)
    response = session.get(f"{base_url}/loginLayer", timeout=30)
    response.raise_for_status()

    print("Submitting login...", flush=True)
    login_response = session.post(
        f"{base_url}/loginProcAjax",
        data={"mbmr_id": config.username, "mbmr_pwd": config.password},
        timeout=30,
    )
    login_response.raise_for_status()

    try:
        payload = login_response.json()
    except ValueError as exc:
        snippet = login_response.text.strip().replace("\n", " ")[:200]
        raise RuntimeError(f"Unexpected login response: {snippet}") from exc

    result = payload.get("result")
    if result not in {"success", "pwdNextChange"}:
        raise RuntimeError(f"Login failed: {result}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        cookies = [_cookie_to_playwright(cookie, base_url) for cookie in session.cookies]
        if cookies:
            context.add_cookies(cookies)

        context.storage_state(path=str(state_path))
        browser.close()

    print(f"Login succeeded. Session saved to: {state_path}")
