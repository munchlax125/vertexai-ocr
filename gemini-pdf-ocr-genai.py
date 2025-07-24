# -*- coding: utf-8 -*-
import os
import re
import json
import gspread
from google.oauth2 import service_account
import vertexai
from vertexai.generative_models import GenerativeModel
from dotenv import load_dotenv
import sys
import time
from datetime import datetime

# UTF-8 인코딩 강제 설정
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

load_dotenv()

# --- Vertex AI 설정 ---
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# --- 기존 설정 ---
SERVICE_ACCOUNT_FILE = 'pdf-ocr.json'
SPREADSHEET_NAME = 'pdf-ocr'
PDF_FOLDER_PATH = './masked-pdfs/'

# --- 추출 필드 및 프롬프트 ---
EXTRACTION_FIELDS = [
    "성명", "생년월일", "안내유형", "기장의무", "추계시 적용경비율",
    "소득종류", "이자", "배당", "근로-단일", "근로-복수",
    "연금", "기타", "종교인 기타소득유무", "중간예납세액", "원천징수세액",
    "국민연금보험료", "개인연금저축", "소기업소상공인공제부금 (노란우산공제)",
    "퇴직연금세액공제", "연금계좌세액공제", "사업자 등록번호", "상호", "수입금액 구분코드",
    "업종 코드", "사업 형태", "기장 의무", "경비율",
    "수입금액", "일반", "자가", "일반(기본)", "자가(초과)"
]

json_example = "[\n" + "  {\n" + ",\n".join([f'    "{field}": "값"' for field in EXTRACTION_FIELDS]) + "\n  },\n  {\n" + ",\n".join([f'    "{field}": "값2"' for field in EXTRACTION_FIELDS]) + "\n  }\n]"

GEMINI_PROMPT = f"""
## 역할
당신은 주어진 문서 전체를 종합적으로 분석하여, 여러 다른 위치와 형식의 표나 텍스트에서 데이터를 정확히 추출하고 구조화된 JSON으로 변환하는 OCR 전문가입니다.

## 작업 순서

### 1단계: 전체 문서에서 단일 값 필드 스캔
먼저 문서 전체를 스캔하여 다음 항목들처럼 주로 한 번만 나타나는 값들을 찾습니다:
- "성명", "생년월일", "안내유형", "기장의무"
- "중간예납세액", "원천징수세액"
- "국민연금보험료", "개인연금저축", "소기업소상공인공제부금 (노란우산공제)" 등

### 2단계: 사업소득 표의 모든 행 찾기
'사업장별 수입금액' 또는 유사한 표에서 **모든 행(데이터)을 찾아주세요**. 
- 각 행은 하나의 사업소득 항목을 나타냅니다
- **빈 행이나 누락된 행이 없도록 주의깊게 확인해주세요**
- 다음 필드들을 각 행에서 추출: "사업자 등록번호", "상호", "수입종류 구분코드", "업종 코드", "수입금액", "경비율" 등

### 3단계: 각 행별 JSON 객체 생성
**사업소득 표의 각 행마다** 별도의 JSON 객체를 생성합니다:
1. 해당 행의 사업 관련 데이터로 객체를 채웁니다
2. **1단계에서 찾은 모든 공통 데이터(성명, 생년월일 등)를 동일하게 복사합니다**

### 4단계: 완전한 JSON 배열 생성
- **모든 사업소득 행이 포함되도록 확인**
- 각 객체는 모든 필드를 포함해야 함
- 값이 없는 필드는 "N/A" 또는 빈 문자열로 설정

## 중요 지침
- **"성명","생년월일","사업자 등록번호","상호"는 개인정보 보호 때문에 일부러 마스킹처리했습니다. 값이 없습니다. 그냥 빈칸으로 두세요.
- **절대로 데이터를 누락하지 마세요**
- **모든 사업소득 행을 찾아 각각 별도의 JSON 객체로 만드세요**
- 하나의 문서에 여러 사업소득이 있다면, 그 수만큼 JSON 객체가 생성되어야 합니다

### 추출할 항목
{', '.join(EXTRACTION_FIELDS)}

### 출력 형식 (여러 행이 있을 경우의 예시)
{json_example}

**반드시 JSON 배열 형태로만 응답하고, 다른 설명은 추가하지 마세요.**
"""

