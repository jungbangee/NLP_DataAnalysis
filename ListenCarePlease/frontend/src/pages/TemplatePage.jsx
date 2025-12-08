import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const MEETING_TYPES = [
  { code: 'a', name: '정보 전달 (Informing)', desc: '공지사항, 변화, Q&A 요약' },
  { code: 'b', name: '점검 및 정렬 (Checking & Syncing)', desc: '진행상황, Blocker, Follow-up' },
  { code: 'c', name: '문제 해결 (Problem Solving)', desc: '문제 정의, 아이디어, 가설 검토' },
  { code: 'd', name: '계획 및 설계 (Plan & Design)', desc: '목표, 산출물, 일정, WBS' },
  { code: 'e', name: '결정 및 합의 (Decide & Commit)', desc: '공식 결정, 근거, 실행 계획' },
  { code: 'f', name: '관계 및 회고 (Relationship & Review)', desc: '피드백, 감정 공유, 회고' },
]

export default function TemplatePage() {
  const { fileId } = useParams()
  const navigate = useNavigate()
  
  const [selectedType, setSelectedType] = useState('d')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleGenerate = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    
    try {
      const response = await axios.post(`${API_BASE_URL}/api/v1/template/${fileId}/generate`, {
        meeting_type: selectedType
      })
      
      if (response.data.status === 'success') {
        setResult(response.data.data)
      } else {
        setError('생성 실패: ' + (response.data.message || '알 수 없는 오류'))
      }
    } catch (err) {
      console.error(err)
      setError('API 호출 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `template_fitting_${fileId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            회의록 템플릿 피팅
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            회의 유형에 맞춰 구조화된 회의록을 자동 생성합니다.
          </p>
        </div>
        <button
          onClick={() => navigate(-1)}
          className="px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg hover:opacity-80 transition-all"
        >
          뒤로 가기
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* 설정 패널 */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark p-6 rounded-xl border border-bg-accent/30 shadow-lg">
            <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">회의 유형 선택</h2>
            <div className="space-y-3">
              {MEETING_TYPES.map((type) => (
                <div
                  key={type.code}
                  onClick={() => setSelectedType(type.code)}
                  className={`p-4 rounded-lg border cursor-pointer transition-all ${
                    selectedType === type.code
                      ? 'border-accent-blue bg-blue-50 dark:bg-blue-900/20 ring-1 ring-accent-blue'
                      : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`font-bold ${selectedType === type.code ? 'text-accent-blue' : 'text-gray-900 dark:text-white'}`}>
                      {type.name}
                    </span>
                    {selectedType === type.code && <span className="text-accent-blue">✓</span>}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{type.desc}</p>
                </div>
              ))}
            </div>

            <button
              onClick={handleGenerate}
              disabled={loading}
              className={`w-full mt-6 py-3 rounded-xl font-bold text-white transition-all ${
                loading
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-accent-blue hover:bg-blue-600 shadow-md hover:shadow-lg'
              }`}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  생성 중...
                </span>
              ) : (
                '템플릿 생성하기'
              )}
            </button>
          </div>
        </div>

        {/* 결과 패널 */}
        <div className="lg:col-span-2">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-200 p-4 rounded-xl mb-6">
              {error}
            </div>
          )}

          {result ? (
            <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl border border-bg-accent/30 shadow-lg overflow-hidden">
              <div className="p-4 border-b border-bg-accent/30 flex justify-between items-center bg-bg-secondary dark:bg-bg-secondary-dark">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">생성 결과</h2>
                <button
                  onClick={handleDownload}
                  className="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  JSON 다운로드
                </button>
              </div>
              
              <div className="p-6 space-y-6 max-h-[800px] overflow-y-auto">
                {/* 요약 섹션 */}
                <div className="space-y-4">
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white border-b pb-2">요약</h3>
                    <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
                        {result.summary?.overall}
                    </p>
                    <ul className="list-disc list-inside space-y-1 text-gray-700 dark:text-gray-300">
                        {result.summary?.key_takeaways?.map((item, idx) => (
                            <li key={idx}>{item}</li>
                        ))}
                    </ul>
                </div>

                {/* 섹션별 내용 */}
                {result.sections?.map((section, idx) => (
                    <div key={idx} className="space-y-4 pt-6 border-t border-gray-200 dark:border-gray-700">
                        <h3 className="text-lg font-bold text-accent-blue">섹션 {idx + 1}</h3>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <h4 className="font-semibold mb-2 text-gray-900 dark:text-white">논의 내용</h4>
                                <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                                    {section.discussion_summary}
                                </p>
                            </div>
                            <div>
                                <h4 className="font-semibold mb-2 text-gray-900 dark:text-white">결정 사항</h4>
                                <ul className="list-disc list-inside text-sm text-gray-600 dark:text-gray-400 space-y-1">
                                    {section.decisions?.map((d, i) => <li key={i}>{d}</li>)}
                                </ul>
                            </div>
                        </div>

                        {section.action_items?.length > 0 && (
                            <div className="bg-blue-50 dark:bg-blue-900/10 p-4 rounded-lg">
                                <h4 className="font-semibold mb-2 text-blue-900 dark:text-blue-100">Action Items</h4>
                                <div className="space-y-2">
                                    {section.action_items.map((item, i) => (
                                        <div key={i} className="flex items-start gap-2 text-sm">
                                            <span className="font-bold text-blue-700 dark:text-blue-300 min-w-[60px]">
                                                {item.owner || '담당자 미정'}
                                            </span>
                                            <span className="text-blue-800 dark:text-blue-200 flex-1">
                                                {item.task}
                                            </span>
                                            {item.due && (
                                                <span className="text-blue-600 dark:text-blue-400 text-xs bg-blue-100 dark:bg-blue-900/30 px-2 py-0.5 rounded">
                                                    ~{item.due}
                                                </span>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                ))}

                {/* Raw JSON 보기 (접기/펼치기 가능하게 하면 좋지만 일단은 맨 아래에) */}
                <div className="mt-8 pt-8 border-t border-gray-200 dark:border-gray-700">
                    <details>
                        <summary className="cursor-pointer font-medium text-gray-500 hover:text-gray-700">Raw JSON 보기</summary>
                        <pre className="mt-4 bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-xs">
                            {JSON.stringify(result, null, 2)}
                        </pre>
                    </details>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-gray-400 space-y-4 min-h-[400px] border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
              <span className="text-6xl">📋</span>
              <p className="text-lg">왼쪽에서 유형을 선택하고 생성 버튼을 눌러주세요</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
