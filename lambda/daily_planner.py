import os, json, datetime as dt
from zoneinfo import ZoneInfo
import requests, boto3

tz = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Seoul"))

CITY_LAT = os.environ["CITY_LAT"]
CITY_LON = os.environ["CITY_LON"]
SCHEDULER_TARGET_ROLE_ARN  = os.environ["SCHEDULER_TARGET_ROLE_ARN"]
UPDATE_STATUS_FUNCTION_ARN = os.environ["UPDATE_STATUS_FUNCTION_ARN"]
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

scheduler = boto3.client("scheduler")
lambda_client = boto3.client("lambda")

def _fetch_astronomy():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={CITY_LAT}&longitude={CITY_LON}"
        "&daily=sunrise,sunset"
        "&timezone=auto"
    )
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    js = r.json()
    return js["daily"]["sunrise"][0], js["daily"]["sunset"][0]

def _to_kst_datetime(iso_str):
    # Open-Meteo 반환은 타임존 포함 ISO
    return dt.datetime.fromisoformat(iso_str).astimezone(tz)

def _iso_minute_zero(x):
    return x.replace(second=0, microsecond=0).isoformat()

def _create_one_time(name, when_iso, mode):
    if DRY_RUN:
        return {"dry": True, "name": name, "at": when_iso, "mode": mode}
    # EventBridge Scheduler는 at() 형식을 지원하지 않으므로 cron 형식으로 변환
    dt_obj = dt.datetime.fromisoformat(when_iso.replace('Z', '+00:00'))
    dt_obj = dt_obj.astimezone(tz)
    
    cron_expr = f"cron({dt_obj.minute} {dt_obj.hour} {dt_obj.day} {dt_obj.month} ? {dt_obj.year})"
    
    return scheduler.create_schedule(
        Name=name,
        ScheduleExpression=cron_expr,
        ScheduleExpressionTimezone=str(tz),
        FlexibleTimeWindow={"Mode": "OFF"},
        Target={
            "Arn": UPDATE_STATUS_FUNCTION_ARN,
            "RoleArn": SCHEDULER_TARGET_ROLE_ARN,
            "Input": json.dumps({"mode": mode}),
            "RetryPolicy": {"MaximumEventAgeInSeconds": 60, "MaximumRetryAttempts": 1}
        },
        Description=f"One-time {mode} update"
    )

def handler(event, context):
    # 오늘의 일출·일몰
    sr_iso, ss_iso = _fetch_astronomy()
    sunrise = _to_kst_datetime(sr_iso)
    sunset  = _to_kst_datetime(ss_iso)

    # 오늘 정오
    today = dt.datetime.now(tz).date()
    noon   = dt.datetime.combine(today, dt.time(hour=12, minute=0, tzinfo=tz))

    # 1) 새벽 선반영 즉시 실행
    if not DRY_RUN:
        lambda_client.invoke(
            FunctionName=UPDATE_STATUS_FUNCTION_ARN,
            InvocationType="Event",
            Payload=json.dumps({"mode": "dawn"}).encode()
        )

    # 2) 일출, 정오, 일몰 스케줄 생성
    date_tag = today.strftime("%Y%m%d")
    created = []
    created.append(_create_one_time(f"update-sunrise-{date_tag}", _iso_minute_zero(sunrise), "sunrise"))
    created.append(_create_one_time(f"update-noon-{date_tag}",    _iso_minute_zero(noon),    "noon"))
    created.append(_create_one_time(f"update-sunset-{date_tag}",  _iso_minute_zero(sunset),  "sunset"))

    return {"ok": True, "sunrise": sunrise.isoformat(), "noon": noon.isoformat(), "sunset": sunset.isoformat(), "schedules": len(created)}
