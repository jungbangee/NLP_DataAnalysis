import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function RagPage() {
  const { fileId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

  const [loading, setLoading] = useState(true)
  const [initializing, setInitializing] = useState(false)
  const [initialized, setInitialized] = useState(false)
  const [hasTranscript, setHasTranscript] = useState(true) // 회의록 존재 여부
  const [speakers, setSpeakers] = useState([])
  const [selectedSpeaker, setSelectedSpeaker] = useState(null)

  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [isSending, setIsSending] = useState(false)

  const messagesEndRef = useRef(null)

  useEffect(() => {
    console.log('RagPage - fileId from useParams:', fileId)
    console.log('RagPage - typeof fileId:', typeof fileId)
    console.log('RagPage - parseInt(fileId):', parseInt(fileId))

    if (!fileId || isNaN(parseInt(fileId))) {
      console.error('RagPage - Invalid fileId:', fileId)
      return
    }

    checkAndInitialize()
  }, [fileId])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const checkAndInitialize = async () => {
    try {
      // fileId를 정수로 변환 (URL 파라미터는 문자열)
      const numericFileId = parseInt(fileId)

      // 1. 화자 목록 조회
      try {
        const speakersResponse = await axios.get(`${API_BASE_URL}/api/v1/rag/${numericFileId}/speakers`)
        setSpeakers(speakersResponse.data.speakers || [])
      } catch (error) {
        console.error('화자 목록 조회 실패:', error.response?.data)
        // 화자 목록 조회 실패해도 계속 진행
        setSpeakers([])
      }

      // 2. RAG 초기화 상태 확인
      try {
        const statusResponse = await axios.get(`${API_BASE_URL}/api/v1/rag/${numericFileId}/status`)
        if (statusResponse.data.rag_initialized) {
          console.log('RAG 이미 초기화됨')
          setInitialized(true)
          setLoading(false)
          return
        }
      } catch (error) {
        console.log('RAG 상태 확인 실패:', error.response?.data)
      }

      // 3. 초기화되지 않았으면 초기화 시도
      setInitializing(true)
      try {
        const initResponse = await axios.post(`${API_BASE_URL}/api/v1/rag/${numericFileId}/initialize`)
        console.log('RAG 초기화 완료:', initResponse.data)
        setInitialized(true)
      } catch (error) {
        console.error('RAG 초기화 실패:', error.response?.data)
        // 회의록이 없는 경우 명확한 메시지 표시
        if (error.response?.status === 400 || error.response?.status === 404) {
          const errorDetail = error.response?.data?.detail || '알 수 없는 오류'
          if (errorDetail.includes('회의록이 아직 생성되지 않았습니다')) {
            // 회의록이 없는 경우 - 페이지는 표시하되 초기화 불가 상태로 설정
            setInitialized(false)
            setHasTranscript(false)
            setMessages([{
              type: 'error',
              content: '회의록이 아직 생성되지 않았습니다. 먼저 파일 처리를 완료해주세요.',
              timestamp: new Date().toISOString()
            }])
          } else {
            setInitialized(false)
          }
        } else {
          setInitialized(false)
        }
      }

      setInitializing(false)
      setLoading(false)
    } catch (error) {
      console.error('RAG 페이지 로딩 실패:', error)
      setLoading(false)
      setInitializing(false)
    }
  }

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isSending) return

    const userMessage = {
      type: 'user',
      content: inputMessage,
      timestamp: new Date().toISOString()
    }

    setMessages([...messages, userMessage])
    const messageToSend = inputMessage
    setInputMessage('')
    setIsSending(true)

    try {
      // fileId를 정수로 변환 (URL 파라미터는 문자열)
      const numericFileId = parseInt(fileId)

      const response = await axios.post(`${API_BASE_URL}/api/v1/rag/${numericFileId}/chat`, {
        question: messageToSend,
        speaker_filter: selectedSpeaker,
        k: 5
      })

      const aiMessage = {
        type: 'ai',
        content: response.data.answer,
        sources: response.data.sources,
        speakers: response.data.speakers,
        timestamp: new Date().toISOString()
      }

      setMessages(prev => [...prev, aiMessage])
    } catch (error) {
      console.error('메시지 전송 실패:', error)
      console.error('Error response:', error.response?.data)
      console.error('Error status:', error.response?.status)

      // detail이 배열인 경우 처리
      let errorDetail = '알 수 없는 오류'
      if (error.response?.data?.detail) {
        if (Array.isArray(error.response.data.detail)) {
          errorDetail = error.response.data.detail.map(err =>
            `${err.loc?.join('.')} - ${err.msg}`
          ).join(', ')
          console.error('Validation errors:', error.response.data.detail)
        } else {
          errorDetail = error.response.data.detail
        }
      } else if (error.message) {
        errorDetail = error.message
      }

      // 벡터 DB가 초기화되지 않은 경우 자동으로 초기화 시도
      if (error.response?.status === 400 && 
          errorDetail.includes('벡터 DB가 초기화되지 않았습니다')) {
        const numericFileId = parseInt(fileId)
        
        // 초기화 시도
        try {
          setInitializing(true)
          const initResponse = await axios.post(`${API_BASE_URL}/api/v1/rag/${numericFileId}/initialize`)
          console.log('RAG 자동 초기화 완료:', initResponse.data)
          setInitialized(true)
          
          // 초기화 후 다시 질문 전송
          const retryResponse = await axios.post(`${API_BASE_URL}/api/v1/rag/${numericFileId}/chat`, {
            question: messageToSend,
            speaker_filter: selectedSpeaker,
            k: 5
          })
          
          const aiMessage = {
            type: 'ai',
            content: retryResponse.data.answer,
            sources: retryResponse.data.sources,
            speakers: retryResponse.data.speakers,
            timestamp: new Date().toISOString()
          }
          
          setMessages(prev => [...prev, aiMessage])
          setInitializing(false)
          return
        } catch (initError) {
          console.error('RAG 초기화 실패:', initError)
          setInitializing(false)
          
          // 회의록이 없는 경우 명확한 메시지 표시
          const initErrorDetail = initError.response?.data?.detail || initError.message
          let errorMessageContent = `벡터 DB 초기화에 실패했습니다: ${initErrorDetail}`
          
          if (initErrorDetail.includes('회의록이 아직 생성되지 않았습니다')) {
            errorMessageContent = '회의록이 아직 생성되지 않았습니다. 먼저 파일 처리를 완료해주세요.'
            setHasTranscript(false)
          }
          
          const errorMessage = {
            type: 'error',
            content: errorMessageContent,
            timestamp: new Date().toISOString()
          }
          setMessages(prev => [...prev, errorMessage])
          return
        }
      }

      const errorMessage = {
        type: 'error',
        content: `답변 생성에 실패했습니다: ${errorDetail}`,
        timestamp: new Date().toISOString()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  if (loading || initializing) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-accent-blue mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-300">
            {initializing ? 'RAG 시스템 초기화 중...' : '로딩 중...'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8 h-[calc(100vh-4rem)]">
      <div className="max-w-7xl mx-auto h-full flex flex-col">
        {/* 헤더 */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">💬 회의록 RAG</h1>
              <p className="text-gray-600 dark:text-gray-300">회의 내용에 대해 자유롭게 질문하세요</p>
            </div>
            <button
              onClick={() => navigate(`/result/${location.state?.resultFileId || fileId}`)}
              className="px-4 py-2 bg-bg-secondary dark:bg-bg-secondary-dark hover:bg-bg-accent/20 text-gray-700 dark:text-gray-200 rounded-lg font-medium transition"
            >
              결과로 돌아가기
            </button>
          </div>

          {/* 화자 필터 */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">화자 필터:</label>
            <select
              value={selectedSpeaker || ''}
              onChange={(e) => setSelectedSpeaker(e.target.value || null)}
              className="px-4 py-2 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-accent-blue"
            >
              <option value="">전체</option>
              {speakers.map((speaker) => (
                <option key={speaker} value={speaker}>{speaker}</option>
              ))}
            </select>
            {selectedSpeaker && (
              <span className="text-sm text-gray-600 dark:text-gray-400">
                "{selectedSpeaker}"의 발언만 검색합니다
              </span>
            )}
          </div>
        </div>

        {/* 채팅 영역 */}
        <div className="flex-1 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl shadow-lg border border-bg-accent/30 flex flex-col overflow-hidden">
          {/* 메시지 목록 */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.length === 0 ? (
              <div className="text-center text-gray-500 dark:text-gray-400 mt-12">
                <div className="text-4xl mb-4">💬</div>
                <p className="text-lg font-medium mb-2">회의록에 대해 질문해보세요!</p>
                <div className="text-sm space-y-1">
                  <p>예시: "김민서가 어떤 의견을 제시했나요?"</p>
                  <p>예시: "프로젝트 일정에 대해 논의된 내용은?"</p>
                  <p>예시: "회의에서 가장 많이 언급된 주제는?"</p>
                </div>
              </div>
            ) : (
              messages.map((message, idx) => (
                <div
                  key={idx}
                  className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[70%] rounded-xl p-4 ${
                      message.type === 'user'
                        ? 'bg-accent-blue text-white'
                        : message.type === 'error'
                        ? 'bg-accent-red/20 text-accent-red border border-accent-red/30'
                        : 'bg-bg-secondary dark:bg-bg-secondary-dark text-gray-900 dark:text-white'
                    }`}
                  >
                    {/* 메시지 내용 */}
                    <div className="whitespace-pre-wrap break-words">{message.content}</div>

                    {/* AI 답변의 소스 표시 */}
                    {message.type === 'ai' && message.sources && message.sources.length > 0 && (
                      <div className="mt-4 pt-4 border-t border-bg-accent/30">
                        <div className="text-sm font-semibold mb-2 text-gray-700 dark:text-gray-300">
                          📚 참고한 발언:
                        </div>
                        <div className="space-y-2">
                          {message.sources.map((source, sidx) => (
                            <div
                              key={sidx}
                              className="text-sm p-2 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded border border-bg-accent/20"
                            >
                              <div className="font-medium text-accent-blue dark:text-blue-300 mb-1">
                                {source.speaker} ({formatTime(source.start_time)} - {formatTime(source.end_time)})
                              </div>
                              <div className="text-gray-600 dark:text-gray-300">{source.text}</div>
                            </div>
                          ))}
                        </div>
                        {message.speakers && message.speakers.length > 0 && (
                          <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                            언급된 화자: {message.speakers.join(', ')}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            {isSending && (
              <div className="flex justify-start">
                <div className="bg-bg-secondary dark:bg-bg-secondary-dark rounded-xl p-4 max-w-[70%]">
                  <div className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
                    <div className="animate-bounce">●</div>
                    <div className="animate-bounce delay-100">●</div>
                    <div className="animate-bounce delay-200">●</div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 입력 영역 */}
          <div className="p-4 border-t border-bg-accent/30">
            <div className="flex gap-3">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={hasTranscript ? "질문을 입력하세요..." : "회의록이 없어 질문할 수 없습니다"}
                disabled={isSending || !hasTranscript || !initialized}
                className="flex-1 px-4 py-3 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-accent-blue focus:border-transparent disabled:opacity-50"
              />
              <button
                onClick={handleSendMessage}
                disabled={!inputMessage.trim() || isSending || !hasTranscript || !initialized}
                className="px-6 py-3 bg-accent-blue hover:bg-blue-600 text-white rounded-lg font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSending ? '전송 중...' : '전송'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
