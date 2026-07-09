import React from 'react';
import { useNavigate } from 'react-router-dom';
import FileUpload from '../components/FileUpload/FileUpload';

const UploadPage = () => {
  const navigate = useNavigate();

  const handleUploadSuccess = (result) => {
    console.log('Upload success:', result);
    // 업로드 성공 후 처리 페이지로 이동 (모드 정보 포함)
    navigate(`/processing/${result.file_id}`, {
      state: {
        whisperMode: result.whisperMode,
        diarizationMode: result.diarizationMode
      }
    });
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          파일 업로드
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          회의 녹음 파일을 업로드하고 AI가 자동으로 화자를 분리하고 태깅합니다
        </p>
      </div>

      {/* Main Content */}
      <div className="max-w-4xl mx-auto">
        <FileUpload onUploadSuccess={handleUploadSuccess} />

        {/* Features */}
        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
            <div className="text-3xl mb-3">🎯</div>
            <h3 className="text-gray-900 dark:text-white font-semibold mb-2">정확한 화자 분리</h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              AI 기술로 여러 화자를 정확하게 구분합니다
            </p>
          </div>

          <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
            <div className="text-3xl mb-3">⚡</div>
            <h3 className="text-gray-900 dark:text-white font-semibold mb-2">빠른 처리</h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              최적화된 알고리즘으로 신속하게 분석합니다
            </p>
          </div>

          <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
            <div className="text-3xl mb-3">📝</div>
            <h3 className="text-gray-900 dark:text-white font-semibold mb-2">자동 요약</h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              회의 내용을 자동으로 요약해드립니다
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UploadPage;
