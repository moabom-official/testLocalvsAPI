import os
import shutil

templates_dir = r"C:\Users\seank\OneDrive\Desktop\Moabom_Prototype - (4)\templates"

print("=== 현재 파일 목록 ===")
for f in os.listdir(templates_dir):
    if 'video_detail' in f:
        print(f"  {f}")

print("\n=== 파일 변경 시작 ===")

# 1. 기존 video_detail.html 삭제
old_file = os.path.join(templates_dir, "video_detail.html")
if os.path.exists(old_file):
    os.remove(old_file)
    print("✓ video_detail.html 삭제됨")

# 2. CLEAN 버전을 정식 이름으로 변경
clean_file = os.path.join(templates_dir, "CLEAN_video_detail.html")
new_file = os.path.join(templates_dir, "video_detail.html")
if os.path.exists(clean_file):
    os.rename(clean_file, new_file)
    print("✓ CLEAN_video_detail.html → video_detail.html 변경됨")

# 3. backup 파일 삭제
backup_file = os.path.join(templates_dir, "video_detail.html.backup")
if os.path.exists(backup_file):
    os.remove(backup_file)
    print("✓ video_detail.html.backup 삭제됨")

print("\n=== 최종 파일 목록 ===")
for f in os.listdir(templates_dir):
    if 'video_detail' in f:
        size = os.path.getsize(os.path.join(templates_dir, f))
        print(f"  {f} ({size} bytes)")

print("\n✅ 파일 정리 완료!")
