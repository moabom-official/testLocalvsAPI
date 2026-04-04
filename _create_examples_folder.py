"""
examples 폴더 생성 스크립트
"""
from pathlib import Path

examples_dir = Path("comment_filtering_agent/examples")
examples_dir.mkdir(parents=True, exist_ok=True)

print(f"✓ {examples_dir} 폴더 생성 완료")

# __init__.py 생성
init_file = examples_dir / "__init__.py"
init_file.write_text("# examples 폴더를 위한 __init__.py\n", encoding="utf-8")

print(f"✓ {init_file} 생성 완료")
