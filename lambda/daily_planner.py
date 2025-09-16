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
WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

def _notify_slack(text: str):
    if not WEBHOOK_URL:
        return
    try:
        requests.post(WEBHOOK_URL, json={"text": text}, timeout=5)
    except Exception:
        pass

def _fetch_astronomy():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={CITY_LAT}&longitude={CITY_LON}"
        "&daily=sunrise,sunset"
        "&timezone=UTC"
    )
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    js = r.json()
    
    # 오늘 날짜 찾기
    today = dt.date.today().isoformat()
    time_list = js["daily"]["time"]
    
    try:
        today_index = time_list.index(today)
        return js["daily"]["sunrise"][today_index], js["daily"]["sunset"][today_index]
    except ValueError:
        # 오늘 날짜가 없으면 첫 번째 사용
        return js["daily"]["sunrise"][0], js["daily"]["sunset"][0]

def _to_kst_datetime(iso_str):
    # Open-Meteo 반환은 타임존 포함 ISO
    return dt.datetime.fromisoformat(iso_str).astimezone(tz)

def _iso_minute_zero(x):
    # KST 시간을 UTC로 변환하여 반환
    utc_time = x.astimezone(dt.timezone.utc)
    return utc_time.replace(second=0, microsecond=0).isoformat()

def _create_one_time(name, when_iso, mode):
    if DRY_RUN:
        return {"dry": True, "name": name, "at": when_iso, "mode": mode}
    
    # 기존 스케줄이 있으면 삭제
    try:
        scheduler.delete_schedule(Name=name)
        print(f"Deleted existing schedule: {name}")
    except scheduler.exceptions.ResourceNotFoundException:
        pass  # 스케줄이 없으면 무시
    
    # EventBridge Scheduler의 at() 표현식 사용
    # ISO 형식을 UTC로 변환하여 at() 표현식에 사용 (타임존 오프셋 제거)
    dt_obj = dt.datetime.fromisoformat(when_iso.replace('Z', '+00:00'))
    at_expr = f"at({dt_obj.strftime('%Y-%m-%dT%H:%M:%S')})"
    
    # 과거 시각인 경우 스케줄 생성하지 않음
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 오늘 날짜의 스케줄이지만 과거 시간인 경우 생성하지 않음
    if dt_obj.date() == today_utc.date() and dt_obj < now_utc:
        print(f"Past time today detected, skipping schedule creation: {at_expr}")
        return {"skipped": True, "name": name, "reason": "past_time_today"}
    elif dt_obj.date() < today_utc.date():
        # 다른 날짜의 스케줄이면 생성하지 않음 (어차피 내일 새벽에 다시 만들 예정)
        print(f"Past date detected, skipping schedule creation: {at_expr}")
        return {"skipped": True, "name": name, "reason": "past_date"}
    else:
        print(f"Future time detected, keeping: {at_expr}")
    
    return scheduler.create_schedule(
        Name=name,
        ScheduleExpression=at_expr,
        ScheduleExpressionTimezone="UTC",
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
    
    # 디버깅 로그 추가
    print(f"API sunrise raw: {sr_iso}")
    print(f"API sunset raw: {ss_iso}")
    print(f"Parsed sunrise: {dt.datetime.fromisoformat(sr_iso)}")
    print(f"Parsed sunset: {dt.datetime.fromisoformat(ss_iso)}")
    
    sunrise = _to_kst_datetime(sr_iso)
    sunset  = _to_kst_datetime(ss_iso)
    
    print(f"Final sunrise KST: {sunrise}")
    print(f"Final sunset KST: {sunset}")

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
    res_sr = _create_one_time(f"update-sunrise-{date_tag}", _iso_minute_zero(sunrise), "sunrise")
    res_nn = _create_one_time(f"update-noon-{date_tag}",    _iso_minute_zero(noon),    "noon")
    res_ss = _create_one_time(f"update-sunset-{date_tag}",  _iso_minute_zero(sunset),  "sunset")
    created.extend([res_sr, res_nn, res_ss])

    # Slack 알림 (요약)
    try:
        sunrise_txt = sunrise.strftime("%Y-%m-%d %H:%M KST")
        noon_txt    = noon.strftime("%Y-%m-%d %H:%M KST")
        sunset_txt  = sunset.strftime("%Y-%m-%d %H:%M KST")
        msg_parts = [
            f"🌅 sunrise: {sunrise_txt} - {'skipped' if isinstance(res_sr, dict) and res_sr.get('skipped') else 'scheduled'}",
            f"🕛 noon: {noon_txt} - {'skipped' if isinstance(res_nn, dict) and res_nn.get('skipped') else 'scheduled'}",
            f"🌇 sunset: {sunset_txt} - {'skipped' if isinstance(res_ss, dict) and res_ss.get('skipped') else 'scheduled'}",
        ]
        _notify_slack("[DailyPlanner] 원타임 스케줄 생성\n" + "\n".join(msg_parts))
    except Exception:
        pass

    return {"ok": True, "sunrise": sunrise.isoformat(), "noon": noon.isoformat(), "sunset": sunset.isoformat(), "schedules": len(created)}
