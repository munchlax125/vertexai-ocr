// ui-controllers.js - UI 컨트롤러 및 유틸리티 함수들 (앞 4글자 코드 추출 버전)

// UI 컨트롤러
class UIController {
    static activateStep(stepNumber) {
        // 모든 스텝 비활성화
        for (let i = 1; i <= 4; i++) {
            const stepCard = document.getElementById(`step${i}`);
            const progressStep = document.getElementById(`progress-step-${i}`);
            
            stepCard.classList.remove('active');
            progressStep.classList.remove('active');
        }
        
        // 현재 스텝 활성화
        const currentStep = document.getElementById(`step${stepNumber}`);
        const currentProgress = document.getElementById(`progress-step-${stepNumber}`);
        
        currentStep.classList.add('active');
        currentProgress.classList.add('active');
        
        // 스크롤을 현재 스텝으로 이동
        currentStep.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    static completeStep(stepNumber) {
        const stepCard = document.getElementById(`step${stepNumber}`);
        const stepNumberEl = document.getElementById(`step${stepNumber}-number`);
        const progressStep = document.getElementById(`progress-step-${stepNumber}`);
        
        stepCard.classList.add('completed');
        stepCard.classList.remove('active');
        stepNumberEl.classList.add('completed');
        stepNumberEl.innerHTML = '✓';
        progressStep.classList.add('completed');
        progressStep.classList.remove('active');
        
        // 다음 스텝 활성화
        if (stepNumber < 4) {
            setTimeout(() => {
                this.activateStep(stepNumber + 1);
            }, 500);
        }
    }
    
    static updateProgress(elementId, percentage) {
        const progressBar = document.getElementById(elementId);
        progressBar.style.width = `${percentage}%`;
    }
    
    static showStepMessage(stepNumber, message, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `status-message status-${type}`;
        messageDiv.textContent = message;
        
        const messagesContainer = document.getElementById(`step${stepNumber}Messages`);
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        setTimeout(() => {
            if (messageDiv.parentNode) {
                messageDiv.remove();
            }
        }, 5000);
    }
    
    // 현재 처리 중인 파일 표시 관련 메서드들 (단순화)
    static showCurrentFile(fileName, status = '처리 중...') {
        const indicator = document.getElementById('currentProcessingFile');
        const fileNameEl = document.getElementById('currentFileName');
        const progressEl = document.getElementById('currentFileProgress');
        
        if (!indicator || !fileNameEl || !progressEl) {
            console.error('현재 파일 표시 요소를 찾을 수 없습니다.');
            return;
        }
        
        console.log(`📄 현재 파일: ${fileName}`);
        
        indicator.style.display = 'flex';
        indicator.classList.remove('completed');
        fileNameEl.textContent = fileName;
        progressEl.textContent = status;
    }
    
    static updateCurrentFileStatus(status) {
        const progressEl = document.getElementById('currentFileProgress');
        if (progressEl) {
            progressEl.textContent = status;
        }
    }
    
    static completeCurrentFile() {
        const indicator = document.getElementById('currentProcessingFile');
        const progressEl = document.getElementById('currentFileProgress');
        
        if (!indicator || !progressEl) return;
        
        indicator.classList.add('completed');
        progressEl.textContent = '완료!';
        
        setTimeout(() => {
            if (progressEl.textContent === '완료!') {
                progressEl.textContent = '대기 중...';
            }
        }, 1000);
    }
    
    static hideCurrentFile() {
        const indicator = document.getElementById('currentProcessingFile');
        if (indicator) {
            console.log('🚫 파일 표시 숨김');
            indicator.style.display = 'none';
        }
    }
}

// OCR 로그 컨트롤러 - 웹에서는 사용하지 않음
class OCRLogController {
    static show() {
        // 웹에서는 로그를 표시하지 않음
        return;
    }
    
    static hide() {
        // 웹에서는 로그를 표시하지 않음  
        return;
    }
    
    static appendLog(message) {
        // 웹에서는 로그를 표시하지 않음
        return;
    }
    
    static appendNewLog(message) {
        // 웹에서는 로그를 표시하지 않음
        return;
    }
    
    static clearLog() {
        // 웹에서는 로그를 표시하지 않음
        return;
    }
    
