import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 1800000,
});

// 요청 인터셉터 추가
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 파일 업로드
export const uploadAudioFile = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/api/v1/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress,
  });

  return response.data;
};

// 파일 상태 조회
export const getFileStatus = async (fileId) => {
  const response = await api.get(`/api/v1/files/${fileId}`);
  return response.data;
};

// 처리된 파일 목록 조회
export const getProcessedFiles = async () => {
  const response = await api.get('/api/v1/files');
  return response.data;
};

// 파일 삭제
export const deleteFile = async (fileId) => {
  const response = await api.delete(`/api/v1/files/${fileId}`);
  return response.data;
};

// 파일 처리 시작
export const startProcessing = async (fileId, whisperMode, diarizationMode) => {
  const params = new URLSearchParams();
  if (whisperMode) params.append('whisper_mode', whisperMode);
  if (diarizationMode) params.append('diarization_mode', diarizationMode);

  const response = await api.post(`/api/v1/process/${fileId}?${params.toString()}`);
  return response.data;
};

// 처리 상태 조회
export const getProcessingStatus = async (fileId) => {
  const response = await api.get(`/api/v1/status/${fileId}`);
  return response.data;
};

// 최종 결과 조회
export const getTranscript = async (fileId) => {
  const response = await api.get(`/api/v1/transcript/${fileId}`);
  return response.data;
};

// NER 결과 조회
export const getNERResult = async (fileId) => {
  const response = await api.get(`/api/v1/ner/${fileId}`);
  return response.data;
};

// 병합된 결과 조회 (STT + Diarization + NER)
export const getMergedResult = async (fileId) => {
  const response = await api.get(`/api/v1/merged/${fileId}`);
  return response.data;
};

// 화자 정보 확정 (사용자가 수정한 화자 수 및 이름, 닉네임 저장)
export const confirmSpeakerInfo = async (fileId, speakerCount, detectedNames, detectedNicknames = []) => {
  const response = await api.post('/api/v1/tagging/speaker-info/confirm', {
    file_id: fileId,
    speaker_count: speakerCount,
    detected_names: detectedNames,
    detected_nicknames: detectedNicknames
  });
  return response.data;
};

// 화자 태깅 분석 시작 (Agent 실행)
export const analyzeTagging = async (fileId) => {
  const response = await api.post(`/api/v1/tagging/analyze/${fileId}`);
  return response.data;
};

// 화자 태깅 제안 조회
export const getTaggingSuggestion = async (fileId) => {
  const response = await api.get(`/api/v1/tagging/${fileId}`);
  return response.data;
};

// 화자 태깅 확정
export const confirmTagging = async (fileId, mappings) => {
  const response = await api.post('/api/v1/tagging/confirm', {
    file_id: fileId,
    mappings: mappings
  });
  return response.data;
};

// 태깅 결과 조회
export const getTaggingResult = async (fileId) => {
  const response = await api.get(`/api/v1/tagging/${fileId}/result`);
  return response.data;
};

// ===== TODO API =====

// TODO 추출 및 저장
export const extractTodos = async (fileId, meetingDate = null) => {
  const response = await api.post(`/api/v1/todos/extract/${fileId}`, {
    meeting_date: meetingDate
  });
  return response.data;
};

// TODO 리스트 조회
export const getTodos = async (fileId) => {
  const response = await api.get(`/api/v1/todos/${fileId}`);
  return response.data;
};

// 모든 TODO 삭제
export const deleteAllTodos = async (fileId) => {
  const response = await api.delete(`/api/v1/todos/${fileId}`);
  return response.data;
};

// 특정 TODO 삭제
export const deleteTodo = async (fileId, todoId) => {
  const response = await api.delete(`/api/v1/todos/${fileId}/${todoId}`);
  return response.data;
};

// ===== 대시보드 API =====

// 대시보드 통계 조회
export const getDashboardStats = async (userId, period = 'week') => {
  const response = await api.get(`/api/v1/dashboard/stats`, {
    params: { user_id: userId, period }
  });
  return response.data;
};

// 최근 파일 목록 조회
export const getRecentFiles = async (userId, limit = 10) => {
  const response = await api.get(`/api/v1/dashboard/recent-files`, {
    params: { user_id: userId, limit }
  });
  return response.data;
};

// 처리 중인 파일 목록 조회
export const getProcessingFilesFromDashboard = async (userId) => {
  const response = await api.get(`/api/v1/dashboard/processing-files`, {
    params: { user_id: userId }
  });
  return response.data;
};

// 파일 삭제
export const deleteAudioFile = async (fileId) => {
  const response = await api.delete(`/api/v1/dashboard/files/${fileId}`);
  return response.data;
};

// ===== 효율성 분석 API =====

// 효율성 분석 트리거 (백그라운드 작업)
export const triggerEfficiencyAnalysis = async (fileId) => {
  const response = await api.post(`/api/v1/efficiency/analyze/${fileId}`);
  return response.data;
};

// 개별 회의 효율성 조회
export const getEfficiencyAnalysis = async (fileId) => {
  const response = await api.get(`/api/v1/efficiency/${fileId}`);
  return response.data;
};

// 전체 회의 효율성 요약 (대시보드용)
export const getEfficiencyOverview = async (limit = 10) => {
  const response = await api.get(`/api/v1/efficiency/overview`, {
    params: { limit }
  });
  return response.data;
};

// 특정 화자의 효율성 지표 조회
export const getSpeakerEfficiency = async (fileId, speakerLabel) => {
  const response = await api.get(`/api/v1/efficiency/${fileId}/speaker/${speakerLabel}`);
  return response.data;
};

// ===== 캘린더 API =====

// 구글 캘린더 일정 추가
export const addToCalendar = async (eventData) => {
  const response = await api.post('/api/v1/calendar/create_event', eventData);
  return response.data;
};

export default api;
