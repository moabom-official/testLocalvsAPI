# 팀 코드 병합 매뉴얼

> 기준 레포: `https://github.com/MeDeoDuck/Moabom_Prototype`  
> 작성일: 2026-04-24

---

## 전체 흐름 요약

```
[내 로컬]                [GitHub 공용 레포]             [팀원 로컬]
   main  ──push──▶  origin/main  ◀──push──  팀원 branch
                          │
                     PR & Merge
```

---

## Step 1. 팀원을 GitHub 레포에 초대

1. GitHub 접속 → `MeDeoDuck/Moabom_Prototype`
2. **Settings → Collaborators → Add people**
3. 팀원 GitHub 계정명 입력 후 초대
4. 팀원이 이메일로 수락

---

## Step 2. 팀원 로컬 환경 세팅

팀원이 처음 clone하는 경우:

```bash
git clone https://github.com/MeDeoDuck/Moabom_Prototype.git
cd Moabom_Prototype
```

Python 환경 구성:
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`.env` 파일 생성 (아래 항목을 팀원에게 직접 전달 — Git에는 절대 올리지 말 것):
```
DATABASE_URL=postgresql://...
YOUTUBE_API_KEY=...
GROQ_API_KEY=...
HF_TOKEN=...
```

---

## Step 3. 브랜치 전략 (권장)

각자 별도 브랜치에서 작업 후 `main`에 병합하는 방식:

```
main               ← 항상 동작하는 안정 버전
├── feat/내-작업
└── feat/팀원-작업
```

**나 (내 작업):**
```bash
git checkout -b feat/내-작업명
# 작업 후
git add .
git commit -m "feat: 내 작업 설명"
git push origin feat/내-작업명
```

**팀원:**
```bash
git checkout -b feat/팀원-작업명
# 작업 후
git push origin feat/팀원-작업명
```

---

## Step 4. Pull Request로 병합

1. GitHub 레포 접속
2. **Pull requests → New pull request**
3. `base: main` ← `compare: feat/작업브랜치` 선택
4. 제목/설명 작성 후 **Create pull request**
5. 상대방이 코드 리뷰 후 **Merge pull request**

---

## Step 5. 충돌(Conflict) 발생 시 해결

충돌은 두 명이 같은 파일의 같은 줄을 수정했을 때 발생한다.

```bash
# main 최신 내용을 내 브랜치로 가져오기
git checkout feat/내-작업명
git fetch origin
git merge origin/main
```

충돌 파일을 열면 아래처럼 표시됨:
```python
<<<<<<< HEAD (내 변경)
sentiment_analyzer = GroqAspectSentimentAnalyzer(...)
=======
sentiment_analyzer = KlueBertSentimentAnalyzer(...)
>>>>>>> origin/main (팀원 변경)
```

원하는 내용으로 수정 후:
```bash
git add <충돌파일>
git commit -m "merge: conflict resolved"
git push origin feat/내-작업명
```

---

## Step 6. 최신 main 동기화 (매일 작업 시작 전)

```bash
git checkout main
git pull origin main
git checkout feat/내-작업명
git merge main
```

---

## 이 프로젝트에서 충돌이 잘 나는 파일

| 파일 | 이유 |
|------|------|
| `scripts/api/sync.py` | 파이프라인 핵심 — 둘 다 건드릴 가능성 높음 |
| `scripts/database/schema.py` | DB 테이블 변경 시 충돌 |
| `scripts/config.py` | 환경변수 추가 시 |
| `requirements.txt` | 패키지 추가 시 |

> **팁:** 이 파일들은 미리 역할을 나눠서 한 명만 수정하거나, 수정 전에 슬랙/카톡으로 먼저 알리기.

---

## .gitignore 확인 사항

`.env`와 가상환경이 git에 올라가지 않도록 확인:

```bash
cat .gitignore
```

아래 항목이 없으면 추가:
```
.env
.venv/
__pycache__/
*.pyc
```

---

## 자주 쓰는 명령어 요약

```bash
# 현재 상태 확인
git status
git log --oneline -10

# 원격 최신 내용 가져오기
git pull origin main

# 내 변경사항 올리기
git add <파일>
git commit -m "설명"
git push origin <브랜치명>

# 브랜치 목록 확인
git branch -a
```
