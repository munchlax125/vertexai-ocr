import fitz  # PyMuPDF
import os
import json
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self, source_folder, target_folder, batch_size=50):
        self.source_folder = source_folder
        self.target_folder = target_folder
        self.batch_size = batch_size
        
        # 기본 마스킹 좌표
        self.default_masking_areas = [
            {'x1': 190, 'y1': 122, 'x2': 270, 'y2': 135},  # 이름
            {'x1': 430, 'y1': 122, 'x2': 510, 'y2': 135},  # 생년월일
            {'x1': 60, 'y1': 255, 'x2': 170, 'y2': 355},   # 사업자번호
        ]
    
    def natural_sort_key(self, filename):
        """파일명을 숫자 순서로 정렬하기 위한 키 함수"""
        try:
            # 파일명에서 .pdf 제거하고 숫자로 변환
            number = int(filename.replace('.pdf', ''))
            return number
        except ValueError:
            # 숫자가 아닌 파일명은 맨 뒤로
            return 999999
    
    def scan_pdf_files(self):
        """PDF 파일 스캔"""
        if not os.path.exists(self.source_folder):
            raise Exception(f"'{self.source_folder}' 폴더가 존재하지 않습니다.")
        
        pdf_files = [f for f in os.listdir(self.source_folder) if f.lower().endswith('.pdf')]
        
        # 숫자 순서로 정렬
        pdf_files.sort(key=self.natural_sort_key)
        
        file_info = []
        total_size = 0
        
        for filename in pdf_files:
            file_path = os.path.join(self.source_folder, filename)
            file_size = os.path.getsize(file_path)
            total_size += file_size
            
            file_info.append({
                'filename': filename,
                'size': file_size
            })
        
        return {
            'files': file_info,
            'count': len(file_info),
            'total_size': total_size
        }
    
    def redact_pdf_batch(self, files_batch, redaction_areas, status_callback=None):
        """PDF 배치 마스킹 처리 - 첫 페이지만 추출"""
        processed_files = []
        
        for i, (input_path, output_path, filename) in enumerate(files_batch):
            try:
                # PDF 첫 페이지만 마스킹 처리
                doc = fitz.open(input_path)
                
                # 첫 페이지만 처리
                if len(doc) > 0:
                    first_page = doc[0]  # 첫 번째 페이지만
                    
                    # 마스킹 영역 적용
                    for area in redaction_areas:
                        rect = fitz.Rect(area['x1'], area['y1'], area['x2'], area['y2'])
                        first_page.add_redact_annot(rect)
                    first_page.apply_redactions()
                    
                    # 새 문서 생성 (첫 페이지만)
                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=0, to_page=0)  # 첫 페이지만 복사
                    new_doc.save(output_path)
                    new_doc.close()
                
                doc.close()
                
                processed_files.append({
                    'original_name': filename,
                    'masked_name': os.path.basename(output_path),
                    'size': os.path.getsize(output_path)
                })
                
                # 진행률 콜백
                if status_callback:
                    progress = ((i + 1) / len(files_batch)) * 100
                    status_callback('running', progress, f'배치 처리 중: {i+1}/{len(files_batch)} (첫 페이지 추출)')
                
            except Exception as e:
                logger.error(f"파일 {filename} 처리 오류: {e}")
                continue
        
        return processed_files
    
    def process_masking(self, status_callback=None):
        """전체 마스킹 처리 프로세스"""
        try:
            if status_callback:
                status_callback('running', 0, 'PDF 파일 스캔 중...')
            
            # PDF 파일 찾기
            pdf_files = [f for f in os.listdir(self.source_folder) if f.lower().endswith('.pdf')]
            
            # 숫자 순서로 정렬 (중요!)
            pdf_files.sort(key=self.natural_sort_key)
            
            if not pdf_files:
                raise Exception(f"'{self.source_folder}' 폴더에 PDF 파일이 없습니다.")
            
            # 타겟 폴더 정리
            if os.path.exists(self.target_folder):
                for file in os.listdir(self.target_folder):
                    if file.endswith('.pdf'):
                        os.remove(os.path.join(self.target_folder, file))
            else:
                os.makedirs(self.target_folder, exist_ok=True)
            
            if status_callback:
                status_callback('running', 5, f'{len(pdf_files)}개 파일 발견. 마스킹 처리 시작...')
            
            # 파일을 배치로 나누기
            batches = [pdf_files[i:i + self.batch_size] for i in range(0, len(pdf_files), self.batch_size)]
            total_files = len(pdf_files)
            processed_count = 0
            all_processed_files = []
            file_mapping = []
            
            # 각 배치를 순차 처리
            for batch_idx, batch in enumerate(batches):
                if status_callback:
                    status_callback('running', 
                                  10 + (batch_idx / len(batches)) * 80,
                                  f'배치 {batch_idx + 1}/{len(batches)} 처리 중')
                
                # 배치용 파일 경로 준비
                batch_files = []
                for filename in batch:
                    file_number = processed_count + len(batch_files) + 1
                    input_path = os.path.join(self.source_folder, filename)
                    output_filename = f"{file_number}.pdf"
                    output_path = os.path.join(self.target_folder, output_filename)
                    batch_files.append((input_path, output_path, filename))
                
                # 배치 처리
                def batch_status_callback(status, progress, message):
                    if status_callback:
                        status_callback(status, progress, message)
                
                batch_result = self.redact_pdf_batch(
                    batch_files, 
                    self.default_masking_areas, 
                    batch_status_callback
                )
                all_processed_files.extend(batch_result)
                
                # 매핑 정보 생성
                for i, filename in enumerate(batch):
                    file_number = processed_count + i + 1
                    file_mapping.append({
                        'number': file_number,
                        'original_name': filename,
                        'masked_name': f"{file_number}.pdf"
                    })
                
                processed_count += len(batch)
                
                # 진행률 업데이트
                if status_callback:
                    overall_progress = 10 + (processed_count / total_files) * 80
                    status_callback('running', overall_progress, 
                                  f'처리 완료: {processed_count}/{total_files} (첫 페이지 추출)')
                
                # 메모리 정리를 위한 잠시 대기
                time.sleep(0.1)
            
            # 매핑 정보 저장
            mapping_path = os.path.join(self.target_folder, 'file_mapping.json')
            with open(mapping_path, 'w', encoding='utf-8') as f:
                json.dump(file_mapping, f, ensure_ascii=False, indent=2)
            
            if status_callback:
                status_callback('completed', 100, 
                              f'마스킹 완료: {len(all_processed_files)}개 파일 처리됨 (첫 페이지만)')
            
            return {
                'processed_files': all_processed_files,
                'file_mapping': file_mapping,
                'total_processed': len(all_processed_files),
                'target_folder': self.target_folder
            }
            
        except Exception as e:
            if status_callback:
                status_callback('failed', 0, str(e))
            raise
    
    def extract_personal_info(self):
        """파일명에서 앞 4글자 코드만 추출 - 마스킹 매핑 정보를 기반으로 순서 결정"""
        if not os.path.exists(self.source_folder):
            raise Exception(f"'{self.source_folder}' 폴더가 존재하지 않습니다.")
        
        # 마스킹 매핑 정보 로드
        mapping_path = os.path.join(self.target_folder, 'file_mapping.json')
        if os.path.exists(mapping_path):
            # 매핑 정보가 있으면 그 순서를 따름 (OCR 처리 순서와 동일)
            with open(mapping_path, 'r', encoding='utf-8') as f:
                file_mapping = json.load(f)
            
            personal_info = []
            for mapping in file_mapping:
                filename = mapping['original_name']
                order = mapping['number']  # 마스킹된 파일 번호 = OCR 처리 순서
                
                # 파일명에서 .pdf 제거
                file_base = filename.replace('.pdf', '')
                
                # 앞 4글자 추출 (파일명이 4글자보다 짧으면 전체)
                code = file_base[:4] if len(file_base) >= 4 else file_base
                
                # 코드가 비어있지 않으면 추가
                if code.strip():
                    personal_info.append({
                        'order': order,  # 마스킹 순서 = OCR 처리 순서
                        'code': code,    # 앞 4글자 코드
                        'original_filename': filename
                    })
            
            # 순서대로 정렬
            personal_info.sort(key=lambda x: x['order'])
            return personal_info
        
        else:
            # 매핑 정보가 없으면 기존 방식 (파일명 순서)
            pdf_files = [f for f in os.listdir(self.source_folder) if f.lower().endswith('.pdf')]
            pdf_files.sort(key=self.natural_sort_key)
            
            personal_info = []
            
            for i, filename in enumerate(pdf_files, 1):
                # 파일명에서 .pdf 제거
                file_base = filename.replace('.pdf', '')
                
                # 앞 4글자 추출 (파일명이 4글자보다 짧으면 전체)
                code = file_base[:4] if len(file_base) >= 4 else file_base
                
                # 코드가 비어있지 않으면 추가
                if code.strip():
                    personal_info.append({
                        'order': i,
                        'code': code,    # 앞 4글자 코드
                        'original_filename': filename
                    })
            
            return personal_info