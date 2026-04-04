# 댓글 분류 User Prompt 템플릿

다음 YouTube 댓글을 분석하여 분류하세요.

**댓글**: {comment}

**제품 정보** (참고용):
- 제품명: {product_name}
- 카테고리: {product_category}

---

위 댓글을 다음 5개 라벨 중 하나로 분류하세요:

1. **PRODUCT_OPINION**: 제품의 성능, 발열, 배터리, 가격, 디자인 등 제품 특성에 대한 평가
2. **VIDEO_REACTION**: 영상 자체, 리뷰어, 편집, 연출에 대한 반응
3. **CHATTER**: 잡담, 밈, 의미 없는 댓글
4. **QUESTION**: 제품에 대한 질문
5. **OFF_TOPIC**: 제품과 완전히 무관한 댓글

반드시 JSON 형식으로만 응답하세요. 다른 텍스트 포함 금지.
