import React, { useState, useRef } from 'react';
import { uploadAudioFile } from '../../services/api';

const FileUpload = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [whisperMode, setWhisperMode] = useState('local'); // 'local' or 'api'
  const [diarizationMode, setDiarizationMode] = useState('senko'); // 'senko' or 'nemo'
  const fileInputRef = useRef(null);

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleFileInputChange = (e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleFileSelect = (file) => {
    // 파일 형식 검증
    const allowedTypes = ['audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/m4a', 'audio/wav', 'audio/ogg', 'audio/flac'];
    const allowedExtensions = ['.mp3', '.m4a', '.wav', '.ogg', '.flac'];

    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();

    if (!allowedTypes.includes(file.type) && !allowedExtensions.includes(fileExtension)) {
      setError('지원하지 않는 파일 형식입니다. (MP3, M4A, WAV, OGG, FLAC만 가능)');
      return;
    }

    // 파일 크기 검증 (100MB)
    const maxSize = 100 * 1024 * 1024;
    if (file.size > maxSize) {
      setError('파일 크기는 100MB를 초과할 수 없습니다.');
      return;
    }

    setSelectedFile(file);
    setError(null);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setError(null);
    setUploadProgress(0);

    try {
      const result = await uploadAudioFile(selectedFile, (progressEvent) => {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setUploadProgress(progress);
      });

      // 업로드 성공 - 모드 정보 포함
      console.log('FileUpload - Upload success');
      console.log('FileUpload - whisperMode:', whisperMode);
      console.log('FileUpload - diarizationMode:', diarizationMode);
      console.log('FileUpload - result:', result);

      if (onUploadSuccess) {
        const uploadData = {
          ...result,
          whisperMode,
          diarizationMode
        };
        console.log('FileUpload - Calling onUploadSuccess with:', uploadData);
        onUploadSuccess(uploadData);
      }
    } catch (err) {
      console.error('Upload error:', err);
      setError(err.response?.data?.detail || '파일 업로드 중 오류가 발생했습니다.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setUploadProgress(0);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto">
      {!selectedFile ? (
        <div
          className={`
            relative border-4 border-dashed rounded-2xl p-12 text-center cursor-pointer
            transition-all duration-300 ease-in-out
            ${isDragging
              ? 'border-accent-blue bg-blue-50 dark:bg-blue-900/20 scale-105'
              : 'border-bg-accent bg-bg-tertiary dark:bg-bg-tertiary-dark hover:border-accent-blue'
            }
          `}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".mp3,.m4a,.wav,.ogg,.flac,audio/*"
            onChange={handleFileInputChange}
            className="hidden"
          />

          <div className="flex flex-col items-center space-y-4">
            <svg
              className="w-20 h-20 text-accent-blue"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>

            <div>
              <p className="text-xl font-semibold text-gray-700 dark:text-gray-200 mb-2">
                오디오 파일을 드래그하거나 클릭하세요
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                MP3, M4A, WAV, OGG, FLAC (최대 100MB)
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-2xl p-8 shadow-lg border border-bg-accent/30">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-4">
              <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center">
                <svg
                  className="w-6 h-6 text-accent-blue"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
                  />
                </svg>
              </div>
              <div>
                <p className="font-semibold text-gray-900 dark:text-white">{selectedFile.name}</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            </div>
            {!isUploading && (
              <button
                onClick={handleReset}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* 모델 선택 옵션 */}
          <div className="space-y-6 mb-6">
            {/* 화자 분리 모델 선택 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                🎙️ 화자 분리 모델
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setDiarizationMode('senko')}
                  className={`p-4 rounded-lg border-2 transition-all ${
                    diarizationMode === 'senko'
                      ? 'border-accent-blue bg-blue-50 dark:bg-blue-900/20'
                      : 'border-bg-accent/30 hover:border-accent-blue'
                  }`}
                >
                  <div className="text-left">
                    <div className="font-semibold text-gray-900 dark:text-white">Senko</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">⚡ 빠름, 간단</div>
                  </div>
                </button>
                <button
                  onClick={() => setDiarizationMode('nemo')}
                  className={`p-4 rounded-lg border-2 transition-all ${
                    diarizationMode === 'nemo'
                      ? 'border-accent-blue bg-blue-50 dark:bg-blue-900/20'
                      : 'border-bg-accent/30 hover:border-accent-blue'
                  }`}
                >
                  <div className="text-left">
                    <div className="font-semibold text-gray-900 dark:text-white">NeMo</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">🎯 정확, 세밀</div>
                  </div>
                </button>
              </div>
            </div>

            {/* Whisper 모드 선택 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                📝 음성 인식 모델
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => setWhisperMode('local')}
                  className={`p-4 rounded-lg border-2 transition-all ${
                    whisperMode === 'local'
                      ? 'border-accent-blue bg-blue-50 dark:bg-blue-900/20'
                      : 'border-bg-accent/30 hover:border-accent-blue'
                  }`}
                >
                  <div className="text-left">
                    <div className="font-semibold text-gray-900 dark:text-white">Local</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">💻 로컬 Whisper</div>
                  </div>
                </button>
                <button
                  onClick={() => setWhisperMode('api')}
                  className={`p-4 rounded-lg border-2 transition-all ${
                    whisperMode === 'api'
                      ? 'border-accent-blue bg-blue-50 dark:bg-blue-900/20'
                      : 'border-bg-accent/30 hover:border-accent-blue'
                  }`}
                >
                  <div className="text-left">
                    <div className="font-semibold text-gray-900 dark:text-white">API</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">☁️ OpenAI API</div>
                  </div>
                </button>
              </div>
            </div>
          </div>

          {isUploading && (
            <div className="mb-6">
              <div className="flex justify-between text-sm text-gray-600 dark:text-gray-300 mb-2">
                <span>업로드 중...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 overflow-hidden">
                <div
                  className="bg-accent-blue h-full rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          {!isUploading && (
            <button
              onClick={handleUpload}
              className="w-full bg-accent-blue text-white font-semibold py-3 px-6 rounded-lg
                       hover:bg-blue-600 transform hover:scale-105 transition-all duration-200
                       shadow-lg hover:shadow-xl"
            >
              분석 시작하기
            </button>
          )}
        </div>
      )}

      {error && !selectedFile && (
        <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
};

export default FileUpload;
