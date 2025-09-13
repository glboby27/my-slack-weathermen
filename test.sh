#!/bin/bash

# Weather Slack Bot 테스트 스크립트
set -e

echo "🧪 Weather Slack Bot 테스트 시작..."

# 1. UpdateStatus Lambda 테스트
echo "📊 UpdateStatus Lambda 테스트 중..."
aws lambda invoke \
  --function-name weather-slack-bot-update-status \
  --payload '{"mode":"test"}' \
  response.json

echo "UpdateStatus 응답:"
cat response.json
echo ""

# 2. DailyPlanner Lambda 테스트
echo "📅 DailyPlanner Lambda 테스트 중..."
aws lambda invoke \
  --function-name weather-slack-bot-daily-planner \
  --payload '{"trigger":"test"}' \
  response.json

echo "DailyPlanner 응답:"
cat response.json
echo ""

# 3. 생성된 스케줄 확인
echo "⏰ 생성된 스케줄 확인 중..."
aws scheduler list-schedules --name-prefix update- | jq '.Schedules[] | {Name: .Name, ScheduleExpression: .ScheduleExpression, State: .State}'

# 4. CloudWatch Logs 확인
echo "📋 최근 로그 확인 중..."
echo "UpdateStatus 로그:"
aws logs describe-log-streams \
  --log-group-name /aws/lambda/weather-slack-bot-update-status \
  --order-by LastEventTime \
  --descending \
  --max-items 1 \
  --query 'logStreams[0].logStreamName' \
  --output text | xargs -I {} aws logs get-log-events \
  --log-group-name /aws/lambda/weather-slack-bot-update-status \
  --log-stream-name {} \
  --limit 10

echo ""
echo "DailyPlanner 로그:"
aws logs describe-log-streams \
  --log-group-name /aws/lambda/weather-slack-bot-daily-planner \
  --order-by LastEventTime \
  --descending \
  --max-items 1 \
  --query 'logStreams[0].logStreamName' \
  --output text | xargs -I {} aws logs get-log-events \
  --log-group-name /aws/lambda/weather-slack-bot-daily-planner \
  --log-stream-name {} \
  --limit 10

echo ""
echo "✅ 테스트 완료!"
