# 🚀 빠른 시작 가이드

## 1단계: 사전 준비 확인

### AWS CLI 설정
```bash
# AWS CLI 설치 확인
aws --version

# AWS 계정 설정 (처음 한 번만)
aws configure
# Access Key ID: [AWS 콘솔에서 생성한 액세스 키]
# Secret Access Key: [AWS 콘솔에서 생성한 시크릿 키]
# Default region: ap-northeast-2
# Default output format: json

# AWS 계정 ID 확인
aws sts get-caller-identity
```

### Terraform 설치
```bash
# macOS
brew install terraform

# 설치 확인
terraform --version
```

### Python 3.12 설치
```bash
# macOS
brew install python@3.12

# 설치 확인
python3 --version
```

## 2단계: Slack Bot 생성

1. **Slack API 콘솔 접속**: https://api.slack.com/apps
2. **새 앱 생성**:
   - "Create New App" → "From scratch"
   - App Name: "Weather Bot"
   - Workspace 선택
3. **권한 설정**:
   - "OAuth & Permissions" 탭
   - "Bot Token Scopes"에 `users.profile:write` 추가
4. **앱 설치**:
   - "Install to Workspace" 클릭
   - Bot User OAuth Token 복사 (`xoxb-...`)

## 3단계: 배포 실행

```bash
# 1. 프로젝트 디렉토리로 이동
cd /Users/boby/Documents/my-slack-emoji

# 2. 자동 배포 실행
./deploy.sh
```

## 4단계: Slack 토큰 설정

```bash
# Slack Bot Token을 SSM에 저장
aws ssm put-parameter \
  --name /weatherbot/slack_token \
  --type SecureString \
  --value 'xoxb-your-slack-bot-token-here' \
  --overwrite
```

## 5단계: 테스트

```bash
# Lambda 함수 테스트
./test.sh

# 또는 개별 테스트
aws lambda invoke \
  --function-name weather-slack-bot-update-status \
  --payload '{"mode":"test"}' \
  response.json

cat response.json
```

## 6단계: 모니터링

```bash
# CloudWatch Logs 확인
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/weather-slack-bot

# 실시간 로그 스트리밍
aws logs tail /aws/lambda/weather-slack-bot-update-status --follow
```

## 🔧 문제 해결

### AWS 권한 오류
```bash
# 현재 사용자 권한 확인
aws sts get-caller-identity

# IAM 정책 확인 (관리자 권한 필요)
aws iam list-attached-user-policies --user-name [사용자명]
```

### Terraform 오류
```bash
# Terraform 상태 초기화
cd terraform
terraform init
terraform plan
```

### Lambda 패키징 오류
```bash
# Python 의존성 재설치
cd lambda
pip install -r requirements.txt -t . --upgrade
zip -r daily_planner.zip daily_planner.py requests*
zip -r update_status.zip update_status.py requests*
```

## 📊 성공 확인

1. **AWS 콘솔에서 확인**:
   - Lambda 함수 2개 생성됨
   - EventBridge Scheduler 스케줄 생성됨
   - SSM Parameter Store에 토큰 저장됨

2. **Slack에서 확인**:
   - 봇의 상태가 날씨에 따라 변경됨
   - 매일 03:05, 일출, 정오, 일몰 시간에 업데이트

3. **CloudWatch Logs에서 확인**:
   - Lambda 실행 로그
   - 에러 메시지 (있다면)

## 💰 예상 비용

- **Lambda**: 월 $0.20 이하
- **EventBridge Scheduler**: 월 $1.00 이하  
- **SSM Parameter Store**: 월 $0.05 이하
- **총 예상 비용**: 월 $1.25 이하
