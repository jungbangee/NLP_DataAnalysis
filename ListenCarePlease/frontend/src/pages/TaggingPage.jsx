import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const TaggingPage = () => {
  const { fileId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [mappings, setMappings] = useState({});
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchTaggingData();
  }, [fileId]);

  const fetchTaggingData = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/v1/tagging/${fileId}`);
      setData(response.data);

      // 초기 매핑 설정 (시스템 제안 값으로) - Enhanced 필드 포함
      const initialMappings = {};
      response.data.suggested_mappings.forEach(mapping => {
        initialMappings[mapping.speaker_label] = {
          suggested_name: mapping.suggested_name,
          suggested_role: mapping.suggested_role || null,
          final_name: mapping.suggested_name || '',
          name_confidence: mapping.name_confidence || null,
          role_confidence: mapping.role_confidence || null,
          name_mentions: mapping.name_mentions || 0,
          conflict_detected: mapping.conflict_detected || false,
          needs_manual_review: mapping.needs_manual_review || false
        };
      });
      setMappings(initialMappings);

      setLoading(false);
    } catch (err) {
      console.error('Error fetching tagging data:', err);
      setError('태깅 데이터를 불러오는 중 오류가 발생했습니다.');
      setLoading(false);
    }
  };

  const handleMappingChange = (speakerLabel, value) => {
    setMappings(prev => ({
      ...prev,
      [speakerLabel]: {
        ...prev[speakerLabel],
        final_name: value
      }
    }));
  };

  const handleSubmit = async () => {
    // 모든 화자에 이름이 입력되었는지 확인
    const emptyMappings = Object.entries(mappings).filter(([_, mapping]) => !mapping.final_name.trim());
    if (emptyMappings.length > 0) {
      alert('모든 화자의 이름을 입력해주세요.');
      return;
    }

    setSubmitting(true);

    try {
      const payload = {
        file_id: fileId,
        mappings: Object.entries(mappings).map(([speaker_label, mapping]) => ({
          speaker_label,
          final_name: mapping.final_name.trim()
        }))
      };

      await axios.post(`${API_BASE_URL}/api/v1/tagging/confirm`, payload);

      // 완료 후 결과 페이지로 이동
      navigate(`/result/${fileId}`);
    } catch (err) {
      console.error('Error confirming tagging:', err);
      alert('태깅 저장 중 오류가 발생했습니다.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center">
        <div className="text-gray-900 text-xl">로딩 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center">
        <div className="text-red-600 text-xl">{error}</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-3">
            화자 태깅
          </h1>
          <p className="text-gray-600 text-lg">
            감지된 화자에게 이름을 지정해주세요
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* 왼쪽: 태깅 영역 */}
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 border border-white/20">
            <h2 className="text-2xl font-bold text-white mb-6">
              화자 이름 지정
            </h2>

            {/* 감지된 이름 목록 */}
            {data.detected_names && data.detected_names.length > 0 && (
              <div className="mb-6 p-4 bg-white/5 rounded-lg border border-white/10">
                <p className="text-white/70 text-sm mb-2">💡 대화에서 감지된 이름:</p>
                <div className="flex flex-wrap gap-2">
                  {data.detected_names.map((name, index) => (
                    <span
                      key={index}
                      className="px-3 py-1 bg-primary-500/30 text-white rounded-full text-sm border border-primary-400/50"
                    >
                      {name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 화자 매핑 입력 */}
            <div className="space-y-4">
              {data.suggested_mappings.map((mapping, index) => {
                const currentMapping = mappings[mapping.speaker_label];
                const hasConflict = currentMapping?.conflict_detected;
                const needsReview = currentMapping?.needs_manual_review;

                return (
                <div
                  key={mapping.speaker_label}
                  className={`p-4 rounded-lg border-2 ${
                    hasConflict
                      ? 'bg-red-500/10 border-red-500/30'
                      : 'bg-white/5 border-white/10'
                  }`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center space-x-3">
                      <div className="w-10 h-10 bg-gradient-to-r from-primary-500 to-secondary-500 rounded-full flex items-center justify-center">
                        <span className="text-white font-bold text-sm">
                          {index + 1}
                        </span>
                      </div>
                      <span className="text-white font-medium">
                        {mapping.speaker_label}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {needsReview && (
                        <span className="text-xs text-red-300 bg-red-500/30 px-2 py-1 rounded font-semibold">
                          ⚠️ 확인 필요
                        </span>
                      )}
                      {currentMapping?.suggested_name && (
                        <span className="text-xs text-primary-300 bg-primary-500/20 px-2 py-1 rounded">
                          제안: {currentMapping.suggested_name}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 신뢰도 및 역할 정보 */}
                  {(currentMapping?.name_confidence || currentMapping?.suggested_role) && (
                    <div className="mb-3 p-3 bg-white/5 rounded-lg space-y-2">
                      {currentMapping.suggested_name && currentMapping.name_confidence && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-white/70">💡 이름 신뢰도:</span>
                          <span className="text-primary-300 font-semibold">
                            {Math.round(currentMapping.name_confidence * 100)}%
                            {currentMapping.name_mentions > 0 && (
                              <span className="text-white/50 ml-2">
                                ({currentMapping.name_mentions}회 언급)
                              </span>
                            )}
                          </span>
                        </div>
                      )}
                      {currentMapping.suggested_role && (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-white/70">👔 추정 역할:</span>
                          <span className="text-purple-300 font-semibold">
                            {currentMapping.suggested_role}
                            {currentMapping.role_confidence && (
                              <span className="text-white/50 ml-2">
                                ({Math.round(currentMapping.role_confidence * 100)}%)
                              </span>
                            )}
                          </span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 모순 경고 */}
                  {hasConflict && (
                    <div className="mb-3 p-3 bg-red-500/20 border border-red-500/30 rounded-lg">
                      <p className="text-sm text-red-300">
                        ⚠️ 대화 문맥에서 모순이 발견되었습니다. 수동으로 확인해주세요.
                      </p>
                    </div>
                  )}

                  <div>
                    <label className="block text-white/70 text-sm mb-2">
                      이름 입력
                    </label>
                    <div className="flex space-x-2">
                      <input
                        type="text"
                        value={currentMapping?.final_name || ''}
                        onChange={(e) => handleMappingChange(mapping.speaker_label, e.target.value)}
                        placeholder="이름을 입력하세요"
                        className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/40 focus:outline-none focus:border-primary-400"
                      />
                      {/* 감지된 이름 빠른 선택 */}
                      {data.detected_names && data.detected_names.length > 0 && (
                        <select
                          onChange={(e) => {
                            if (e.target.value) {
                              handleMappingChange(mapping.speaker_label, e.target.value);
                            }
                          }}
                          className="px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:border-primary-400"
                        >
                          <option value="">이름 선택</option>
                          {data.detected_names.map((name, idx) => (
                            <option key={idx} value={name}>{name}</option>
                          ))}
                        </select>
                      )}
                      {/* 감지된 닉네임 빠른 선택 */}
                      {data.detected_nicknames && data.detected_nicknames.length > 0 && (
                        <select
                          onChange={(e) => {
                            if (e.target.value) {
                              handleMappingChange(mapping.speaker_label, e.target.value);
                            }
                          }}
                          className="px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:border-primary-400"
                        >
                          <option value="">닉네임 선택</option>
                          {data.detected_nicknames.map((nickname, idx) => (
                            <option key={idx} value={nickname}>{nickname}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  </div>
                </div>
                );
              })}
            </div>

            {/* 제출 버튼 */}
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="w-full mt-6 bg-gradient-to-r from-primary-500 to-secondary-500 text-white font-semibold py-3 px-6 rounded-lg
                       hover:from-primary-600 hover:to-secondary-600 transform hover:scale-105 transition-all duration-200
                       shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
            >
              {submitting ? '저장 중...' : '태깅 완료하고 결과 보기'}
            </button>
          </div>

          {/* 오른쪽: 참고용 대본 */}
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 border border-white/20">
            <h2 className="text-2xl font-bold text-white mb-6">
              참고용 대본
            </h2>

            <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
              {data.sample_transcript.map((segment, index) => (
                <div
                  key={index}
                  className="p-4 bg-white/5 rounded-lg border border-white/10"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-primary-300 font-medium">
                      {segment.speaker_label}
                      {mappings[segment.speaker_label]?.final_name && (
                        <span className="text-white ml-2">
                          ({mappings[segment.speaker_label].final_name})
                        </span>
                      )}
                    </span>
                    <span className="text-white/50 text-xs">
                      {segment.start_time.toFixed(1)}s - {segment.end_time.toFixed(1)}s
                    </span>
                  </div>
                  <p className="text-white/90">
                    {segment.text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TaggingPage;
