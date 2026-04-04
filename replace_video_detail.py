import os
import shutil

templates_dir = r"C:\Users\seank\OneDrive\Desktop\Moabom_Prototype - (4)\templates"

print("=== 파일 교체 시작 ===")

# 1. 기존 파일 백업
old_file = os.path.join(templates_dir, "video_detail.html")
backup_file = os.path.join(templates_dir, "video_detail.html.old_backup")
if os.path.exists(old_file):
    shutil.copy(old_file, backup_file)
    print(f"✓ 기존 파일 백업됨: {backup_file}")

# 2. 기존 파일 삭제
if os.path.exists(old_file):
    os.remove(old_file)
    print(f"✓ 기존 파일 삭제됨")

# 3. FINAL 버전을 정식 이름으로 변경
final_file = os.path.join(templates_dir, "video_detail_FINAL.html")
new_file = os.path.join(templates_dir, "video_detail.html")
if os.path.exists(final_file):
    os.rename(final_file, new_file)
    print(f"✓ video_detail_FINAL.html → video_detail.html 변경됨")

# 4. 검증
if os.path.exists(new_file):
    with open(new_file, 'r', encoding='utf-8') as f:
        content = f.read()
        has_rewrite = 'rewrite' in content.lower()
        has_onclick_filter = 'onclick="filterBySentiment' in content
        
        print("\n=== 검증 결과 ===")
        print(f"  Rewrite 버튼 있음: {'❌ YES (문제!)' if has_rewrite else '✅ NO (정상)'}")
        print(f"  Sentiment 필터링 있음: {'✅ YES (정상)' if has_onclick_filter else '❌ NO (문제!)'}")
        
        if not has_rewrite and has_onclick_filter:
            print("\n🎉 완벽합니다! 최신 버전으로 교체되었습니다!")
        else:
            print("\n⚠️ 문제가 있습니다. 수동으로 확인해주세요.")
else:
    print("❌ 파일 생성 실패!")

print("\n✅ 작업 완료!")
