#!/bin/bash

# Weather Slack Bot 배포 스크립트
set -e

echo "🌤️  Weather Slack Bot 배포 시작..."

# 1. Lambda 패키징
echo "📦 Lambda 함수 패키징 중..."
cd lambda

# 의존성 설치 및 패키징
pip3.12 install -r requirements.txt -t . --quiet

# ZIP 파일 생성
zip -r daily_planner.zip daily_planner.py requests* -q
zip -r update_status.zip update_status.py requests* -q

echo "✅ Lambda 패키징 완료"

# 2. Terraform 배포
echo "🏗️  Terraform 배포 중..."
cd ../terraform

# AWS 계정 ID 확인
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$ACCOUNT_ID" ]; then
    echo "❌ AWS 계정 ID를 가져올 수 없습니다. AWS CLI 설정을 확인하세요."
    exit 1
fi

echo "AWS 계정 ID: $ACCOUNT_ID"

# Terraform 초기화 및 배포
terraform init
terraform apply -var="account_id=$ACCOUNT_ID" -auto-approve

echo "✅ Terraform 배포 완료"

# 3. Slack 토큰 설정 안내
echo ""
echo "🔑 다음 단계:"
echo "1. Slack Bot Token을 SSM Parameter Store에 설정하세요:"
echo "   aws ssm put-parameter --name /weatherbot/slack_token --type SecureString --value 'xoxb-...' --overwrite"
echo ""
echo "2. 테스트를 위해 Lambda 함수를 직접 호출해보세요:"
echo "   aws lambda invoke --function-name weather-slack-bot-update-status --payload '{\"mode\":\"test\"}' response.json"
echo ""
echo "3. CloudWatch Logs에서 로그를 확인하세요:"
echo "   aws logs describe-log-groups --log-group-name-prefix /aws/lambda/weather-slack-bot"
echo ""
echo "🎉 배포 완료!"
