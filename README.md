**Google Service Account 설정**

1. [Google Cloud Console](https://console.cloud.google.com/)에서 새 프로젝트 생성
2. Google Sheets API, Google Drive API, Vertex AI 활성화
3. 서비스 계정 생성 후 JSON 키 파일 다운로드
    
    [상세한 설명: JSON 키 파일 생성](https://www.notion.so/JSON-2333b90af4a080e89e97fddd3f7e5306?pvs=21)
    
4. 파일명을 `pdf-ocr.json`으로 변경하여 프로젝트 루트에 저장

**Google Sheet 권한 허용**

작성하고자 하는 구글 시트 파일을 열어 ‘공유’ 클릭 후 서비스 계정의 이메일을 편집자로 권한 허용
