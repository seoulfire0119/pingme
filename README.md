# Yeonsu Alert Monitor

서울시연수원 통합예약시스템의 잔여객실 변화를 감시해서 조건이 맞으면 알림을 보내는 작은 모니터링 도구입니다.

## What it does

- Playwright로 로그인 세션을 저장합니다.
- `/onlineRsv/rsvRoomList` 응답을 주기적으로 확인합니다.
- 원하는 연수원 / 날짜 / 객실 타입이 열리면 Telegram으로 알립니다.

## Why this shape

- 사이트가 로그인 기반이고, 화면 로직이 JS로 데이터를 불러오기 때문에 브라우저 세션을 그대로 쓰는 방식이 가장 안전합니다.
- 예약 버튼 자동 클릭은 넣지 않고, 알림까지만 자동화하는 쪽이 운영 리스크가 낮습니다.

## Next steps

1. `.env`를 채웁니다.
2. `python -m playwright install chromium`을 실행합니다.
3. `python -m yeonsu_monitor login`으로 1회 로그인 세션을 저장합니다.
4. 텔레그램에서 봇에 `/start`를 보낸 뒤 `python -m yeonsu_monitor chat-id`로 `chat_id`를 확인합니다.
5. `python -m yeonsu_monitor watch`로 감시를 시작합니다.
