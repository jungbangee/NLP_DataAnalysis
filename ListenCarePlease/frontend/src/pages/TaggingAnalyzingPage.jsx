import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { analyzeTagging, getTaggingSuggestion } from '../services/api'

export default function TaggingAnalyzingPage() {
  const { fileId } = useParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState('시작 중...')
  const [error, setError] = useState(null)
  const hasStarted = useRef(false)  // 중복 실행 방지

  useEffect(() => {
    if (hasStarted.current) return  // 이미 시작했으면 무시
    hasStarted.current = true

    const startAnalysis = async () => {
      try {
        setStatus('Agent 실행 중...')
        
        // 1. Agent 실행 시작
        const analyzeResponse = await analyzeTagging(fileId)
        console.log('Agent 실행 시작:', analyzeResponse)
        
        setStatus('분석 진행 중...')
        
        // 2. 결과가 준비될 때까지 폴링 (최대 60초)
        let attempts = 0
        const maxAttempts = 600 // 600초 (10분) - 분석 시간 제한 대폭 완화
        
        const checkResult = async () => {
          try {
            const result = await getTaggingSuggestion(fileId)
            
            // suggested_mappings가 있고 suggested_name이 있으면 완료
            if (result.suggested_mappings && result.suggested_mappings.length > 0) {
              const hasSuggestions = result.suggested_mappings.some(
                m => m.suggested_name
              )
              
              if (hasSuggestions) {
                setStatus('분석 완료!')
                setTimeout(() => {
                  navigate(`/tagging/${fileId}`)
                }, 1000)
                return
              }
            }
            
            // 아직 완료되지 않았으면 계속 체크
            attempts++
            if (attempts < maxAttempts) {
              setTimeout(checkResult, 1000)
            } else {
              setError('분석 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.')
            }
          } catch (err) {
            console.error('결과 확인 실패:', err)
            attempts++
            if (attempts < maxAttempts) {
              setTimeout(checkResult, 1000)
            } else {
              setError('결과를 확인하는 중 오류가 발생했습니다.')
            }
          }
        }
        
        // 3초 후부터 결과 체크 시작 (Agent가 시작되는 시간)
        setTimeout(checkResult, 3000)
        
      } catch (err) {
        console.error('Agent 실행 실패:', err)
        setError('Agent 실행 중 오류가 발생했습니다: ' + (err.response?.data?.detail || err.message))
      }
    }
    
    startAnalysis()
  }, [fileId, navigate])

  return (
    <div className="p-8 flex items-center justify-center min-h-[calc(100vh-4rem)]">
      <div className="max-w-2xl w-full">
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-2xl shadow-xl p-12 border border-bg-accent/30">
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
              🤖 AI가 화자를 분석하고 있습니다
            </h2>
            <p className="text-gray-600 dark:text-gray-300 text-lg">
              {status}
            </p>
            {error && (
              <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-red-800 dark:text-red-400">{error}</p>
                <button
                  onClick={() => navigate(`/tagging/${fileId}`)}
                  className="mt-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                >
                  태깅 페이지로 이동
                </button>
              </div>
            )}
          </div>

          {/* 분석 단계 */}
          <div className="space-y-3">
            {[
              { label: '대화 문맥 추출 중', emoji: '📝' },
              { label: '이름 감지 및 매칭', emoji: '👤' },
              { label: '발화 패턴 분석', emoji: '🗣️' },
              { label: '역할 추론', emoji: '👔' },
              { label: '신뢰도 계산', emoji: '📊' },
            ].map((step, index) => (
              <div
                key={index}
                className="flex items-center space-x-3 p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg animate-pulse"
                style={{ animationDelay: `${index * 0.2}s` }}
              >
                <span className="text-2xl">{step.emoji}</span>
                <span className="text-gray-700 dark:text-gray-200 font-medium">{step.label}</span>
                <div className="ml-auto">
                  <div className="w-6 h-6 border-2 border-accent-blue dark:border-blue-400 border-t-transparent rounded-full animate-spin"></div>
                </div>
              </div>
            ))}
          </div>

          {/* 안내 메시지 */}
          <div className="mt-8 p-4 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-300 text-center">
              💡 잠시만 기다려주세요. I,O.md의 멀티턴 LLM 분석이 진행됩니다.
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
  )
}
