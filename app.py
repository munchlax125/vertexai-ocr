from flask import Flask, request, jsonify, send_file, send_from_directory, Response
from flask_cors import CORS
import os
import tempfile
import zipfile
import uuid
from datetime import datetime
import threading
import logging
import subprocess
import json
import queue

from pdf_processor import PDFProcessor

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# 로깅 설정 (HTTP 요청 로그 레벨 조정)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Werkzeug 로깅 레벨을 WARNING으로 설정하여 HTTP 요청 로그 숨기기
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

# 설정
PDF_SOURCE_FOLDER = 'pdfs'
MASKED_PDF_FOLDER = 'masked-pdfs'
MAX_WORKERS = 4
BATCH_SIZE = 50

# 작업 상태 추적
job_status = {}
job_lock = threading.Lock()

# 실시간 로그 스트리밍을 위한 큐
log_queues = {}
log_queues_lock = threading.Lock()

# 폴더 생성
os.makedirs(PDF_SOURCE_FOLDER, exist_ok=True)
os.makedirs(MASKED_PDF_FOLDER, exist_ok=True)

# PDF 프로세서 초기화
pdf_processor = PDFProcessor(PDF_SOURCE_FOLDER, MASKED_PDF_FOLDER, BATCH_SIZE)

def update_job_status(job_id, status, progress=0, message="", error=None, log_output=None):
    """작업 상태 업데이트"""
    with job_lock:
        job_status[job_id] = {
            'status': status,
            'progress': progress,
            'message': message,
            'error': error,
            'log_output': log_output,
            'timestamp': datetime.now().isoformat()
        }

def add_log_to_queue(job_id, log_line):
    """실시간 로그 큐에 새 로그 추가"""
    with log_queues_lock:
        if job_id in log_queues:
            try:
                log_queues[job_id].put_nowait(log_line)
            except queue.Full:
                # 큐가 가득 찬 경우 오래된 로그 제거
                try:
                    log_queues[job_id].get_nowait()
                    log_queues[job_id].put_nowait(log_line)
                except queue.Empty:
                    pass

@app.route('/')
def index():
    """메인 페이지 - index.html 반환"""
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    """정적 파일 서빙 (CSS, JS 등)"""
    return send_from_directory('.', filename)

@app.route('/scan-pdfs', methods=['GET'])
def scan_pdfs():
    """pdfs 폴더의 파일 목록 스캔"""
    try:
        result = pdf_processor.scan_pdf_files()
        return jsonify({
            'success': True,
            'files': result['files'],
            'count': result['count'],
            'total_size': result['total_size'],
            'folder': PDF_SOURCE_FOLDER
        })
    except Exception as e:
        return jsonify({'error': f'폴더 스캔 중 오류: {str(e)}'}), 500

@app.route('/mask-pdfs', methods=['POST'])
def mask_pdfs():
    """pdfs 폴더의 파일들을 마스킹 처리"""
    try:
        # 작업 ID 생성
        job_id = str(uuid.uuid4())
        update_job_status(job_id, 'pending', 0, '마스킹 처리 대기 중')
        
        # 백그라운드에서 비동기 처리 시작
        def background_task():
            def status_callback(status, progress, message):
                update_job_status(job_id, status, progress, message)
            
            try:
                result = pdf_processor.process_masking(status_callback)
                # 결과를 job_status에 저장
                with job_lock:
                    job_status[job_id]['result'] = result
            except Exception as e:
                update_job_status(job_id, 'failed', 0, '', str(e))
        
        thread = threading.Thread(target=background_task)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': '마스킹 처리가 시작되었습니다.',
            'source_folder': PDF_SOURCE_FOLDER,
            'target_folder': MASKED_PDF_FOLDER
        })
        
    except Exception as e:
        return jsonify({'error': f'마스킹 작업 시작 중 오류: {str(e)}'}), 500

