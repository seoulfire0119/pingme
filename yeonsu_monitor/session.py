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

        # alert 팝업 자동 수락 + 텍스트 캡처
        alert_messages: list[str] = []
        page.on("dialog", lambda d: (alert_messages.append(d.message), d.accept()))

        print("로그인 모달 열기...")
        page.evaluate("login()")
        page.wait_for_selector("#mbmr_id", state="visible", timeout=10000)

        page.fill("#mbmr_id", config.username)
        page.fill("#mbmr_pwd", config.password)
        page.click("#loginBtn")

        # 네트워크 응답 대기
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # 모달이 사라졌는지 확인
        if page.is_visible("#mbmr_id"):
            # 사이트 오류 메시지 수집
            for sel in ["#errMsg", ".err_msg", ".login_err", ".alert", ".modal .error", ".pop .msg"]:
                try:
                    el = page.locator(sel)
                    if el.is_visible():
                        print(f"[디버그] 오류 메시지({sel}): {el.text_content()}", flush=True)
                except Exception:
                    pass
            # alert 다이얼로그 텍스트 캡처용 - 이미 닫혔을 수 있음
            if alert_messages:
                print(f"[디버그] Alert 팝업: {alert_messages}", flush=True)
            print(f"[디버그] 아이디 입력값 확인: {page.input_value('#mbmr_id')}", flush=True)
            print(f"[디버그] URL: {page.url}", flush=True)
            raise RuntimeError("로그인 실패. 아이디/비밀번호를 확인해주세요.")

        context.storage_state(path=str(state_path))
        browser.close()

    print(f"로그인 성공. 세션 저장 완료: {state_path}")
