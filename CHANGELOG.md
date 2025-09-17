## Changelog

### v1.0.4 — 2025-09-17
- sunset/night에서 구름량 40–79%일 때 `:partly_sunny:` 사용 제거, `:cloud:`(구름 많음)으로 통일
- 이모지 선택 로직 명확화 및 야간 표현 일관성 개선

### v1.0.3 — 2025-09-17
- Slack 알림 전송 디버깅 로깅 추가 (요청/응답 코드, 본문 일부 로깅)
- 스케줄 생성 요약 Slack 메시지 전송 시 이모지 제거 및 전체 메시지 로그 출력
- Slack Webhook 알림 안정화

### v1.0.2 — 2025-09-17
- DailyPlanner의 날짜 계산을 KST 기준으로 수정 (UTC 기준으로 어제로 인식되던 문제 해결)
- 오늘 기준 sunrise/noon/sunset 계산 및 스케줄 생성 안정화

### v1.0.1 — 2025-09-16
- DailyPlanner가 Open-Meteo `daily` 데이터에서 오늘 인덱스를 사용하도록 수정 (기존 [0] 사용 제거)
- 원타임 스케줄을 `at()` 표현식 + `UTC`로 생성하도록 통일
- 과거 시간 스케줄은 생성하지 않고 스킵하도록 로직 정제 (today past/past date)
- 스케줄 생성 전 동일 이름 스케줄 삭제로 `ConflictException` 방지
- Slack Webhook 알림 추가: 스케줄 생성 요약/결과 통지
- 상세 디버그 로깅 추가

### v1.0.0 — 2025-09-16
- 초기 안정 버전 태깅
- Lambda 및 EventBridge Scheduler 기반 일출/정오/일몰 상태 업데이트 워크플로우 동작
- 기본 로깅 및 SSM 파라미터 기반 구성


