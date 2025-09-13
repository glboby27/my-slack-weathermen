# Weather Slack Bot 🌤️

매일 자동으로 서울 날씨를 조회하여 Slack 상태를 업데이트하는 봇입니다.

## 아키텍처 다이어그램

```mermaid
flowchart TB
  subgraph AWS
    A[EventBridge Rule<br/>매일 03:05 KST] --> B[Lambda DailyPlanner]
    B --> C[Open-Meteo API<br/>서울 예보·일출·일몰·달 위상]
    B --> D[EventBridge Scheduler<br/>원타임 스케줄 3건 생성]
    D --> E[Lambda UpdateStatus 일출]
    D --> F[Lambda UpdateStatus 정오]
    D --> G[Lambda UpdateStatus 일몰]
    B --> H[Lambda UpdateStatus 새벽 선반영]

    subgraph Config & Secrets
      I[SSM Parameter Store<br/>SecureString SLACK_BOT_TOKEN]
      J[SSM Parameter Store<br/>String LAST_STATUS_HASH]
    end

    E --> K[Slack API users.profile.set]
    F --> K
    G --> K
    H --> K

    I -. 토큰 조회 .-> E
    I -. 토큰 조회 .-> F
    I -. 토큰 조회 .-> G
    I -. 토큰 조회 .-> H

    J <--> E
    J <--> F
    J <--> G
    J <--> H
  end
```

## 비즈니스 로직 플로우

```mermaid
flowchart LR
  S[DailyPlanner<br/>매일 03:05 KST] --> Q{서울 데이터 조회 성공?}
  Q -->|예| U[일출·일몰·정오 계산]
  Q -->|아니오| R[재시도 후 전일 스케줄 유지]

  U --> V[EventBridge Scheduler<br/>원타임 3건 생성]
  U --> W[UpdateStatus 실행<br/>새벽 선반영]

  subgraph UpdateStatus 공통
    X[현재 시점 예보 재조회] --> Y{상태 결정 규칙}
    Y --> Y1[오전 영역<br/>강수 우선, 아니면 맑음/구름/흐림]
    Y --> Y2[오후 영역<br/>강수 우선, 아니면 맑음/구름/흐림]
    Y --> Y3[야간 영역<br/>강수·흐림 우선, 맑은 밤이면 달 위상]
    Y1 --> Z[이모지·텍스트 산출]
    Y2 --> Z
    Y3 --> Z
    Z --> C1{직전 상태와 동일?}
    C1 -->|예| C2[Slack 호출 생략]
    C1 -->|아니오| C3[Slack users.profile.set 호출]
    C3 --> C4[LAST_STATUS_HASH 갱신]
  end
```

## 아키텍처

- **DailyPlanner Lambda**: 매일 03:05 KST에 실행되어 일출/정오/일몰 시간을 조회하고 원타임 스케줄을 생성
- **UpdateStatus Lambda**: 실제 Slack 상태를 업데이트하는 함수
- **EventBridge Scheduler**: 원타임 스케줄 3건/일 생성 (일출, 정오, 일몰)
- **SSM Parameter Store**: Slack 토큰과 마지막 상태 해시 저장

## 기능

- 🌅 **일출 시**: 오전 날씨 상태 업데이트
- ☀️ **정오 시**: 오후 날씨 상태 업데이트  
- 🌇 **일몰 시**: 야간 날씨 상태 업데이트 (맑으면 달 위상 표시)
- 🌙 **새벽 선반영**: 03:05에 즉시 상태 업데이트

## 날씨 우선순위

1. **강수 우선**: 눈 > 비
2. **흐림/구름**: 구름량 80% 이상 → 흐림, 40% 이상 → 구름 조금/많음
3. **맑음**: 야간 맑으면 달 위상 표시

## 배포

### 1. 사전 준비

```bash
# AWS CLI 설정
aws configure

# Terraform 설치 (1.6.0 이상)
# Python 3.12 설치
```

### 2. 자동 배포

```bash
./deploy.sh
```

### 3. 수동 배포

```bash
# Lambda 패키징
cd lambda
pip install -r requirements.txt -t .
zip -r daily_planner.zip daily_planner.py requests*
zip -r update_status.zip update_status.py requests*

# Terraform 배포
cd ../terraform
terraform init
terraform apply -var="account_id=$(aws sts get-caller-identity --query Account --output text)"
```

### 4. Slack 토큰 설정

```bash
aws ssm put-parameter \
  --name /weatherbot/slack_token \
  --type SecureString \
  --value 'xoxb-your-slack-bot-token' \
  --overwrite
```

## 테스트

### Lambda 함수 직접 호출

```bash
# UpdateStatus 테스트
aws lambda invoke \
  --function-name weather-slack-bot-update-status \
  --payload '{"mode":"test"}' \
  response.json

# DailyPlanner 테스트  
aws lambda invoke \
  --function-name weather-slack-bot-daily-planner \
  --payload '{"trigger":"test"}' \
  response.json
```

### 로그 확인

```bash
# CloudWatch Logs 확인
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/weather-slack-bot

# 실시간 로그 스트리밍
aws logs tail /aws/lambda/weather-slack-bot-update-status --follow
```

## 설정 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `region` | ap-northeast-2 | AWS 리전 |
| `city_lat` | 37.5665 | 서울 위도 |
| `city_lon` | 126.9780 | 서울 경도 |
| `timezone` | Asia/Seoul | 타임존 |
| `dry_run` | false | 실제 Slack 호출 여부 |

## 이모지 매핑

| 날씨 | 이모지 | 텍스트 |
|------|--------|--------|
| 눈 | :snowflake: | 눈 |
| 비 | :rain_cloud: | 비 |
| 흐림 | :cloud: | 흐림 |
| 구름 | :partly_sunny: | 구름 조금/많음 |
| 맑음 | :sunny: | 맑음 |
| 달 위상 | :new_moon: 등 | 맑은 밤 [달 위상] |

## 문제 해결

### 1. Lambda 함수가 실행되지 않는 경우
- CloudWatch Logs에서 에러 메시지 확인
- IAM 권한 설정 확인
- SSM Parameter Store 접근 권한 확인

### 2. Slack API 호출 실패
- Bot Token 유효성 확인
- Bot 권한 설정 확인 (users.profile:write)
- 네트워크 연결 상태 확인

### 3. 스케줄이 생성되지 않는 경우
- EventBridge Scheduler 권한 확인
- DailyPlanner Lambda 로그 확인
- 시간대 설정 확인

## 비용

- **Lambda**: 월 100만 요청 기준 약 $0.20
- **EventBridge Scheduler**: 월 100만 스케줄 기준 약 $1.00
- **SSM Parameter Store**: 월 10,000 요청 기준 약 $0.05

**총 예상 비용**: 월 $1.25 이하

## 정리

```bash
# Terraform으로 리소스 삭제
cd terraform
terraform destroy -var="account_id=$(aws sts get-caller-identity --query Account --output text)"
```