# --- 숫자 정제 대상 필드 ---
currency_fields = [
    "중간예납세액", "원천징수세액", "국민연금보험료", "개인연금저축",
    "소기업소상공인공제부금 (노란우산공제)", "퇴직연금세액공제", "연금계좌세액공제", "수입금액"
]

# --- 로그 출력 함수 (실시간 업데이트용) ---
def log_progress(message, flush=True):
    """진행상황을 실시간으로 출력"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    if flush:
        sys.stdout.flush()

# --- 유틸리티 함수 ---
def clean_currency(value: str) -> str:
    if not isinstance(value, str): return "0"
    if value.strip() in ["", "없음", "N/A"]: return "0"
    cleaned = re.sub(r"[^\d]", "", value)
    return cleaned if cleaned else "0"

def safe_extract_json(text):
    """
    텍스트에서 JSON 배열을 안전하게 추출하는 함수
    """
    # 여러 패턴으로 JSON 찾기 시도
    patterns = [
        r'\[[\s\S]*?\]',  # JSON 배열 (가장 우선)
        r'```json\s*([\s\S]*?)\s*```',  # 마크다운 JSON 블록
        r'```\s*([\s\S]*?)\s*```',  # 일반 마크다운 블록
        r'\{[\s\S]*?\}',  # JSON 객체 (단일)
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                # 마크다운 패턴의 경우
                if '```' in pattern and isinstance(match, str):
                    json_data = json.loads(match.strip())
                else:
                    json_data = json.loads(match)
                
                # 배열이 아닌 경우 배열로 변환
                if isinstance(json_data, dict):
                    return [json_data]
                elif isinstance(json_data, list):
                    return json_data
                    
            except json.JSONDecodeError:
                continue
    
    return None

def extract_data_with_vertex_ai(file_path: str, prompt: str, file_number: int, total_files: int):
    """
    Vertex AI를 직접 사용하여 PDF에서 데이터를 추출합니다.
    """
    log_progress(f"🔄 [{file_number}/{total_files}] '{os.path.basename(file_path)}' Vertex AI OCR 분석 시작...")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"❌ 오류: PDF 파일을 찾을 수 없습니다. 경로: {file_path}")

    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            if max_retries > 1:
                log_progress(f"🔄 [{file_number}/{total_files}] Vertex AI OCR 시도 {attempt + 1}/{max_retries}")
            
            # Vertex AI GenerativeModel 생성
            model = GenerativeModel("gemini-2.5-flash")
            
            # 파일 읽기
            log_progress(f"📤 [{file_number}/{total_files}] '{os.path.basename(file_path)}' 파일 읽는 중...")
            
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # PDF를 base64로 인코딩
            import base64
            pdf_data = base64.b64encode(file_data).decode('utf-8')
            
            # Part 생성
            from vertexai.generative_models import Part
            pdf_part = Part.from_data(
                data=file_data,
                mime_type="application/pdf"
            )
            
            # 콘텐츠 생성
            log_progress(f"🧠 [{file_number}/{total_files}] '{os.path.basename(file_path)}' Vertex AI 분석 중...")
            
            response = model.generate_content([pdf_part, prompt])
            
            log_progress(f"📄 [{file_number}/{total_files}] '{os.path.basename(file_path)}' 응답 수신 완료 (길이: {len(response.text)} 문자)")
            
            # JSON 추출
            extracted_data = safe_extract_json(response.text)
            
            if extracted_data is None:
                log_progress(f"⚠️ [{file_number}/{total_files}] '{os.path.basename(file_path)}' JSON 추출 실패 (시도 {attempt + 1})")
                if attempt < max_retries - 1:
                    log_progress(f"🔄 [{file_number}/{total_files}] '{os.path.basename(file_path)}' 재시도합니다...")
                    time.sleep(5)  # 재시도 전 대기
                    continue
                else:
                    raise ValueError(f"❌ '{os.path.basename(file_path)}' 모든 시도에서 JSON 추출 실패")
            
            log_progress(f"✅ [{file_number}/{total_files}] '{os.path.basename(file_path)}' Vertex AI OCR 성공! {len(extracted_data)}개 항목 발견")
            return extracted_data
            
        except Exception as e:
            log_progress(f"❌ [{file_number}/{total_files}] '{os.path.basename(file_path)}' Vertex AI OCR 실패 (시도 {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(5)  # 재시도 전 대기

def validate_and_fix_data(data_list, file_number, total_files, filename):
    """
    추출된 데이터의 유효성을 검사하고 수정
    """
    if not isinstance(data_list, list):
        log_progress(f"⚠️ [{file_number}/{total_files}] '{filename}' 데이터가 배열이 아닙니다. 배열로 변환합니다.")
        return [data_list] if isinstance(data_list, dict) else []
    
    validated_data = []
    for i, item in enumerate(data_list):
        if not isinstance(item, dict):
            log_progress(f"⚠️ [{file_number}/{total_files}] '{filename}' 항목 {i+1}이 객체가 아닙니다. 건너뜁니다.")
            continue
        
        # 모든 필드가 있는지 확인하고 없으면 추가
        for field in EXTRACTION_FIELDS:
            if field not in item:
                item[field] = "N/A"
        
        validated_data.append(item)
    
    log_progress(f"✅ [{file_number}/{total_files}] '{filename}' 데이터 검증 완료. {len(validated_data)}개 항목 유효")
    return validated_data

def add_to_spreadsheet_batch(worksheet, rows_to_append, file_number, total_files, filename):
    """스프레드시트에 배치로 데이터 추가"""
    try:
        log_progress(f"📊 [{file_number}/{total_files}] '{filename}' 구글시트에 {len(rows_to_append)}개 행 업로드 중...")
        worksheet.append_rows(rows_to_append)
        log_progress(f"✅ [{file_number}/{total_files}] '{filename}' 구글시트 업로드 완료!")
        return True
    except Exception as e:
        log_progress(f"❌ [{file_number}/{total_files}] '{filename}' 구글시트 업로드 실패: {e}")
        return False

# --- 🚀 Main ---
def main():
    start_time = time.time()
    log_progress("=" * 70)
    log_progress("🚀 PDF 일괄 Vertex AI OCR 처리 및 구글시트 업로드를 시작합니다")
    log_progress("=" * 70)
    
    # 시스템 정보 출력
    log_progress(f"📅 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_progress(f"📂 작업 폴더: {PDF_FOLDER_PATH}")
    log_progress(f"📊 대상 스프레드시트: {SPREADSHEET_NAME}")
    log_progress(f"🏭 Vertex AI 프로젝트: {PROJECT_ID}")
    log_progress(f"🌍 Vertex AI 위치: {LOCATION}")
    log_progress("-" * 70)

    # --- Vertex AI 및 Google Sheets 인증 ---
    try:
        # Vertex AI 초기화
        if not PROJECT_ID:
            raise ValueError("GOOGLE_CLOUD_PROJECT 환경변수가 설정되지 않았습니다.")
        
        log_progress("🔑 Vertex AI 초기화 중...")
        
        # 서비스 계정 인증 설정
        if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDENTIALS_PATH
            log_progress(f"🔐 서비스 계정 인증 파일 설정: {CREDENTIALS_PATH}")
        
        # 환경 변수 확인
        log_progress(f"🔍 환경 변수 확인:")
        log_progress(f"   - GOOGLE_CLOUD_PROJECT: {PROJECT_ID}")
        log_progress(f"   - GOOGLE_CLOUD_LOCATION: {LOCATION}")
        log_progress(f"   - GOOGLE_APPLICATION_CREDENTIALS: {CREDENTIALS_PATH}")
        
        # Vertex AI용 google-generativeai 설정
        import vertexai
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        
        log_progress("✅ Vertex AI 초기화 성공!")

        # Google Sheets 인증
        log_progress("📋 Google Sheets 연결 중...")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SPREADSHEET_NAME)
        worksheet = spreadsheet.sheet1
        
        # 오류 로그 시트 설정
        try:
            log_worksheet = spreadsheet.worksheet("오류_로그")
        except gspread.exceptions.WorksheetNotFound:
            log_worksheet = spreadsheet.add_worksheet(title="오류_로그", rows="100", cols="10")
            log_worksheet.append_row(["파일 이름", "오류 내용", "처리 시간"])
        
        log_progress("✅ 구글 스프레드시트 연결 성공!")
    except Exception as e:
        log_progress(f"❌ 인증 실패: {e}")
        return

    # 헤더 설정
    try:
        log_progress("📝 스프레드시트 헤더 확인 중...")
        first_row = worksheet.row_values(1)
        if not first_row:
            log_progress("📝 1행이 비어있어 헤더를 추가합니다...")
            headers = ["파일이름", "행번호"] + EXTRACTION_FIELDS
            worksheet.append_row(headers)
            log_progress("✅ 헤더 추가 완료!")
        else:
            log_progress("✅ 헤더가 이미 존재합니다.")
    except Exception as e:
        log_progress(f"❌ 헤더 확인 중 오류 발생: {e}")

    # PDF 파일 목록 가져오기
    try:
        log_progress("📂 PDF 파일 목록 스캔 중...")
        pdf_files = [f for f in os.listdir(PDF_FOLDER_PATH) if f.lower().endswith('.pdf')]
        if not pdf_files:
            log_progress(f"❌ '{PDF_FOLDER_PATH}' 폴더에 PDF 파일이 없습니다.")
            return
        
        # 파일명을 숫자 순서로 정렬 (1.pdf, 2.pdf, 3.pdf...)
        def natural_sort_key(filename):
            try:
                # 파일명에서 .pdf 제거하고 숫자로 변환
                number = int(filename.replace('.pdf', ''))
                return number
            except ValueError:
                # 숫자가 아닌 파일명은 맨 뒤로
                return 999999
        
        pdf_files.sort(key=natural_sort_key)
        
        log_progress(f"📂 총 {len(pdf_files)}개의 PDF 파일을 Vertex AI로 처리합니다")
        log_progress(f"📋 파일 목록: {pdf_files[:10]}{'...' if len(pdf_files) > 10 else ''}")
    except FileNotFoundError:
        log_progress(f"❌ 폴더를 찾을 수 없습니다: '{PDF_FOLDER_PATH}'")
        return

    total_rows_added = 0
    error_count = 0
    successful_files = 0

    # 파일 처리 시작
    log_progress(f"{'='*25} 📄 Vertex AI 파일별 OCR 처리 시작 {'='*25}")
    
    # 각 PDF 파일 처리
    for i, pdf_file in enumerate(pdf_files, 1):
        file_start_time = time.time()
        
        log_progress(f"")
        log_progress(f"📄 [{i}/{len(pdf_files)}] ===== {pdf_file} Vertex AI 처리 시작 =====")
        log_progress("-" * 50)
        
        try:
            full_path = os.path.join(PDF_FOLDER_PATH, pdf_file)
            
            # 파일 크기 정보 추가
            file_size = os.path.getsize(full_path) / 1024 / 1024  # MB
            log_progress(f"📏 [{i}/{len(pdf_files)}] '{pdf_file}' 파일 크기: {file_size:.2f} MB")
            
            # Vertex AI로 데이터 추출
            extracted_data_list = extract_data_with_vertex_ai(full_path, GEMINI_PROMPT, i, len(pdf_files))
            
            # 데이터 검증 및 수정
            validated_data = validate_and_fix_data(extracted_data_list, i, len(pdf_files), pdf_file)
            
            if not validated_data:
                log_progress(f"⚠️ [{i}/{len(pdf_files)}] '{pdf_file}'에서 유효한 데이터를 찾지 못했습니다.")
                log_worksheet.append_row([pdf_file, "유효한 데이터 없음", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                continue
            
            # 스프레드시트에 추가할 행들 준비
            log_progress(f"📊 [{i}/{len(pdf_files)}] '{pdf_file}' 스프레드시트 데이터 준비 중...")
            rows_to_append = []
            for j, extracted_data in enumerate(validated_data):
                # 모든 행에 파일 이름 표시 (확장자 제거)
                file_name_without_ext = pdf_file.replace('.pdf', '')  # .pdf 확장자 제거
                row_number = j + 1
                
                data_row = [file_name_without_ext, row_number]
                for field in EXTRACTION_FIELDS:
                    value = extracted_data.get(field, 'N/A')
                    if isinstance(value, str):
                        value = value.replace('\n', ' ').replace('\r', ' ')
                    if field in currency_fields:
                        value = clean_currency(str(value))
                    data_row.append(str(value))
                
                rows_to_append.append(data_row)
            
            # 스프레드시트에 실시간 추가
            if rows_to_append:
                success = add_to_spreadsheet_batch(worksheet, rows_to_append, i, len(pdf_files), pdf_file)
                if success:
                    total_rows_added += len(rows_to_append)
                    successful_files += 1
                else:
                    log_worksheet.append_row([pdf_file, "스프레드시트 추가 실패", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                    error_count += 1
                    continue
            
            # 처리 시간 계산
            file_end_time = time.time()
            processing_time = file_end_time - file_start_time
            
            log_progress(f"✅ [{i}/{len(pdf_files)}] '{pdf_file}' Vertex AI 처리 완료!")
            log_progress(f"   📊 OCR 추출: {len(validated_data)}개 항목")
            log_progress(f"   📝 시트 업로드: {len(rows_to_append)}개 행")
            log_progress(f"   ⏱️ 처리 시간: {processing_time:.2f}초")
            log_progress(f"   📈 전체 진행률: {i}/{len(pdf_files)} ({(i/len(pdf_files)*100):.1f}%)")
            log_progress(f"===== {pdf_file} Vertex AI 처리 완료 =====")

        except Exception as e:
            error_message = f"🚨 [{i}/{len(pdf_files)}] '{pdf_file}' Vertex AI 처리 중 오류 발생: {e}"
            log_progress(error_message)
            
            # 오류 로그에 기록
            log_worksheet.append_row([pdf_file, str(e), datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            error_count += 1
            continue

    # 총 처리 시간 계산
    end_time = time.time()
    total_processing_time = end_time - start_time

    # 최종 결과
    log_progress(f"")
    log_progress(f"{'='*25} ✨ Vertex AI 처리 완료 {'='*25}")
    log_progress(f"⏱️ 총 처리 시간: {total_processing_time:.2f}초 ({total_processing_time/60:.1f}분)")
    log_progress(f"📊 총 처리된 파일: {len(pdf_files)}개")
    log_progress(f"✅ 성공: {successful_files}개")
    log_progress(f"❌ 오류: {error_count}개")
    log_progress(f"📝 총 업로드 행 수: {total_rows_added}개")
    log_progress(f"⚡ 평균 처리 속도: {total_processing_time/successful_files:.2f}초/파일" if successful_files > 0 else "")
    
    if error_count > 0:
        log_progress(f"⚠️ 오류 상세 내용은 '오류_로그' 시트를 확인하세요.")
    
    log_progress("🎉 모든 Vertex AI OCR 및 구글시트 업로드 작업이 완료되었습니다!")
    log_progress("=" * 70)

if __name__ == '__main__':
    main()