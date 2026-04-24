from __future__ import annotations

from .config import Config


def login_and_save_session(config: Config) -> None:
    if not config.username or not config.password:
        raise ValueError("YEONSU_USERNAME and YEONSU_PASSWORD must be set in .env.")

    state_path = config.storage_dir / "storage_state.json"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US']});
            Object.defineProperty(navigator, 'userAgentData', {
                get: () => ({
                    brands: [
                        { brand: 'Not A(Brand', version: '99' },
                        { brand: 'Google Chrome', version: '124' },
                        { brand: 'Chromium', version: '124' }
                    ],
                    mobile: false,
                    platform: 'Windows',
                    getHighEntropyValues: () => Promise.resolve({})
                })
            });
        """)

        alert_messages: list[str] = []
        page.on("dialog", lambda d: (alert_messages.append(d.message), d.accept()))

        post_requests: list[str] = []
        page.on("request", lambda r: post_requests.append(f"POST {r.url}") if r.method == "POST" else None)

        print("Opening login page...", flush=True)
        page.goto(f"{config.base_url}/loginLayer", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("#mbmr_id", state="visible", timeout=15000)

        print("Filling credentials...", flush=True)
        page.fill("#mbmr_id", config.username)
        page.fill("#mbmr_pwd", config.password)

        print("Submitting login...", flush=True)
        payload: dict[str, object] | None = None
        try:
            with page.expect_response(
                lambda r: r.url.endswith("/loginProcAjax") and r.request.method == "POST",
                timeout=30000,
            ) as response_info:
                page.click("#loginBtn")
            payload = response_info.value.json()
        except Exception:
            payload = None

        if isinstance(payload, dict):
            result = payload.get("result")
            if result not in {None, "success", "pwdNextChange"}:
                raise RuntimeError(f"Login failed: {result}")

        try:
            page.wait_for_url("**/main", timeout=40000)
        except Exception:
            if alert_messages:
                print(f"[login alert] {alert_messages}", flush=True)
            print(f"[login request log] {[r for r in post_requests if 'google' not in r]}", flush=True)
            print(f"[login url] {page.url}", flush=True)
            if isinstance(payload, dict):
                raise RuntimeError(f"Login failed: {payload.get('result', 'unknown')}")
            raise RuntimeError("Login failed. Check your username and password.")

        context.storage_state(path=str(state_path))
        browser.close()

    print(f"Login succeeded. Session saved to: {state_path}")
