import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { startProcessing, getProcessingStatus } from '../services/api';

const ProcessingPage = () => {
  const { fileId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('처리 시작 중...');
  const [error, setError] = useState(null);
  const hasStartedProcessing = useRef(false);

  // 네비게이션 state에서 모드 정보 가져오기
  const whisperMode = location.state?.whisperMode || 'local';
  const diarizationMode = location.state?.diarizationMode || 'senko';

  // 디버깅용 로그
  useEffect(() => {
    console.log('ProcessingPage - Location state:', location.state);
    console.log('ProcessingPage - whisperMode:', whisperMode);
    console.log('ProcessingPage - diarizationMode:', diarizationMode);
  }, [location.state, whisperMode, diarizationMode]);

  useEffect(() => {
    // 이미 처리가 시작되었으면 중복 실행 방지
    if (hasStartedProcessing.current) {
      return;
    }
    hasStartedProcessing.current = true;

    let pollingInterval = null;

    const initiateProcessing = async () => {
      try {
        // 먼저 상태 확인 - 이미 처리 중이면 startProcessing 호출 안 함
        const currentStatus = await getProcessingStatus(fileId).catch(() => null);

        // 이미 처리 중이거나 완료된 경우는 startProcessing 호출 안 함
        if (!currentStatus || currentStatus.status === 'uploaded' || currentStatus.status === 'failed') {
          // 백엔드 처리 시작
          await startProcessing(fileId, whisperMode, diarizationMode);
        }

        // 상태 폴링 시작 (2초마다)
        pollingInterval = setInterval(async () => {
          try {
            const status = await getProcessingStatus(fileId);

            // 상태에 따라 진행률 및 메시지 업데이트
            if (status.status === 'preprocessing') {
              setProgress(30);
              setCurrentStep('음성 전처리 중...');
            } else if (status.status === 'stt') {
              setProgress(50);
              setCurrentStep('STT 분석 중...');
            } else if (status.status === 'diarization') {
              setProgress(70);
              setCurrentStep('화자 분리 중...');
            } else if (status.status === 'ner') {
              setProgress(80);
              setCurrentStep(status.step || '이름 및 닉네임 추출 중...');
            } else if (status.status === 'saving') {
              setProgress(90);
              setCurrentStep('결과 저장 중...');
            } else if (status.status === 'completed') {
              setProgress(100);
              setCurrentStep('완료!');
              clearInterval(pollingInterval);

              // 완료 후 화자 정보 확인 페이지로 이동
              setTimeout(() => {
                navigate(`/confirm/${fileId}`);
              }, 1000);
            } else if (status.status === 'failed') {
              setError(status.error || '처리 중 오류가 발생했습니다.');
              clearInterval(pollingInterval);
            }
          } catch (err) {
            console.error('Status polling error:', err);
            // 404 에러 처리 (파일이 없는 경우)
            if (err.response && err.response.status === 404) {
              clearInterval(pollingInterval);
              setError('파일을 찾을 수 없습니다. 대시보드로 이동합니다.');
              setTimeout(() => navigate('/'), 2000);
            }
          }
        }, 2000);

      } catch (err) {
        console.error('Processing error:', err);
        if (err.response && err.response.status === 404) {
          setError('파일을 찾을 수 없습니다. 대시보드로 이동합니다.');
          setTimeout(() => navigate('/'), 2000);
        } else {
          setError(err.response?.data?.detail || '파일 처리 중 오류가 발생했습니다.');
        }
      }
    };

    initiateProcessing();

    // 컴포넌트 언마운트 시 폴링 중지
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [fileId, navigate, whisperMode, diarizationMode]);

  return (
    <div className="p-8 flex items-center justify-center min-h-[calc(100vh-4rem)]">
      <div className="max-w-2xl w-full">
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-2xl p-12 border border-bg-accent/30">
          {/* 애니메이션 아이콘 */}
          <div className="flex justify-center mb-8">
            <div className="relative">
              <div className="w-24 h-24 bg-accent-blue rounded-full animate-pulse"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <svg
                  className="w-12 h-12 text-white animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
              </div>
            </div>
          </div>

          {/* 상태 텍스트 */}
          <div className="text-center mb-8">
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-3">
              파일 분석 중...
            </h2>
            <p className="text-gray-600 dark:text-gray-300 text-lg">
              {currentStep}
            </p>
          </div>

          {/* 선택된 모델 정보 - location.state가 있을 때만 표시 */}
          {location.state && (
            <div className="mb-8 p-4 bg-bg-secondary dark:bg-bg-secondary-dark rounded-lg border border-bg-accent/30">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-700 dark:text-gray-300 font-medium">🎙️ 화자 분리:</span>
                  <span className="ml-2 text-gray-900 dark:text-white">
                    {diarizationMode === 'senko' ? 'Senko (빠름)' : 'NeMo (정확)'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-700 dark:text-gray-300 font-medium">📝 음성 인식:</span>
                  <span className="ml-2 text-gray-900 dark:text-white">
                    {whisperMode === 'local' ? 'Local Whisper' : 'OpenAI API'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* 에러 메시지 */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          {/* 진행률 바 */}
          <div className="mb-6">
            <div className="flex justify-between text-sm text-gray-600 dark:text-gray-300 mb-2">
              <span>진행률</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-bg-secondary dark:bg-bg-secondary-dark rounded-full h-4 overflow-hidden">
              <div
                className="bg-accent-blue h-full rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* 처리 단계 */}
          <div className="space-y-3">
            {[
              { label: '음성 전처리', done: progress >= 30 },
              { label: 'STT 분석', done: progress >= 50 },
              { label: '화자 분리', done: progress >= 75 },
              { label: '결과 저장', done: progress >= 90 },
              { label: '완료', done: progress >= 100 },
            ].map((step, index) => (
              <div
                key={index}
                className={`flex items-center space-x-3 transition-all duration-300 ${step.done ? 'opacity-100' : 'opacity-40'
                  }`}
              >
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center ${step.done
                      ? 'bg-green-500'
                      : 'bg-gray-300 dark:bg-gray-600'
                    }`}
                >
                  {step.done && (
                    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                <span className="text-gray-900 dark:text-white font-medium">{step.label}</span>
              </div>
            ))}
          </div>

          {/* 안내 메시지 */}
          <div className="mt-8 p-4 bg-blue-50 dark:bg-blue-900/30 rounded-lg border border-blue-200 dark:border-blue-800">
            <p className="text-blue-700 dark:text-blue-300 text-sm text-center">
              💡 처리가 완료되면 자동으로 다음 단계로 이동합니다
            </p>
          </div>

          {/* 홈으로 가기 버튼 */}
          <div className="mt-6 text-center">
            <button
              onClick={() => navigate('/')}
              className="px-6 py-2 bg-bg-secondary dark:bg-bg-secondary-dark hover:bg-bg-accent/20 text-gray-700 dark:text-gray-200 rounded-lg font-medium transition"
            >
              홈으로 가기
            </button>
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              나중에 대시보드에서 이어서 진행할 수 있습니다
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProcessingPage;