def run_ocr_with_realtime_output(job_id):
    """실시간 출력을 캡처하면서 OCR 스크립트 실행 (시간 제한 없음)"""
    try:
        update_job_status(job_id, 'running', 10, 'Gemini OCR 스크립트 실행 중...')
        
        # 실시간 로그 큐 생성
        with log_queues_lock:
            log_queues[job_id] = queue.Queue(maxsize=1000)
        
        # 환경 변수 설정
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUNBUFFERED'] = '1'
        
        # 프로세스 시작 (timeout 제거)
        process = subprocess.Popen(
            ['python', 'gemini-pdf-ocr-genai.py'], 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            env=env,
            bufsize=1,
            universal_newlines=True
        )
        
        output_lines = []
        
        # 실시간으로 출력 읽기
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                if line:  # 빈 줄 제외
                    output_lines.append(line)
                    
                    # 실시간 로그 큐에 추가 (타임스탬프 포함된 원본 그대로)
                    add_log_to_queue(job_id, line)
                    
                    # 진행률 계산 (파일별 처리 단계 기반)
                    progress = 20
                    if '처리 시작' in line:
                        progress = min(30, 20 + len(output_lines) // 10)
                    elif 'OCR 분석 시작' in line:
                        progress = min(50, 30 + len(output_lines) // 8)
                    elif 'AI 분석 중' in line:
                        progress = min(70, 50 + len(output_lines) // 6)
                    elif '구글시트 업로드' in line:
                        progress = min(85, 70 + len(output_lines) // 4)
                    elif '완전 처리 완료' in line:
                        progress = min(95, 85 + len(output_lines) // 3)
                    elif '모든 처리 완료' in line:
                        progress = 100
                    elif '연결' in line or '초기화' in line:
                        progress = 15
                    
                    # 주요 메시지만 status에 표시
                    status_message = "OCR 처리 진행 중..."
                    if any(keyword in line for keyword in 
                        ['처리 완료', '업로드 완료', '시작', '연결', '성공', '실패', '오류', '완료']):
                        status_message = line.replace('[', '').replace(']', '').split('] ')[-1] if '] ' in line else line
                    
                    # 최근 로그만 status에 포함 (로그 스트림은 별도)
                    recent_logs = '\n'.join(output_lines[-50:])  # 최근 50줄만
                    update_job_status(job_id, 'running', progress, status_message, log_output=recent_logs)
        
        # 프로세스 완료 대기 (무제한)
        return_code = process.wait()
        
        # 전체 출력 결합
        full_output = '\n'.join(output_lines)
        
        if return_code == 0:
            completion_msg = "🎉 OCR 처리가 완전히 완료되었습니다!"
            add_log_to_queue(job_id, f"[{datetime.now().strftime('%H:%M:%S')}] {completion_msg}")
            update_job_status(job_id, 'completed', 100, 'OCR 처리 완료', log_output=full_output)
            with job_lock:
                job_status[job_id]['result'] = {
                    'output': full_output,
                    'success': True
                }
        else:
            error_msg = "❌ OCR 처리가 실패했습니다."
            add_log_to_queue(job_id, f"[{datetime.now().strftime('%H:%M:%S')}] {error_msg}")
            update_job_status(job_id, 'failed', 0, 'OCR 처리 실패', full_output, log_output=full_output)
                    
    except Exception as e:
        error_msg = f"OCR 처리 오류: {str(e)}"
        add_log_to_queue(job_id, f"[{datetime.now().strftime('%H:%M:%S')}] ❌ {error_msg}")
        update_job_status(job_id, 'failed', 0, error_msg, str(e))
        logger.error(error_msg)
    finally:
        # 로그 큐 정리
        with log_queues_lock:
            if job_id in log_queues:
                del log_queues[job_id]

@app.route('/run-gemini-ocr-async', methods=['POST'])
def run_gemini_ocr_async():
    """비동기 Gemini OCR 처리"""
    try:
        if not os.path.exists(MASKED_PDF_FOLDER):
            return jsonify({'error': f'"{MASKED_PDF_FOLDER}" 폴더가 없습니다.'}), 400
        
        masked_files = [f for f in os.listdir(MASKED_PDF_FOLDER) if f.lower().endswith('.pdf')]
        if not masked_files:
            return jsonify({'error': f'"{MASKED_PDF_FOLDER}" 폴더에 처리할 파일이 없습니다.'}), 400
        
        # 작업 ID 생성
        job_id = str(uuid.uuid4())
        update_job_status(job_id, 'pending', 0, f'{len(masked_files)}개 파일 OCR 처리 대기 중')
        
        # 백그라운드에서 실시간 출력과 함께 OCR 실행
        thread = threading.Thread(target=run_ocr_with_realtime_output, args=(job_id,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': f'{len(masked_files)}개 파일 OCR 처리가 시작되었습니다. (시간 제한 없음)',
            'source_folder': MASKED_PDF_FOLDER
        })
        
    except Exception as e:
        return jsonify({'error': f'OCR 작업 시작 중 오류: {str(e)}'}), 500

@app.route('/extract-info', methods=['POST'])
def extract_personal_info():
    """개인정보 추출"""
    try:
        personal_info = pdf_processor.extract_personal_info()
        
        return jsonify({
            'success': True,
            'personal_info': personal_info,
            'total_extracted': len(personal_info),
            'source_folder': PDF_SOURCE_FOLDER
        })
        
    except Exception as e:
        return jsonify({'error': f'정보 추출 중 오류: {str(e)}'}), 500

@app.route('/job-status/<job_id>')
def get_job_status(job_id):
    """작업 상태 조회"""
    with job_lock:
        if job_id not in job_status:
            return jsonify({'error': '작업 ID를 찾을 수 없습니다.'}), 404
        return jsonify(job_status[job_id])

@app.route('/stream-logs/<job_id>')
def stream_logs(job_id):
    """실시간 로그 스트리밍 (Server-Sent Events)"""
    def generate():
        # 기존 로그가 있다면 먼저 전송
        with job_lock:
            if job_id in job_status and job_status[job_id].get('log_output'):
                existing_logs = job_status[job_id]['log_output'].split('\n')
                for log_line in existing_logs:
                    if log_line.strip():
                        yield f"data: {json.dumps({'type': 'log', 'message': log_line})}\n\n"
        
        # 실시간 로그 스트림
        timeout_count = 0
        max_timeout = 300  # 5분 타임아웃
        
        while timeout_count < max_timeout:
            try:
                with log_queues_lock:
                    if job_id not in log_queues:
                        # 작업이 완료되었는지 확인
                        with job_lock:
                            if job_id in job_status:
                                status = job_status[job_id]['status']
                                if status in ['completed', 'failed']:
                                    yield f"data: {json.dumps({'type': 'status', 'status': status})}\n\n"
                                    break
                        timeout_count += 1
                        time.sleep(1)
                        continue
                    
                    log_queue = log_queues[job_id]
                
                try:
                    # 0.5초 대기로 새 로그 확인
                    log_line = log_queue.get(timeout=0.5)
                    yield f"data: {json.dumps({'type': 'log', 'message': log_line})}\n\n"
                    timeout_count = 0  # 로그를 받았으므로 타임아웃 리셋
                except queue.Empty:
                    timeout_count += 1
                    continue
                    
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                break
        
        yield f"data: {json.dumps({'type': 'close'})}\n\n"
    
    return Response(generate(), mimetype='text/plain')

import time

@app.route('/download-masked')
def download_masked_files():
    """마스킹된 파일들을 ZIP으로 다운로드"""
    try:
        if not os.path.exists(MASKED_PDF_FOLDER):
            return jsonify({'error': f'"{MASKED_PDF_FOLDER}" 폴더가 없습니다.'}), 400
        
        masked_files = [f for f in os.listdir(MASKED_PDF_FOLDER) if f.endswith('.pdf')]
        
        if not masked_files:
            return jsonify({'error': '다운로드할 마스킹된 파일이 없습니다.'}), 400
        
        zip_path = os.path.join(tempfile.gettempdir(), 
                               f'masked_files_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in masked_files:
                file_path = os.path.join(MASKED_PDF_FOLDER, filename)
                zipf.write(file_path, filename)
            
            # 매핑 파일도 포함
            mapping_path = os.path.join(MASKED_PDF_FOLDER, 'file_mapping.json')
            if os.path.exists(mapping_path):
                zipf.write(mapping_path, 'file_mapping.json')
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f'masked_pdfs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
            mimetype='application/zip'
        )
        
    except Exception as e:
        return jsonify({'error': f'다운로드 중 오류: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """서버 상태 확인 - Vertex AI 버전"""
    
    # 폴더 상태 확인
    pdfs_exists = os.path.exists(PDF_SOURCE_FOLDER)
    pdfs_count = len([f for f in os.listdir(PDF_SOURCE_FOLDER) if f.endswith('.pdf')]) if pdfs_exists else 0
    
    masked_exists = os.path.exists(MASKED_PDF_FOLDER)
    masked_count = len([f for f in os.listdir(MASKED_PDF_FOLDER) if f.endswith('.pdf')]) if masked_exists else 0
    
    # Vertex AI 환경 변수 체크
    vertex_ai_config = {
        'project_id': os.getenv('GOOGLE_CLOUD_PROJECT'),
        'location': os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1'),
        'credentials_path': os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
        'credentials_exists': os.path.exists(os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')) if os.getenv('GOOGLE_APPLICATION_CREDENTIALS') else False
    }
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '4.0.0 (Vertex AI)',
        'api_type': 'Vertex AI',
        'vertex_ai': vertex_ai_config,
        'folders': {
            'pdfs': {
                'exists': pdfs_exists,
                'count': pdfs_count,
                'path': PDF_SOURCE_FOLDER
            },
            'masked_pdfs': {
                'exists': masked_exists,
                'count': masked_count,
                'path': MASKED_PDF_FOLDER
            }
        },
        'max_workers': MAX_WORKERS,
        'batch_size': BATCH_SIZE
    })

if __name__ == '__main__':
    print("🚀 PDF 통합 처리 백엔드 서버를 시작합니다...")
    print(f"📂 원본 PDF 폴더: {PDF_SOURCE_FOLDER}")
    print(f"📂 마스킹 폴더: {MASKED_PDF_FOLDER}")
    print(f"⚙️ 최대 동시 처리: {MAX_WORKERS} 스레드")
    print(f"📦 배치 크기: {BATCH_SIZE} 파일")
    print("🌐 서버 주소: http://localhost:5000")
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)