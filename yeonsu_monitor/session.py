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
        # 자동화 감지 우회
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US']});
        """)

        # alert 팝업 자동 수락 + 텍스트 캡처
        alert_messages: list[str] = []
        page.on("dialog", lambda d: (alert_messages.append(d.message), d.accept()))

        # 로그인 관련 네트워크 요청 캡처
        login_requests: list[str] = []
        login_responses: list[str] = []
        page.on("request", lambda r: login_requests.append(f"{r.method} {r.url}") if "login" in r.url.lower() else None)
        page.on("response", lambda r: login_responses.append(f"{r.status} {r.url}") if "login" in r.url.lower() else None)

        print("사이트 접속 중...")
        page.goto(f"{config.base_url}/main", wait_until="networkidle", timeout=60000)

        print("로그인 모달 열기...")
        page.evaluate("login()")
        page.wait_for_selector("#mbmr_id", state="visible", timeout=10000)

        page.fill("#mbmr_id", config.username)
        page.fill("#mbmr_pwd", config.password)
        page.click("#loginBtn")

        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        # 버튼 클릭 후에도 모달이 살아있으면 Enter 키 재시도
        if page.is_visible("#mbmr_id"):
            print("[디버그] 버튼 클릭 후 모달 유지 → Enter 키 시도", flush=True)
            page.press("#mbmr_pwd", "Enter")
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

        if page.is_visible("#mbmr_id"):
            if alert_messages:
                print(f"[디버그] Alert 팝업: {alert_messages}", flush=True)
            print(f"[디버그] 로그인 요청 목록: {login_requests}", flush=True)
            print(f"[디버그] 로그인 응답 목록: {login_responses}", flush=True)
            print(f"[디버그] URL: {page.url}", flush=True)
            raise RuntimeError("로그인 실패. 아이디/비밀번호를 확인해주세요.")

        context.storage_state(path=str(state_path))
        browser.close()

    print(f"로그인 성공. 세션 저장 완료: {state_path}")
