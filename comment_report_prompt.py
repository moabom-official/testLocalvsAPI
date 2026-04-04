"""
Groq Llama 프롬프트 매니저 - 댓글 분석 보고서 생성용
자유로운 형식의 분석 보고서를 작성하도록 Llama를 가이드합니다.
"""

def get_comment_analysis_prompt(product_name: str, total_count: int, pos_count: int, 
                                neg_count: int, neutral_count: int, 
                                pos_samples: list, neg_samples: list) -> str:
    """
    댓글 분석 보고서 생성용 Llama 프롬프트
    자유로운 형식의 전문적인 분석 보고서를 요청합니다.
    """
    
    pos_text = "\n".join(f"- {comment}" for comment in pos_samples) if pos_samples else "없음"
    neg_text = "\n".join(f"- {comment}" for comment in neg_samples) if neg_samples else "없음"
    
    prompt = f"""
당신은 제품 평가 전문가입니다. 다음 유튜브 댓글 데이터를 분석하여 상세한 시장 보고서를 작성해주세요.

📊 데이터 요약
================
제품명: {product_name}
총 댓글 수: {total_count}개
- 긍정 댓글: {pos_count}개 ({pos_count/total_count*100:.1f}%)
- 중립 댓글: {neutral_count}개 ({neutral_count/total_count*100:.1f}%)
- 부정 댓글: {neg_count}개 ({neg_count/total_count*100:.1f}%)

📈 긍정 댓글 샘플 (상위 5개)
================
{pos_text}

📉 부정 댓글 샘플 (상위 5개)
================
{neg_text}

📝 요청사항
================
위 데이터를 바탕으로 다음과 같은 형식의 상세 분석 보고서를 작성해주세요:

1. **시장 반응 분석**
   - 긍정/부정 비율 해석
   - 시장에서의 전반적 평가

2. **주요 긍정 요소**
   - 사용자들이 가장 많이 칭찬하는 부분
   - 강점 분석

3. **주요 부정 요소**
   - 사용자들이 불만을 표하는 부분
   - 개선 필요 영역

4. **경쟁력 평가**
   - 현재 시장 위치
   - 경쟁 우위/약점

5. **최종 평가 및 추천**
   - 제품의 종합 평가 (★ 별점으로 표현)
   - 구매/추천 여부
   - 개선 방안 제언

**작성 가이드:**
- 전문적이고 객관적인 톤 유지
- 댓글 데이터를 근거로 구체적인 분석
- 한국어로 작성
- 약 500자~800자 분량의 상세 보고서

보고서를 작성해주세요.
"""
    
    return prompt


def get_sentiment_summary_prompt(product_name: str, comments_by_sentiment: dict) -> str:
    """
    감정 분석 요약용 간단한 프롬프트
    """
    
    pos_count = len(comments_by_sentiment.get("positive", []))
    neg_count = len(comments_by_sentiment.get("negative", []))
    neutral_count = len(comments_by_sentiment.get("neutral", []))
    
    pos_samples = "\n".join(f"- {c}" for c in comments_by_sentiment.get("positive", [])[:3])
    neg_samples = "\n".join(f"- {c}" for c in comments_by_sentiment.get("negative", [])[:3])
    
    prompt = f"""
{product_name}에 대한 유튜브 댓글 분석:

긍정 ({pos_count}개): {pos_samples if pos_samples else '없음'}
부정 ({neg_count}개): {neg_samples if neg_samples else '없음'}

한 문장으로 핵심 평가를 내려주세요.
"""
    
    return prompt
