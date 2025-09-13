terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# Lambda용 공통 정책
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# EventBridge Scheduler가 Lambda를 호출하는 역할
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# Lambda 실행 역할
resource "aws_iam_role" "lambda_role" {
  name               = "${var.name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Lambda 실행 정책
data "aws_iam_policy_document" "lambda_policy" {
  statement {
    sid     = "Logs"
    effect  = "Allow"
    actions = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${var.account_id}:*"]
  }

  statement {
    sid     = "SSMReadWriteHash"
    effect  = "Allow"
    actions = ["ssm:GetParameter", "ssm:PutParameter"]
    resources = [
      "arn:aws:ssm:${var.region}:${var.account_id}:parameter${var.param_slack_token_path}",
      "arn:aws:ssm:${var.region}:${var.account_id}:parameter${var.param_last_hash_path}"
    ]
  }

  statement {
    sid     = "SchedulerCRUD"
    effect  = "Allow"
    actions = [
      "scheduler:CreateSchedule",
      "scheduler:DeleteSchedule",
      "scheduler:ListSchedules",
      "scheduler:TagResource"
    ]
    resources = ["*"]
  }

  statement {
    sid     = "InvokeUpdateStatusDirect"
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.update_status.arn]
  }

  statement {
    sid     = "PassRole"
    effect  = "Allow"
    actions = ["iam:PassRole"]
    resources = [aws_iam_role.scheduler_target_role.arn]
  }
}

resource "aws_iam_role_policy" "lambda_inline" {
  role   = aws_iam_role.lambda_role.id
  name   = "${var.name}-lambda-policy"
  policy = data.aws_iam_policy_document.lambda_policy.json
}

# 스케줄러가 람다를 대신 호출할 때 사용할 역할
resource "aws_iam_role" "scheduler_target_role" {
  name               = "${var.name}-scheduler-target-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler_target_policy" {
  statement {
    effect = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.update_status.arn,
      aws_lambda_function.daily_planner.arn
    ]
  }
}

resource "aws_iam_role_policy" "scheduler_target_inline" {
  role   = aws_iam_role.scheduler_target_role.id
  name   = "${var.name}-scheduler-target-policy"
  policy = data.aws_iam_policy_document.scheduler_target_policy.json
}

# CloudWatch Logs
resource "aws_cloudwatch_log_group" "daily_planner" {
  name              = "/aws/lambda/${var.name}-daily-planner"
  retention_in_days = 14
}
resource "aws_cloudwatch_log_group" "update_status" {
  name              = "/aws/lambda/${var.name}-update-status"
  retention_in_days = 14
}

# Lambda 패키지 경로
locals {
  daily_planner_zip = "${path.module}/../lambda/daily_planner.zip"
  update_status_zip = "${path.module}/../lambda/update_status.zip"
}

# UpdateStatus Lambda
resource "aws_lambda_function" "update_status" {
  function_name = "${var.name}-update-status"
  role          = aws_iam_role.lambda_role.arn
  handler       = "update_status.handler"
  runtime       = "python3.12"
  filename      = local.update_status_zip
  timeout       = 15
  memory_size   = 256
  environment {
    variables = {
      PARAM_SLACK_TOKEN_PATH   = var.param_slack_token_path
      PARAM_LAST_HASH_PATH     = var.param_last_hash_path
      CITY_LAT                 = var.city_lat
      CITY_LON                 = var.city_lon
      TIMEZONE                 = var.timezone
      DRY_RUN                  = var.dry_run
    }
  }
  depends_on = [aws_cloudwatch_log_group.update_status]
}

# DailyPlanner Lambda
resource "aws_lambda_function" "daily_planner" {
  function_name = "${var.name}-daily-planner"
  role          = aws_iam_role.lambda_role.arn
  handler       = "daily_planner.handler"
  runtime       = "python3.12"
  filename      = local.daily_planner_zip
  timeout       = 20
  memory_size   = 256
  environment {
    variables = {
      PARAM_SLACK_TOKEN_PATH     = var.param_slack_token_path
      PARAM_LAST_HASH_PATH       = var.param_last_hash_path
      CITY_LAT                   = var.city_lat
      CITY_LON                   = var.city_lon
      TIMEZONE                   = var.timezone
      SCHEDULER_TARGET_ROLE_ARN  = aws_iam_role.scheduler_target_role.arn
      UPDATE_STATUS_FUNCTION_ARN = aws_lambda_function.update_status.arn
      DRY_RUN                    = var.dry_run
    }
  }
  depends_on = [aws_cloudwatch_log_group.daily_planner]
}

# 매일 03:05 KST에 DailyPlanner 호출
resource "aws_scheduler_schedule" "daily_0305_kst" {
  name       = "${var.name}-daily-0305-kst"
  flexible_time_window { mode = "OFF" }

  schedule_expression_timezone = var.timezone
  schedule_expression          = "cron(5 3 * * ? *)"  # 03:05 매일

  target {
    arn      = aws_lambda_function.daily_planner.arn
    role_arn = aws_iam_role.scheduler_target_role.arn
    retry_policy {
      maximum_event_age_in_seconds = 60
      maximum_retry_attempts       = 1
    }
    input = jsonencode({ trigger = "daily" })
  }
}

# Slack 토큰과 상태 해시용 SSM 파라미터(토큰은 수동으로 SecureString 업데이트 권장)
resource "aws_ssm_parameter" "slack_token" {
  name  = var.param_slack_token_path
  type  = "SecureString"
  value = "PUT_YOUR_SLACK_BOT_TOKEN_HERE"
  lifecycle { ignore_changes = [value] }
}

resource "aws_ssm_parameter" "last_hash" {
  name  = var.param_last_hash_path
  type  = "String"
  value = "initial"
}
