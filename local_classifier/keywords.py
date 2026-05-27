"""LocalRobertaClassifier 가 VR → ANALYZE 승격 판단을 위해 사용하는 제품 속성 키워드.

운영 agent 의 _handle_video_reaction 는 mentioned_product_features 가
2개 이상이면 분석 대상으로 승격한다. API 분류기 (GPT-4.1) 는 프롬프트로
이 필드를 직접 채워주지만, Local 분류기는 분류만 하므로 후처리 매칭이 필요.

scripts/api/sync.py 의 PRODUCT_ASPECT_KEYWORDS 와 **동기**된 리스트.
변경 시 양쪽 모두 업데이트할 것.
"""
from __future__ import annotations

# 소비자 전자제품 리뷰에서 공통적으로 등장하는 속성(attribute) 키워드.
# 감정어(좋다/나쁘다/추천 등)는 의도적으로 제외 — 영상 반응 댓글과 구분 불가.
PRODUCT_ASPECT_KEYWORDS: list[str] = [
    # 성능/처리
    "성능", "속도", "처리", "발열", "온도", "쿨링",
    # 배터리
    "배터리", "충전", "배터리수명", "전력",
    # 디스플레이
    "화면", "디스플레이", "해상도", "밝기",
    # 디자인/외형
    "디자인", "무게", "크기", "마감", "색상", "두께",
    # 카메라
    "카메라", "화질", "사진",
    # 가격/가성비
    "가격", "가성비", "성가비",
    # 소프트웨어/UI
    "소프트웨어", "앱", "업데이트", "버그",
    # 내구성/서비스
    "내구성", "AS", "서비스", "품질",
    # 음향
    "소리", "음질", "스피커",
]


def extract_mentioned_features(text: str, extra_keywords: list[str] | None = None) -> list[str]:
    """댓글 텍스트에 등장하는 제품 속성 키워드 추출.

    Args:
        text: 댓글 원문
        extra_keywords: 추가 매칭할 키워드 (예: product_name 토큰). default None.

    Returns:
        매칭된 키워드 리스트 (중복 제거, 입력 순서 유지).
    """
    if not text:
        return []
    haystack = text.lower()
    all_kw = PRODUCT_ASPECT_KEYWORDS + (extra_keywords or [])
    matched: list[str] = []
    seen: set[str] = set()
    for kw in all_kw:
        if not kw:
            continue
        kw_lower = kw.lower()
        if kw_lower in seen:
            continue
        if kw_lower in haystack:
            matched.append(kw)
            seen.add(kw_lower)
    return matched
