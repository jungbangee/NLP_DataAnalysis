# AI 강의분석 리포트 시스템

STT(Speech-to-Text) 기반 강의 텍스트를 AI로 분석하여 강사별 역량을 평가하고 시각화하는 웹 대시보드입니다.

## 주요 기능

- `.txt` 강의 파일 업로드 및 5개 카테고리 자동 분석
- 레이더 차트 · 막대 차트 · 점수 카드로 결과 시각화
- 강사별 종합 평가 (역량 프로파일, 강점/약점, 개발 과제) AI 자동 생성
- 강사 간 비교 대시보드 (카테고리 비교, 날짜별 추이, 성장률)
- 분석 결과 PDF · DOCX 내보내기
- MongoDB 기반 분석 이력 저장 및 관리

---

## 프로젝트 구조

```
NLP_Task_AI_Report/
│
├── server.js                  # Express 메인 서버 (API + 인증 + DB 연동)
├── package.json
│
├── public/                    # 프론트엔드 HTML (정적 서빙)
│   ├── login.html             # 로그인 페이지
│   ├── dashboard.html         # 메인 대시보드 (강의 분석 업로드)
│   ├── instructors.html       # 강사 목록 대시보드
│   ├── instructor.html        # 강사 개인 종합평가 페이지
│   ├── analysis.html          # 강의별 상세 분석 결과 페이지
│   └── comparison.html        # 강사 간 비교 분석 페이지
│
├── cate1,5/                   # 카테고리 1·5 분석 스크립트
│   └── lecture_analyzer.py    # 언어 표현 품질 / 수강생 상호작용 분석
│
├── cate2/                     # 카테고리 2 분석 스크립트
│   └── v8_unified.py          # 강의 도입 및 구조 분석
│
├── cate3/                     # 카테고리 3 분석 스크립트
│   └── main.py                # 개념 설명 명확성 분석
│
├── cate4/                     # 카테고리 4 분석 스크립트
│   └── cate4_analyze_lecture.py  # 예시 및 실습 연계 분석
│
├── instructor_summary.py      # 강사 종합평가 AI 생성 스크립트
├── daily_summary.py           # 일별 강의 요약 생성 스크립트
├── generate_docx.py           # DOCX 내보내기 스크립트
│
├── json/                      # 기분석 JSON 결과물 (DB import용)
│   ├── cate15/                # cate1 + cate5 분석 결과
│   ├── cate2/                 # cate2 분석 결과
│   ├── cate3/                 # cate3 분석 결과
│   ├── cate4/                 # cate4 분석 결과
│   ├── 데일리평가/             # 일별 요약 결과
│   └── 강사평가 결과_날짜별추이/ # 강사별 종합평가 결과
│
├── results/                   # 분석 중간 결과물 (로컬 캐시)
├── results_unified/           # 통합 분석 결과 (summary + instructor)
├── uploads/                   # 업로드된 CSV 메타데이터 파일
├── backup/                    # DB 백업 디렉토리
│
├── import_to_db.py            # json/ 폴더 결과물을 MongoDB에 일괄 import
├── backup_db.py               # MongoDB 컬렉션을 JSON으로 백업
└── .env                       # 환경변수 설정
```

---

## 평가 카테고리

| 카테고리 | 항목 | 설명 |
|----------|------|------|
| Cate 1 | 1.1 ~ 1.3 | 언어 표현 품질 (발음, 문장 완성도, 언어 품질) |
| Cate 2 | 2.1 ~ 2.5 | 강의 도입 및 구조 (학습목표, 전날복습, 개념정의 등) |
| Cate 3 | 3.1 ~ 3.4 | 개념 설명 명확성 (설명순서, 핵심강조, 비유활용 등) |
| Cate 4 | 4.1 ~ 4.3 | 예시 및 실습 연계 (예시적절성, 실습연계, 오류대응) |
| Cate 5 | 5.1 ~ 5.3 | 수강생 상호작용 (질문유도, 반응확인, 참여독려) |

각 항목은 1~5점으로 평가되며, 100점 만점으로 환산됩니다.

---

## MongoDB 컬렉션 구조

| 컬렉션 | 설명 |
|--------|------|
| `categoryresults` | 강의별 카테고리 분석 결과 (cate1~5) |
| `dailysummaries` | 강의별 일일 종합 요약 |
| `instructorsummaries` | 강사별 종합평가 (AI 생성) |
| `analyses` | 분석 실행 이력 |
| `metas` | 강의 메타데이터 (CSV 업로드) |

---

## 설치 및 실행

### 사전 요구사항

- Node.js 18+
- Python 3.10+
- MongoDB 6.0+

### 환경변수 설정 (`.env`)

```env
MONGO_URI=mongodb://127.0.0.1:27017/nlp_lecture
SESSION_SECRET=your_secret_key
ADMIN_ID=admin
ADMIN_PW=your_password
GOOGLE_API_KEY=your_gemini_api_key
PORT=3000
```

### 의존성 패키지

**Node.js 패키지** (`npm install` 로 일괄 설치)

| 패키지 | 용도 |
|--------|------|
| `express` | 웹 서버 프레임워크 |
| `express-session` | 로그인 세션 관리 |
| `mongoose` | MongoDB ODM |
| `multer` | 파일 업로드 처리 |
| `dotenv` | 환경변수 로드 |

**Python 패키지**

| 패키지 | 용도 | 설치 명령 |
|--------|------|-----------|
| `google-genai` | Gemini AI API 호출 | `pip install google-genai` |
| `pymongo` | MongoDB 연결 | `pip install pymongo` |
| `python-dotenv` | 환경변수 로드 | `pip install python-dotenv` |
| `python-docx` | DOCX 파일 생성 | `pip install python-docx` |
| `Pillow` | 차트 이미지 처리 | `pip install Pillow` |
| `pandas` | 데이터 처리 | `pip install pandas` |
| `pydantic` | 데이터 유효성 검사 | `pip install pydantic` |

### 설치

```bash
# Node.js 패키지
npm install

# Python 패키지 (한 번에 설치)
pip install google-genai pymongo python-dotenv python-docx Pillow pandas pydantic
```

### 실행

```bash
node server.js
```

브라우저: `http://localhost:3000`

---

## DB 관련 유틸리티

### 백업

```bash
python backup_db.py
# → backup/YYYYMMDD_HHMM/ 폴더에 컬렉션별 JSON 저장
```

### 기분석 결과 일괄 Import

`json/` 폴더에 분석 결과 JSON 파일들을 배치한 후 실행:

```bash
python import_to_db.py
```

---

## 분석 흐름

```
.txt 강의 파일 업로드
        ↓
server.js → cate1~5 Python 스크립트 병렬 실행
        ↓
각 카테고리 점수 + 피드백 생성
        ↓
MongoDB (categoryresults) 저장
        ↓
daily_summary.py → 일별 종합 요약 생성
        ↓
instructor_summary.py → 강사 종합평가 생성 (수동 실행)
        ↓
웹 대시보드에서 시각화 / PDF · DOCX 내보내기
```

---

## 주의사항

- `.env` 파일은 Git에 포함되지 않습니다. 직접 생성해야 합니다.
- `uploads/`, `backup/`, `results/`, `results_unified/`, `node_modules/`, `json/` 폴더는 `.gitignore`에 추가를 권장합니다.
