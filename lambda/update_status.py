import json, os, hashlib, datetime as dt
from zoneinfo import ZoneInfo
import requests
import boto3

tz = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Seoul"))
PARAM_SLACK_TOKEN_PATH = os.environ["PARAM_SLACK_TOKEN_PATH"]
PARAM_LAST_HASH_PATH   = os.environ["PARAM_LAST_HASH_PATH"]
CITY_LAT = os.environ["CITY_LAT"]
CITY_LON = os.environ["CITY_LON"]
DRY_RUN  = os.environ.get("DRY_RUN", "false").lower() == "true"

ssm = boto3.client("ssm")

def _get_ssm(name, with_decrypt=False):
    return ssm.get_parameter(Name=name, WithDecryption=with_decrypt)["Parameter"]["Value"]

def _put_ssm(name, value):
    ssm.put_parameter(Name=name, Value=value, Type="String", Overwrite=True)

def _fetch_nowcast():
    # 시간대에 맞춰 필요한 변수만 최소 호출
    # precipitation, snowfall, cloudcover, weathercode
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={CITY_LAT}&longitude={CITY_LON}"
        "&hourly=precipitation,snowfall,cloudcover,weathercode"
        "&timezone=auto"
    )
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    return r.json()

def _pick_hour_index(times, target):
    # times: ["2025-09-13T10:00", ...], target: dt aware
    # 정확한 시간 매칭 없으면 가장 가까운 지난 시간
    target_str = target.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00")
    if target_str in times:
        return times.index(target_str)
    # fallback: 가장 가까운 인덱스
    best_i, best_diff = 0, None
    for i, t in enumerate(times):
        hh = dt.datetime.fromisoformat(t)
        diff = abs((hh - target.replace(tzinfo=None)).total_seconds())
        if best_diff is None or diff < best_diff:
            best_i, best_diff = i, diff
    return best_i

def _decide_emoji_text(now, mode):
    data = _fetch_nowcast()
    hourly = data["hourly"]
    times = hourly["time"]
    idx = _pick_hour_index(times, now)

    precip = hourly.get("precipitation", [0])[idx] or 0
    snow   = hourly.get("snowfall", [0])[idx] or 0
    cover  = hourly.get("cloudcover", [0])[idx] or 0
    wcode  = hourly.get("weathercode", [0])[idx] or 0

    # 강수 우선
    if snow and snow > 0:
        return ":snowflake:", "눈"
    if precip and precip > 0:
        # 간단 구분
        return ":rain_cloud:", "비"

    # 흐림/구름
    if cover >= 80:
        return ":cloud:", "흐림"
    if cover >= 40:
        if mode in ("sunset", "night"):
            return ":partly_sunny:", "구름 많음"
        return ":partly_sunny:", "구름 조금"
    # 맑음 or 야간 (달 위상 기능 비활성화)
    if mode == "sunset" or (now.hour >= 18 or now.hour < 6):
        return ":crescent_moon:", "맑은 밤"
    return ":sunny:", "맑음"

def _moon_emoji_text(now):
    # Farmsense API로 달 위상 정보 가져오기
    timestamp = int(now.timestamp())
    url = f"https://api.farmsense.net/v1/moonphases/?d={timestamp}"
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        js = r.json()
        if js and len(js) > 0:
            phase_data = js[0]
            phase = phase_data.get("Phase", 0)  # 0-1 사이의 값
            illumination = phase_data.get("Illumination", 0)  # 0-100 사이의 값
        else:
            raise Exception("No moon phase data")
    except Exception:
        # API 오류 시 기본값 반환
        return ":full_moon:", "보름달"
    # 0 new, 0.25 first quarter, 0.5 full, 0.75 last quarter
    # 맑은 밤일 때만 사용
    if phase < 0.03 or phase > 0.97:
        return ":new_moon:", "삭"
    if 0.03 <= phase < 0.22:
        return ":waxing_crescent_moon:", "왼쪽 초승달"
    if 0.22 <= phase < 0.28:
        return ":first_quarter_moon:", "왼쪽 반달"
    if 0.28 <= phase < 0.47:
        return ":waxing_gibbous_moon:", "왼쪽 그믐달"
    if 0.47 <= phase < 0.53:
        return ":full_moon:", "보름달"
    if 0.53 <= phase < 0.72:
        return ":waning_gibbous_moon:", "오른쪽 그믐달"
    if 0.72 <= phase < 0.78:
        return ":last_quarter_moon:", "오른쪽 반달"
    return ":waning_crescent_moon:", "오른쪽 초승달"

def _hash_status(emoji, text):
    h = hashlib.sha256(f"{emoji}|{text}".encode()).hexdigest()
    return h

def _slack_set_status(token, emoji, text):
    url = "https://slack.com/api/users.profile.set"
    payload = {"profile": {"status_text": text, "status_emoji": emoji, "status_expiration": 0}}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=8)
    return r.status_code, r.text

def handler(event, context):
    mode = (event.get("mode") or event.get("trigger") or "").lower()
    # sunset 모드 구분을 위해 야간 판단
    now = dt.datetime.now(tz)
    if not mode:
        if 6 <= now.hour < 12: mode = "sunrise"
        elif 12 <= now.hour < 18: mode = "noon"
        else: mode = "sunset"

    emoji, text = _decide_emoji_text(now, mode)
    status_hash = _hash_status(emoji, text)
    last_hash = ""
    try:
        last_hash = _get_ssm(PARAM_LAST_HASH_PATH, with_decrypt=False) or ""
    except Exception:
        pass

    if last_hash == status_hash:
        return {"ok": True, "skipped": True, "emoji": emoji, "text": text}

    if DRY_RUN:
        _put_ssm(PARAM_LAST_HASH_PATH, status_hash)
        return {"ok": True, "dry_run": True, "emoji": emoji, "text": text}

    token = _get_ssm(PARAM_SLACK_TOKEN_PATH, with_decrypt=True)
    code, body = _slack_set_status(token, emoji, text)
    if code == 200:
        _put_ssm(PARAM_LAST_HASH_PATH, status_hash)
        return {"ok": True, "emoji": emoji, "text": text}
    return {"ok": False, "code": code, "body": body}
