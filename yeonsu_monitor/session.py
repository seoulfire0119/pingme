from __future__ import annotations

from playwright.sync_api import sync_playwright

from .config import Config


def login_and_save_session(config: Config) -> None:
    if not config.username or not config.password:
        raise ValueError(".env에 YEONSU_USERNAME과 YEONSU_PASSWORD를 입력해주세요.")

    state_path = config.storage_dir / "storage_state.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("사이트 접속 중...")
        page.goto(f"{config.base_url}/main", wait_until="load", timeout=60000)

        print("로그인 모달 열기...")
        page.evaluate("login()")
        page.wait_for_selector("#mbmr_id", state="visible", timeout=10000)

        page.fill("#mbmr_id", config.username)
        page.fill("#mbmr_pwd", config.password)
        page.click("#loginBtn")

        # 모달이 닫히거나 페이지가 이동할 때까지 대기
        page.wait_for_timeout(3000)

        # 로그인 실패 시 모달이 여전히 보임
        modal_still_visible = page.is_visible("#mbmr_id")
        if modal_still_visible:
            raise RuntimeError("로그인 실패. 아이디/비밀번호를 확인해주세요.")

        context.storage_state(path=str(state_path))
        browser.close()

    print(f"로그인 성공. 세션 저장 완료: {state_path}")
