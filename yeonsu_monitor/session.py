from __future__ import annotations

from .config import Config


def login_and_save_session(config: Config) -> None:
    if not config.username or not config.password:
        raise ValueError(".env에 YEONSU_USERNAME과 YEONSU_PASSWORD를 입력해주세요.")

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
        """)

        alert_messages: list[str] = []
        page.on("dialog", lambda d: (alert_messages.append(d.message), d.accept()))

        # 모든 POST 요청 캡처 (실제 로그인 엔드포인트 찾기용)
        post_requests: list[str] = []
        page.on("request", lambda r: post_requests.append(f"{r.method} {r.url}") if r.method == "POST" else None)

        print("사이트 접속 중...")
        page.goto(f"{config.base_url}/main", wait_until="networkidle", timeout=60000)

        print("로그인 모달 열기...")
        page.evaluate("login()")
        page.wait_for_selector("#mbmr_id", state="visible", timeout=10000)

        page.fill("#mbmr_id", config.username)
        page.fill("#mbmr_pwd", config.password)
        page.click("#loginBtn")

        print("로그인 처리 대기 중 (NetFunnel 대기열 포함)...")
        # NetFunnel 대기열 처리를 포함해 최대 40초 대기
        try:
            page.wait_for_selector("#mbmr_id", state="hidden", timeout=40000)
            # 성공
        except Exception:
            # 버튼 클릭이 실패한 경우 Enter 키 재시도
            if page.is_visible("#mbmr_id"):
                print("[디버그] Enter 키 재시도...", flush=True)
                page.press("#mbmr_pwd", "Enter")
                try:
                    page.wait_for_selector("#mbmr_id", state="hidden", timeout=40000)
                except Exception:
                    if alert_messages:
                        print(f"[디버그] Alert: {alert_messages}", flush=True)
                    print(f"[디버그] POST 요청들: {post_requests}", flush=True)
                    print(f"[디버그] URL: {page.url}", flush=True)
                    raise RuntimeError("로그인 실패. 아이디/비밀번호를 확인해주세요.")

        context.storage_state(path=str(state_path))
        browser.close()

    print(f"로그인 성공. 세션 저장 완료: {state_path}")
