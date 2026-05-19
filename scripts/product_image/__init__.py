"""제품 이미지 검색·검증·저장 모듈 (Phase 3).

★ 이미지 검색 모듈이다 — 이미지 생성 아님. Serper(google.serper.dev)
   Google Images 로 실제 제품 사진을 가져와 비전 LLM 으로 검증·저장.
범위 격리: 보고서 파이프라인·영상/댓글 Agent 와 무관한 독립 모듈.
노드 친화: search/filter/vision/store 단계 함수 분리, 부수효과 격리.
"""
