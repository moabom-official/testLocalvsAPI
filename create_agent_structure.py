import os

# 폴더 구조 정의
folders = [
    "comment_filtering_agent",
    "comment_filtering_agent/core",
    "comment_filtering_agent/filters",
    "comment_filtering_agent/classifiers",
    "comment_filtering_agent/utils",
    "comment_filtering_agent/prompts",
    "comment_filtering_agent/tests",
    "comment_filtering_agent/data",
]

# 폴더 생성
for folder in folders:
    os.makedirs(folder, exist_ok=True)
    print(f"✅ Created: {folder}")

# __init__.py 파일 생성
init_files = [
    "comment_filtering_agent/__init__.py",
    "comment_filtering_agent/core/__init__.py",
    "comment_filtering_agent/filters/__init__.py",
    "comment_filtering_agent/classifiers/__init__.py",
    "comment_filtering_agent/utils/__init__.py",
    "comment_filtering_agent/tests/__init__.py",
]

for init_file in init_files:
    with open(init_file, "w", encoding="utf-8") as f:
        f.write('"""Comment Filtering Agent Module"""\n')
    print(f"📝 Created: {init_file}")

print("\n🎉 댓글 필터링 Agent 폴더 구조 생성 완료!")
