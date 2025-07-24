# 🗒️ 개요

## **프로젝트 설명**

1. Gemini AI를 활용해 PDF를 OCR하여 필요한 데이터를 추출한다.
2. OCR한 데이터를 JSON으로 파싱한다.
3. 파싱한 데이터를 Google Sheets의 행과 열에 맞춰 입력한다.

## **사용 기술 및 특징**

- **AI**: Gemini 2.5 Flash
- **인증**: Google Service Account
- **클라우드**: Google Sheets API, Google Drive API

---

# ⭐ 주요 기능

- **자동 PDF 처리**: 폴더 내 모든 PDF 파일을 일괄 처리
- **다중 행 처리**: 하나의 PDF에서 여러 데이터를 개별 행으로 분리
- **Google Sheets 연동**: 추출된 데이터를 자동으로 구글 스프레드시트에 저장
- **오류 기록**: 처리 실패 시 자동으로 오류 로그 시트에 기록


### 실행 단계

```bash
# 1. 서버 시작
python app.py

# 2. 웹 브라우저에서 접속
# index.html 실행

# 3. 5단계 워크플로우 실행
# 📁 1단계: PDF 폴더 스캔
# 🎭 2단계: 마스킹 처리
# 🤖 3단계: OCR 처리
# 📊 4단계: 개인정보 엑셀 생성
# 🔒 5단계: XLOOKUP 수동 결합

```
