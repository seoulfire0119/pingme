from __future__ import annotations

from .config import Config


def login_and_save_session(config: Config) -> None:
    if not config.username or not config.password:
        raise ValueError(".env에 YEONSU_USERNAME과 YEONSU_PASSWORD를 입력해주세요.")

    state_path = config.storage_dir / "storage_state.json"

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        print("사이트 접속 중...")
        page.goto(f"{config.base_url}/main", wait_until="networkidle", timeout=60000)

        print("로그인 모달 열기...")
        page.evaluate("login()")
        page.wait_for_selector("#mbmr_id", state="visible", timeout=10000)

        page.fill("#mbmr_id", config.username)
        page.fill("#mbmr_pwd", config.password)
        page.click("#loginBtn")

        # 모달이 사라질 때까지 최대 10초 대기
        try:
            page.wait_for_selector("#mbmr_id", state="hidden", timeout=10000)
        except Exception:
            print(f"[디버그] 현재 URL: {page.url}", flush=True)
            print(f"[디버그] 페이지 제목: {page.title()}", flush=True)
            raise RuntimeError("로그인 실패. 아이디/비밀번호를 확인해주세요.")

        context.storage_state(path=str(state_path))
        browser.close()

    print(f"로그인 성공. 세션 저장 완료: {state_path}")
