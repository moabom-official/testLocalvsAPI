# 영상별 자막 기반 보고서 시각화 (transcript-report-visual-rich)

영상별 자막 기반 보고서(`video_reports.transcript_report`)를 텍스트 위주의
보고서에서, 단일 리뷰어 평가를 30초 안에 흡수할 수 있는 시각적 인사이트
페이지로 재구성한다. 종합 인사이트(PIR) 보고서와는 다른 시각 정체성을 가진다.

## 기술 접근

종합 인사이트 시각화와 동일한 방식.

- **서버 측**: 변경 없음. LLM 프롬프트, 모델, DB 스키마, `transcript_report.py`
  모두 그대로. 마크다운은 기존 `markdown_to_html()` 으로 HTML 변환되어
  `{{ transcript_report|safe }}` 로 주입됨.
- **프론트엔드 후처리**: `templates/video_detail.html` 에 `_tr*` 함수군 추가.
  `DOMContentLoaded` 시 `#transcriptReportBox` 의 렌더된 HTML 을 스캔하여
  의미 데이터를 추출하고, DOM 에 시각 컴포넌트를 삽입한다.
- **fallback**: 각 시각화는 `try/catch` 로 격리. 실패 시 원본 마크다운이
  그대로 표시된다. 원본은 시각화가 성공적으로 삽입된 후에만 숨겨진다.

## 추가된 파싱 유틸리티 (JS)

| 함수 | 역할 |
|---|---|
| `_trFindHeading(bodyEl, keyword)` | 텍스트에 키워드를 포함한 첫 헤딩 반환 |
| `_trSectionSiblings(headingEl)` | 다음 같은/상위 헤딩 또는 `<hr>` 직전까지의 형제 수집 |
| `_trClassifyLi(text)` | 리더 기호(◎/○/△/✕)로 항목의 강도 분류 |
| `_trCountSymbols(text)` | 전체 텍스트에서 ◎○△✕ 개수 카운트 |
| `_trClassifyByCategory(text)` | 8 카테고리 키워드 매칭 |
| `_trMoodFromSymbols(sym)` | 강도 점수 → 무드 위치/라벨 |
| `_trCollectAllLis(bodyEl)` | `<ul><li>` 외에 `nl2br` 로 인해 `<p>+<br>` 로 평탄화된 항목까지 수집 |
| `_trCollectListUnder(headingEl)` | 추천/비추 등 임의 리스트(섹션 형태 무관) 수집 |

`_trCollectAllLis` 가 핵심 — Python `markdown` 라이브러리는 `nl2br` 확장으로
`**장점**\n- ◎ ...` 처럼 빈 줄 없이 이어지는 리스트를 `<ul>` 이 아닌
`<p><strong>장점</strong><br>- ◎ ...</p>` 로 출력한다. 이를 모두 잡아내기
위해 `<br>` 분리 후 텍스트 라인을 재분류한다.

## 시각화 컴포넌트 (7)

| # | 이름 | 데이터 출처 | 위치 |
|---|---|---|---|
| 1 | 평가 무드 메터 | `_trCountSymbols` 합산 (◎×3 / ○×2 / △×2 / ✕×3), 한 줄 구매 판정 인용구 | 보고서 최상단 히어로 |
| 2 | 장단점 균형 다이어그램 | `_trCollectAllLis` 강도 합산, 카테고리 아이콘 | 장점/단점 헤딩 직하단 |
| 3 | 카테고리 히트맵 (8 셀) | `_trClassifyByCategory` 매칭 + 강도 우선순위 | 균형 다이어그램 직하단, hover 툴팁 |
| 4 | 변화 임팩트 카드 (top 3) | 전작 대비 표 행 파싱, 수치 변화율 계산, ↑/↓ 방향성 | 전작 대비 헤딩 직하단 |
| 5 | 적합도 매처 (chip 인터랙션) | 추천/비추 섹션 리스트 추출 → fit/misfit chip | 추천/비추 섹션 통합 대체 |
| 6 | 핵심 포인트 타임라인 | `<ol>` 항목별 키워드 분석 (positive/negative/neutral) | 핵심 포인트 섹션 대체 |
| 7 | 리뷰 신뢰도 인디케이터 | 수치 단위 패턴 카운트, 비교/추천/단점 유무 | 히어로 우측 작은 카드 |

## 검증

`scripts/reports/transcript_report.py` 의 `_FINAL_PROMPT` 두 예시로 JSDOM
회귀 테스트를 수행했다. 결과:

- **예시 1 (수치 풍부)**: 무드 63% (긍정), 균형 12점 vs 7점, 히트맵 6개 카테고리
  분류, 카드 3개 (디스플레이 +49%, 가격 +6%, 무게 -1%), 매처 fit×2 + misfit×2,
  타임라인 4 항목 (sellingpoint→pos, 발열→neg), 신뢰도 100%.
- **예시 2 (수치 부족)**: 무드 100% (매우 긍정), 균형 9점 vs 0점,
  카드 3개(수치 없이 '향상'/'감소'/'개선'), 매처 fit×2만, 타임라인 2항목,
  신뢰도 50% (수치 정보·단점 충실도 부족 정상 감지).

## 변경 파일

- `templates/video_detail.html`
  - `<style>` 블록에 `.tr-*` 시각화 클래스 추가 (CSS, ~280 lines)
  - 자막 보고서 `<div class="report-box">` 에 `id="transcriptReportBox"`,
    `data-report-type="transcript"` 부여
  - `<script>` 블록에 시각화 JS 추가 (~430 lines)

## 모바일 반응형

- ≤720px: 히어로 1열, 히트맵 4열, 변화 카드 1열
- ≤480px: 히트맵 2열
- 매처 chip 자동 줄바꿈, 타임라인 그대로

## 절대 변경하지 않은 것

- `scripts/reports/transcript_report.py` (LLM 프롬프트, 모델)
- `video_reports.transcript_report` 컬럼 / DB 스키마
- 종합 인사이트(`product_detail.html`), 댓글 반응 보고서, 통합 보고서
- 영상 클립 임베드 등 비디오 재생 기능
