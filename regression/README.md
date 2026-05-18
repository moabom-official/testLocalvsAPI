# 보고서 양식 회귀 안전망 (Phase 0)

## 목적
Phase 1~4(다중 LLM 검증 / RAG / 이미지 / LangGraph Agent화)가 보고서 생성 로직을
바꿔도 **4종 보고서의 출력 양식(구조)이 보존됐는지** 자동 검증한다. 보고서 생성
코드는 한 줄도 수정하지 않고 검증·테스트 자산만 추가했다. 모든 검증은
**오프라인**(DB·LLM·네트워크 없음)으로 동작한다.

## raw 응답 ≠ 최종 산출물 (중요)
보고서 ②③은 LLM 이 뱉은 JSON 을 그대로 저장하지 않는다. `comment_report.py` /
`integrated_report.py` 가 LLM 응답을 받은 뒤 **후처리**로 댓글 원문을 첨부하고
(`②: representative_comments`, `③: consumer_comments` / `question_comment`)
`_meta` 를 붙인다. **DB 에 저장되고 프론트·PDF 가 소비하는 "최종 dict" 가 검증
대상**이다. 따라서 골든 픽스처도 최종 산출물 형태(메타·첨부 키 포함)로 작성한다.
- 1차(raw 필수 스키마) 위반 → `severity="error"` (게이트 실패).
- 2차(후처리 첨부 형태) 위반 → `severity="warning"` (raw 형태일 수 있어 hard fail
  아님 — `is_ok=True` 유지).

## 실행법
```bash
# 회귀 게이트 (valid 픽스처가 하나라도 violated 면 종료 코드 1)
python -m regression.run_gate
python -m regression.run_gate --report 4      # 특정 보고서만

# 단위 테스트
pip install -r requirements-dev.txt
pytest regression/tests/
```

## 골든 샘플 추가법
실제 파이프라인이 만든 보고서 출력물을 파일로 저장한 뒤 적재한다(오프라인 — 파이프
라인을 돌리는 live 모드는 Phase 0 범위 밖):
```bash
python -m regression.snapshot_cli ingest --report 4 --file out.md --label v2
python -m regression.snapshot_cli validate --report 2 --file new.json   # 즉석 점검
python -m regression.snapshot_cli list
```
`ingest` 는 정규화 사본을 `golden/reportN/<label>.{md|json}` 으로 저장하고 옆에
`<label>.meta.json`(report_kind / label / captured_at / source_path / fingerprint /
contract_status)을 기록한다.

## Phase 1~4 작업자를 위한 절차
보고서 생성 코드를 바꾼 뒤:
1. 새 출력을 한 건 뽑아 `snapshot_cli validate` 로 즉시 양식을 점검한다.
2. `python -m regression.run_gate` 를 돌려 전체 게이트가 초록(종료 코드 0)인지
   확인하고, 그 출력 캡처를 PR 에 첨부한다.
3. 양식을 **의도적으로** 바꿔야 한다면 임의로 바꾸지 말고 먼저 보고한 뒤,
   골든 픽스처와 계약(`contracts/`)을 함께 갱신하고 PR 에 사유를 남긴다.

또한 Phase 1 의 검증 함수는 Phase 4 에서 LangGraph 노드로 흡수할 수 있도록
"노드 친화적"(상태 in/out, 부수효과 분리)으로 설계한다. 본 안전망의 검증기도
같은 원칙으로 순수 함수다(예외 없이 항상 `ContractResult` 반환).

## 상태(status) 분류
| status | 의미 | 게이트 |
|---|---|---|
| `ok` | 양식 위반 없음 | 통과 |
| `violated` | error 위반 ≥1 | **valid 라벨이면 실패** |
| `generation_failed` | 생성 실패 산출물(`[ERROR]`/`None`/자막없음) | 통과(정보) |
| `fallback` | 보고서 ④ 휴리스틱 폴백(LLM 미사용 모드) | 통과(정보) |

`valid` 라벨 픽스처가 `violated` 일 때만 게이트가 하드 실패한다.
`broken`/`raw`/`generation_failed`/`fallback` 은 정보로만 표기한다.

## 보고서별 계약 요약
| 보고서 | 형태 | 핵심 잠금 대상 |
|---|---|---|
| ① 자막 기반 | 마크다운 | `## 📦 제품 핵심 인사이트 보고서`, `**제품명:**`, 7개 H3(장점/단점·전작·맞음·비추·차별성·핵심포인트·한 줄 판정), 장점/단점 라벨, 강도 기호(◎○△✕), `- 차별점:`/`- 감안할 점:` 불릿, 전작 표 |
| ② 댓글 기반 | JSON | `validate_report2_json` + `REQUIRED_REPORT2_*` 재사용(1차 error). 2차 warning: `_meta`, `representative_comments`, `top_issues` 키 |
| ③ 통합 | JSON | `validate_report3_json` + `REQUIRED_REPORT3_*` 재사용(1차 error). 2차 warning: `_meta`, `consumer_comments`, `question_comment` |
| ④ 제품 종합 | 마크다운 7섹션 | 7개 동그라미 H2(①~⑦)+키워드, ① 점수 `X.X / 10`, ③ 표 5컬럼 `\| 차원 \| 점수 \| 커버리지 \| 리뷰어 합의 \| 핵심 코멘트 \|`, ④ `### 장점`/`### 단점`, ⑤ `### 소비자가 꼽은 강점`/`불만`/`### 대표 댓글`, ⑥ 표 5컬럼 `\| 항목 \| 전작 \| 현재 \| 변화 평가 \| 언급 영상 수 \|`, ⑦ `### 추천`/`### 비추`, `📊 분석 기반` |

산문 본문·항목 개수·구체 수치는 잠그지 않는다(LLM 정상 변동). 보고서 ④의 선택적
H3 `### 개별 리뷰어 의견` 은 존재·부재 모두 위반이 아니며, ⑤가 "데이터 부족
(분석 가능한 댓글 없음)" 한 줄이면 ⑤ 하위 H3 검사를 건너뛴다.

## 양식 스펙 보정 메모(작업 로그)
지시서 §4.5 는 보고서 ④ 폴백을 "7섹션 동그라미 H2 가 통째로 부재"로 식별하라고
했으나, 실제 `scripts/reports/product_integrated_insight.py:_heuristic_fallback_report`
는 7개 동그라미 H2 를 **모두** 출력한다. 원본 코드를 스펙보다 우선해, 폴백 판별을
H1 제목줄의 `(LLM 미사용 모드)` 마커(보조: `## 입력 영상별 보고서 (참고)`) +
7섹션 동그라미 H2 전부 부재 의 OR 조건으로 구현했다.

## 디렉터리
```
regression/
  contracts/   result.py + report{1..4}_contract.py (+ _markdown.py 헬퍼)
  fingerprint.py    구조 지문 + diff
  snapshot_cli.py   ingest / validate / list (오프라인)
  run_gate.py       회귀 게이트 단일 진입점
  golden/           reportN/{valid,broken[,raw,fallback]}.{md|json} + .meta.json
  tests/            pytest (DB·LLM·네트워크 없이 통과)
```
