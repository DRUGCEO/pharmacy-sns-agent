"""
약사 SNS 브랜딩 자동화 에이전트
매일 아침 건강 트렌드를 수집하고 글감을 텔레그램으로 전송합니다.
"""
import os
import requests
from datetime import date

import anthropic
from pytrends.request import TrendReq


# ─────────────────────────────────────────
# 1단계: 구글 트렌드 수집
# ─────────────────────────────────────────

HEALTH_SEED_KEYWORDS = [
    "영양제", "비타민", "약 부작용", "다이어트 약", "건강기능식품",
    "처방전", "약 복용법", "유산균", "마그네슘", "오메가3",
]

def get_health_trends() -> list[str]:
    """구글 트렌드에서 건강·약 관련 인기 검색어를 수집합니다."""
    pytrends = TrendReq(hl="ko", tz=540)
    collected = []

    # 씨앗 키워드별 연관 검색어 수집
    for keyword in HEALTH_SEED_KEYWORDS:
        try:
            pytrends.build_payload([keyword], timeframe="now 1-d", geo="KR")
            related = pytrends.related_queries()
            top_df = related.get(keyword, {}).get("top")
            if top_df is not None and not top_df.empty:
                collected.extend(top_df.head(3)["query"].tolist())
        except Exception:
            continue

    # 한국 실시간 급상승 검색어 중 건강 관련 항목 추가
    health_markers = ["약", "비타민", "영양", "건강", "다이어트", "처방", "복용", "부작용", "효능"]
    try:
        trending = pytrends.trending_searches(pn="south_korea")
        for term in trending[0].tolist():
            if any(m in term for m in health_markers):
                collected.append(term)
    except Exception:
        pass

    unique = list(dict.fromkeys(collected))  # 순서 유지 중복 제거
    return unique[:12]


# ─────────────────────────────────────────
# 2단계: Claude로 글감 큐레이션
# ─────────────────────────────────────────

def curate_with_claude(trends: list[str]) -> str:
    """Claude API를 이용해 약사 관점의 글감 카드 3개를 생성합니다."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today_str = date.today().strftime("%Y년 %m월 %d일")

    if trends:
        trends_block = "\n".join(f"- {t}" for t in trends)
    else:
        # 트렌드 수집 실패 시 기본 소재로 대체
        trends_block = "- 마그네슘 과다복용\n- GLP-1 다이어트 약\n- 비타민D 결핍"

    prompt = f"""당신은 30대 여성 약사의 SNS 콘텐츠 기획 전문가입니다.

오늘({today_str}) 구글 트렌드에서 수집한 건강 관련 인기 검색어입니다:
{trends_block}

이 약사는 스레드(Threads) SNS에서 개인 브랜드를 구축하고 있으며 아래 원칙을 지킵니다:
- 약사로서의 전문성과 신뢰도를 반드시 유지한다
- 식약처, 대한약사회, PubMed 등 검증된 근거를 인용한다
- 일반인이 읽기 쉽고 실생활에 도움이 되어야 한다
- 공포 마케팅이 아닌 따뜻하고 정확한 정보를 전달한다

위 트렌드를 바탕으로 오늘의 추천 글감 3개를 아래 형식으로 작성해주세요.
각 글감은 실제 근거가 있는 내용만 포함해야 합니다.

📌 글감 #1
제목 아이디어: "[클릭하고 싶은 제목]"
핵심 내용:
• [핵심 포인트 1 — 구체적인 수치나 기준 포함]
• [핵심 포인트 2]
• [핵심 포인트 3]
신뢰 근거: [식약처 / 대한약사회 / 논문 출처]
추천 해시태그: #약사추천 #[관련태그] #[관련태그]
예상 반응: [높음/보통] — [이유 한 줄]

📌 글감 #2
(위와 동일한 형식)

📌 글감 #3
(위와 동일한 형식)"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ─────────────────────────────────────────
# 3단계: 텔레그램 봇 전송
# ─────────────────────────────────────────

def send_telegram(text: str) -> None:
    """텔레그램 봇 API로 메시지를 전송합니다 (4096자 초과 시 분할 전송)."""
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
            timeout=30,
        )
        resp.raise_for_status()


# ─────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────

def main() -> None:
    print("▶ 트렌드 수집 중...")
    trends = get_health_trends()
    print(f"  수집 완료: {trends[:5]}{'...' if len(trends) > 5 else ''}")

    print("▶ Claude로 글감 큐레이션 중...")
    curated = curate_with_claude(trends)

    today_label = date.today().strftime("%m월 %d일")
    header = f"🌅 *오늘의 스레드 글감 리포트* ({today_label})\n\n"
    footer = "\n\n✅ 오늘도 좋은 글 쓰세요\\! 약사 언니 파이팅\\! 💊"
    full_message = header + curated + footer

    print("▶ 텔레그램으로 전송 중...")
    send_telegram(full_message)
    print("✅ 완료!")


if __name__ == "__main__":
    main()