    static setLogContent(content) {
        // 웹에서는 로그를 표시하지 않음
        return;
    }
}

// 리스트 표시 유틸리티 함수
function createSummaryList(items, maxShow = 20, itemRenderer) {
    if (!items || items.length === 0) {
        return '<div class="no-items">항목이 없습니다.</div>';
    }
    
    const showItems = items.slice(0, maxShow);
    const remainingCount = items.length - maxShow;
    
    let html = showItems.map(itemRenderer).join('');
    
    if (remainingCount > 0) {
        html += `<div class="remaining-items">그외 ${remainingCount}개 파일...</div>`;
    }
    
    return html;
}

// 데이터 표시 함수들
function displayScannedFiles(result) {
    const folderInfo = document.getElementById('folderInfo');
    const filesList = document.getElementById('scannedFiles');
    
    // 폴더 정보 업데이트
    folderInfo.innerHTML = `
        📁 <strong>${result.folder}</strong><br>
        📄 파일 수: ${result.count}개<br>
        💾 총 크기: ${(result.total_size / 1024 / 1024).toFixed(2)} MB
    `;
    folderInfo.className = result.count > 0 ? 'folder-info' : 'folder-info empty';

    // 파일 목록 표시 (최대 20개)
    if (result.count > 0) {
        filesList.innerHTML = '';
        filesList.style.display = 'block';

        const maxShow = 20;
        const showFiles = result.files.slice(0, maxShow);
        const remainingCount = result.count - maxShow;

        showFiles.forEach((file, index) => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                <span>${index + 1}. ${file.filename}</span>
                <span>${(file.size / 1024 / 1024).toFixed(2)} MB</span>
            `;
            filesList.appendChild(fileItem);
        });

        if (remainingCount > 0) {
            const remainingItem = document.createElement('div');
            remainingItem.className = 'file-item remaining-files';
            remainingItem.innerHTML = `<span>그외 ${remainingCount}개 파일...</span>`;
            filesList.appendChild(remainingItem);
        }
    }
}

function displayResults() {
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.style.display = 'block';
    
    // 마스킹된 파일 목록 (최대 20개)
    const maskedList = document.getElementById('maskedFilesList');
    if (maskedFiles.length > 0) {
        maskedList.innerHTML = createSummaryList(
            maskedFiles, 
            20,
            (file, index) => `<div class="file-item">${index + 1}. ${file.masked_name} (${(file.size / 1024 / 1024).toFixed(2)} MB)</div>`
        );
    } else {
        maskedList.innerHTML = '<div class="file-item">마스킹된 파일 정보를 불러오는 중...</div>';
    }
    
    // 개인정보 테이블 - 앞 4글자 코드로 변경
    const personalTable = document.getElementById('personalInfoTable');
    const maxPersonalShow = 20;
    const showPersonalData = personalInfoData.slice(0, maxPersonalShow);
    const remainingPersonalCount = personalInfoData.length - maxPersonalShow;
    
    personalTable.innerHTML = `
        <table class="preview-table">
            <thead>
                <tr>
                    <th>순서</th>
                    <th>코드 (앞 4글자)</th>
                    <th>원본 파일명</th>
                </tr>
            </thead>
            <tbody>
                ${showPersonalData.map(item => `
                    <tr>
                        <td>${item.order}</td>
                        <td><strong>${item.code}</strong></td>
                        <td style="font-size: 0.85em; color: #666;">${item.original_filename}</td>
                    </tr>
                `).join('')}
                ${remainingPersonalCount > 0 ? `
                    <tr class="remaining-row">
                        <td colspan="3" style="text-align: center; font-style: italic; color: #666;">
                            그외 ${remainingPersonalCount}개 항목...
                        </td>
                    </tr>
                ` : ''}
            </tbody>
        </table>
    `;
    
    // 파일 매핑 정보 (최대 20개)
    const mappingInfo = document.getElementById('fileMappingInfo');
    if (fileMappingData.length > 0) {
        mappingInfo.innerHTML = createSummaryList(
            fileMappingData,
            20,
            (item, index) => `<div class="file-item">${index + 1}. ${item.masked_name} ← ${item.original_name}</div>`
        );
    } else {
        mappingInfo.innerHTML = '<div class="file-item">매핑 정보를 불러오는 중...</div>';
    }
    
    // 모든 다운로드 버튼 활성화
    document.getElementById('downloadMaskedBtn').disabled = false;
    document.getElementById('downloadExcelBtn').disabled = false;
    document.getElementById('downloadMappingBtn').disabled = false;
}

// 다운로드 함수들
async function downloadMaskedFiles() {
    try {
        UIController.showStepMessage(2, '마스킹된 파일을 다운로드하는 중...', 'info');
        
        const response = await fetch(`${API_BASE_URL}/download-masked`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `다운로드 실패: ${response.status}`);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `masked_pdfs_${new Date().toISOString().split('T')[0]}.zip`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        UIController.showStepMessage(2, '마스킹된 파일이 다운로드되었습니다.', 'success');
        
    } catch (error) {
        UIController.showStepMessage(2, `다운로드 중 오류: ${error.message}`, 'error');
    }
}

function downloadExcel() {
    if (personalInfoData.length === 0) return;
    
    // 앞 4글자 코드로 엑셀 데이터 구성
    const excelData = personalInfoData.map(item => ({
        '순서': item.order,
        '코드': item.code,
        '원본파일명': item.original_filename
    }));
    
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.json_to_sheet(excelData);
    
    const colWidths = [
        { wch: 10 },  // 순서
        { wch: 15 },  // 코드
        { wch: 30 }   // 원본파일명
    ];
    ws['!cols'] = colWidths;
    
    XLSX.utils.book_append_sheet(wb, ws, '파일목록');
    
    const fileName = `파일코드목록_${new Date().toISOString().split('T')[0]}.xlsx`;
    XLSX.writeFile(wb, fileName);
    
    UIController.showStepMessage(4, '엑셀 파일이 다운로드되었습니다.', 'success');
}

function downloadMapping() {
    if (fileMappingData.length === 0) {
        UIController.showStepMessage(2, '매핑 정보가 없습니다.', 'error');
        return;
    }

    const mappingText = "번호 → 원본파일명\n" + "=".repeat(30) + "\n" +
        fileMappingData.map(item => `${item.masked_name} → ${item.original_name}`).join('\n');
    
    const blob = new Blob([mappingText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '파일매핑.txt';
    a.click();
    URL.revokeObjectURL(url);
    
    UIController.showStepMessage(2, '매핑 파일이 다운로드되었습니다.', 'success');
}