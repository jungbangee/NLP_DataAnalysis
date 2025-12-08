import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const ResultPage = () => {
  const { fileId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('transcript'); // transcript, summary, subtitle

  useEffect(() => {
    fetchResult();
  }, [fileId]);

  const fetchResult = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/v1/tagging/${fileId}/result`);
      setData(response.data);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching result:', err);
      setError('결과를 불러오는 중 오류가 발생했습니다.');
      setLoading(false);
    }
  };

  const handleNewUpload = () => {
    navigate('/');
  };

  const handleDownloadTranscript = () => {
    if (!data) return;

    // 대본을 텍스트 파일로 다운로드
    const text = data.final_transcript
      .map(segment => `[${segment.start_time.toFixed(1)}s - ${segment.end_time.toFixed(1)}s] ${segment.speaker_name}:\n${segment.text}\n`)
      .join('\n');

    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcript_${fileId}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center">
        <div className="text-gray-900 text-xl">결과를 불러오는 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-red-600 text-xl mb-4">{error}</div>
          <button
            onClick={handleNewUpload}
            className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            처음으로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 py-8 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-green-500 rounded-full mb-4">
            <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-4xl font-bold text-gray-900 mb-3">
            분석 완료!
          </h1>
          <p className="text-gray-600 text-lg">
            화자 태깅이 완료되었습니다
          </p>
        </div>

        {/* 화자 매핑 요약 */}
        <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6 border border-white/20 mb-8">
          <h2 className="text-xl font-bold text-white mb-4">화자 매핑</h2>
          <div className="flex flex-wrap gap-3">
            {Object.entries(data.mappings).map(([speaker, name], index) => (
              <div
                key={speaker}
                className="flex items-center space-x-2 px-4 py-2 bg-white/5 rounded-lg border border-white/10"
              >
                <div className="w-8 h-8 bg-gradient-to-r from-primary-500 to-secondary-500 rounded-full flex items-center justify-center">
                  <span className="text-white font-bold text-xs">{index + 1}</span>
                </div>
                <span className="text-white/70">{speaker}</span>
                <span className="text-white">→</span>
                <span className="text-white font-semibold">{name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 탭 메뉴 */}
        <div className="bg-white/10 backdrop-blur-lg rounded-2xl border border-white/20 overflow-hidden">
          <div className="flex border-b border-white/10">
            <button
              onClick={() => setActiveTab('transcript')}
              className={`flex-1 px-6 py-4 font-semibold transition-colors ${
                activeTab === 'transcript'
                  ? 'bg-white/10 text-white'
                  : 'text-white/60 hover:text-white hover:bg-white/5'
              }`}
            >
              📝 전체 대본
            </button>
            <button
              onClick={() => setActiveTab('summary')}
              className={`flex-1 px-6 py-4 font-semibold transition-colors ${
                activeTab === 'summary'
                  ? 'bg-white/10 text-white'
                  : 'text-white/60 hover:text-white hover:bg-white/5'
              }`}
            >
              ✨ 요약
            </button>
            <button
              onClick={() => setActiveTab('subtitle')}
              className={`flex-1 px-6 py-4 font-semibold transition-colors ${
                activeTab === 'subtitle'
                  ? 'bg-white/10 text-white'
                  : 'text-white/60 hover:text-white hover:bg-white/5'
              }`}
            >
              🎬 자막
            </button>
          </div>

          <div className="p-8">
            {/* 전체 대본 탭 */}
            {activeTab === 'transcript' && (
              <div>
                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-2xl font-bold text-white">전체 대본</h2>
                  <button
                    onClick={handleDownloadTranscript}
                    className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition flex items-center space-x-2"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    <span>다운로드</span>
                  </button>
                </div>

                <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
                  {data.final_transcript.map((segment, index) => (
                    <div
                      key={index}
                      className="p-4 bg-white/5 rounded-lg border border-white/10 hover:bg-white/10 transition"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-primary-300 font-semibold">
                          {segment.speaker_name}
                        </span>
                        <span className="text-white/50 text-sm">
                          {segment.start_time.toFixed(1)}s - {segment.end_time.toFixed(1)}s
                        </span>
                      </div>
                      <p className="text-white/90 leading-relaxed">
                        {segment.text}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 요약 탭 (Mock) */}
            {activeTab === 'summary' && (
              <div>
                <h2 className="text-2xl font-bold text-white mb-6">회의 요약</h2>
                <div className="space-y-6">
                  <div className="p-6 bg-white/5 rounded-lg border border-white/10">
                    <h3 className="text-lg font-semibold text-white mb-3">📌 핵심 내용</h3>
                    <p className="text-white/80 leading-relaxed">
                      이 회의에서는 프로젝트 진행 상황을 공유하고, 향후 일정에 대해 논의했습니다.
                      모든 참석자가 일정대로 진행하는 것에 동의했으며, 추가적인 리소스 배분에 대해서도 이야기가 나왔습니다.
                    </p>
                  </div>

                  <div className="p-6 bg-white/5 rounded-lg border border-white/10">
                    <h3 className="text-lg font-semibold text-white mb-3">✅ 결정 사항</h3>
                    <ul className="space-y-2 text-white/80">
                      <li className="flex items-start space-x-2">
                        <span className="text-green-400">•</span>
                        <span>프로젝트 일정 유지</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-green-400">•</span>
                        <span>추가 인력 배치 검토</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-green-400">•</span>
                        <span>다음 주 중간 점검 회의 예정</span>
                      </li>
                    </ul>
                  </div>

                  <div className="p-6 bg-white/5 rounded-lg border border-white/10">
                    <h3 className="text-lg font-semibold text-white mb-3">🔔 액션 아이템</h3>
                    <ul className="space-y-2 text-white/80">
                      <li className="flex items-start space-x-2">
                        <span className="text-yellow-400">•</span>
                        <span>김팀장: 리소스 배분 계획서 작성</span>
                      </li>
                      <li className="flex items-start space-x-2">
                        <span className="text-yellow-400">•</span>
                        <span>민서: 진행 상황 보고서 준비</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* 자막 탭 (Mock) */}
            {activeTab === 'subtitle' && (
              <div>
                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-2xl font-bold text-white">자막 파일</h2>
                  <button
                    className="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition flex items-center space-x-2"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    <span>SRT 다운로드</span>
                  </button>
                </div>

                <div className="p-6 bg-white/5 rounded-lg border border-white/10">
                  <pre className="text-white/80 font-mono text-sm whitespace-pre-wrap">
{`1
00:00:00,500 --> 00:00:03,200
${data.final_transcript[0]?.speaker_name}: ${data.final_transcript[0]?.text}

2
00:00:03,500 --> 00:00:06,800
${data.final_transcript[1]?.speaker_name}: ${data.final_transcript[1]?.text}

3
00:00:07,000 --> 00:00:10,500
${data.final_transcript[2]?.speaker_name}: ${data.final_transcript[2]?.text}`}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 액션 버튼 */}
        <div className="mt-8 flex justify-center space-x-4">
          <button
            onClick={handleNewUpload}
            className="px-8 py-3 bg-gradient-to-r from-primary-500 to-secondary-500 text-white font-semibold rounded-lg
                     hover:from-primary-600 hover:to-secondary-600 transform hover:scale-105 transition-all duration-200
                     shadow-lg hover:shadow-xl"
          >
            새 파일 업로드
          </button>
        </div>
      </div>
    </div>
  );
};

export default ResultPage;
