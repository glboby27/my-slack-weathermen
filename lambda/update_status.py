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
    print(f"🌐 Open-Meteo API 호출 중... (위도: {CITY_LAT}, 경도: {CITY_LON})")
    data = _fetch_nowcast()
    hourly = data["hourly"]
    times = hourly["time"]
    idx = _pick_hour_index(times, now)
    print(f"📅 시간 인덱스: {idx} (총 {len(times)}개 시간대)")

    precip = hourly.get("precipitation", [0])[idx] or 0
    snow   = hourly.get("snowfall", [0])[idx] or 0
    cover  = hourly.get("cloudcover", [0])[idx] or 0
    wcode  = hourly.get("weathercode", [0])[idx] or 0
    
    print(f"🌧️ 강수량: {precip}mm")
    print(f"❄️ 적설량: {snow}mm") 
    print(f"☁️ 구름량: {cover}%")
    print(f"🌤️ 날씨코드: {wcode}")

    # 강수 우선
    if snow and snow > 0:
        print("❄️ 눈 감지 - 눈 이모지 선택")
        return ":snowflake:", "눈"
    if precip and precip > 0:
        print("🌧️ 비 감지 - 비 이모지 선택")
        return ":rain_cloud:", "비"

    # 흐림/구름
    if cover >= 80:
        print("☁️ 구름 80% 이상 - 흐림 이모지 선택")
        return ":cloud:", "흐림"
    if cover >= 40:
        if mode in ("sunset", "night"):
            print("⛅ 구름 40% 이상 + 야간모드 - 구름 많음 이모지 선택")
            return ":partly_sunny:", "구름 많음"
        print("⛅ 구름 40% 이상 + 주간모드 - 구름 조금 이모지 선택")
        return ":partly_sunny:", "구름 조금"
    
    # 맑음 or 야간
    if mode == "sunset" or (now.hour >= 18 or now.hour < 6):
        print("🌙 맑음 + 야간모드 - 달 이모지 선택")
        return ":crescent_moon:", "맑은 밤"
    print("☀️ 맑음 + 주간모드 - 태양 이모지 선택")
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
    # 상세 로깅 시작
    print("=" * 60)
    print(f"🚀 UpdateStatus Lambda 시작 - {dt.datetime.now(tz).isoformat()}")
    print(f"📥 입력 이벤트: {json.dumps(event, ensure_ascii=False)}")
    print(f"🆔 Request ID: {context.aws_request_id}")
    
    mode = (event.get("mode") or event.get("trigger") or "").lower()
    now = dt.datetime.now(tz)
    print(f"⏰ 현재 시간: {now.isoformat()} (KST)")
    print(f"🎯 원본 모드: {event.get('mode', 'None')} / {event.get('trigger', 'None')}")
    
    # sunset 모드 구분을 위해 야간 판단
    if not mode:
        if 6 <= now.hour < 12: mode = "sunrise"
        elif 12 <= now.hour < 18: mode = "noon"
        else: mode = "sunset"
    
    print(f"🔍 최종 모드: {mode} (시간 기반 자동 결정: {now.hour}시)")
    
    print("🌤️ 날씨 데이터 조회 시작...")
    emoji, text = _decide_emoji_text(now, mode)
    print(f"📊 날씨 분석 결과: {emoji} {text}")
    
    status_hash = _hash_status(emoji, text)
    print(f"🔐 상태 해시: {status_hash[:16]}...")
    
    print("💾 이전 상태 해시 조회...")
    last_hash = ""
    try:
        last_hash = _get_ssm(PARAM_LAST_HASH_PATH, with_decrypt=False) or ""
        print(f"📋 이전 해시: {last_hash[:16] if last_hash else 'None'}...")
    except Exception as e:
        print(f"⚠️ 이전 해시 조회 실패: {e}")
        pass

    if last_hash == status_hash:
        print("⏭️ 상태 변경 없음 - 스킵")
        result = {"ok": True, "skipped": True, "emoji": emoji, "text": text}
        print(f"📤 응답: {json.dumps(result, ensure_ascii=False)}")
        return result

    if DRY_RUN:
        print("🧪 DRY RUN 모드 - 실제 Slack 호출 생략")
        _put_ssm(PARAM_LAST_HASH_PATH, status_hash)
        result = {"ok": True, "dry_run": True, "emoji": emoji, "text": text}
        print(f"📤 응답: {json.dumps(result, ensure_ascii=False)}")
        return result

    print("🔑 Slack 토큰 조회...")
    token = _get_ssm(PARAM_SLACK_TOKEN_PATH, with_decrypt=True)
    print(f"🎫 토큰 길이: {len(token)} 문자")
    
    print("📡 Slack API 호출 시작...")
    code, body = _slack_set_status(token, emoji, text)
    print(f"📊 Slack 응답: {code} - {body[:100]}{'...' if len(body) > 100 else ''}")
    
    if code == 200:
        print("✅ Slack 상태 업데이트 성공")
        _put_ssm(PARAM_LAST_HASH_PATH, status_hash)
        print("💾 상태 해시 저장 완료")
        result = {"ok": True, "emoji": emoji, "text": text}
        print(f"📤 응답: {json.dumps(result, ensure_ascii=False)}")
        return result
    else:
        print(f"❌ Slack API 오류: {code}")
        result = {"ok": False, "code": code, "body": body}
        print(f"📤 응답: {json.dumps(result, ensure_ascii=False)}")
        return result
