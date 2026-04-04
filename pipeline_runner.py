"""
댓글 분석 파이프라인 실행 스크립트

Usage:
    python pipeline_runner.py --video-id VIDEO_ID [--max-comments 100]

Environment Variables:
    YOUTUBE_API_KEY: YouTube Data API 키
    GROQ_API_KEY: Groq API 키
"""
import argparse
import os
import sys
import json
import logging
from pathlib import Path

# 프로젝트 루트를 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from comment_filtering_agent.services.pipeline_orchestrator import (
    CommentAnalysisPipeline,
    PipelineConfig
)

logger = logging.getLogger(__name__)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='YouTube 댓글 분석 파이프라인')
    parser.add_argument(
        '--video-id',
        type=str,
        required=True,
        help='YouTube 비디오 ID'
    )
    parser.add_argument(
        '--max-comments',
        type=int,
        default=100,
        help='최대 수집 댓글 수 (기본: 100)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='배치 크기 (기본: 50)'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='로그 레벨 (기본: INFO)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='결과 저장 경로 (JSON 파일)'
    )
    
    args = parser.parse_args()
    
    # 설정 생성
    config = PipelineConfig(
        youtube_api_key=os.getenv('YOUTUBE_API_KEY'),
        groq_api_key=os.getenv('GROQ_API_KEY'),
        max_comments=args.max_comments,
        batch_size=args.batch_size,
        log_level=args.log_level
    )
    
    # 파이프라인 실행
    try:
        pipeline = CommentAnalysisPipeline(config)
        result = pipeline.run(args.video_id)
        
        # 결과 저장
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            
            logger.info(f"Results saved to: {output_path}")
        
        # 종료 코드
        if result.errors:
            sys.exit(1)  # 에러 있음
        else:
            sys.exit(0)  # 성공
            
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
