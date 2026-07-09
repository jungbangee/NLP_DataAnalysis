import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function RagView({ fileId }) {
  const [loading, setLoading] = useState(true)
  const [initializing, setInitializing] = useState(false)
  const [initialized, setInitialized] = useState(false)
  const [hasTranscript, setHasTranscript] = useState(true)
  const [speakers, setSpeakers] = useState([])
  const [selectedSpeaker, setSelectedSpeaker] = useState(null)

  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [isSending, setIsSending] = useState(false)

  const messagesEndRef = useRef(null)

  useEffect(() => {
    if (fileId) {
      checkAndInitialize()
    }
  }, [fileId])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const checkAndInitialize = async () => {
    try {
      const numericFileId = parseInt(fileId)

      // 1. 화자 목록 조회
      try {
        const speakersResponse = await axios.get(`${API_BASE_URL}/api/v1/rag/${numericFileId}/speakers`)
        setSpeakers(speakersResponse.data.speakers || [])
      } catch (error) {
        console.error('화자 목록 조회 실패:', error)
        setSpeakers([])
      }

      // 2. RAG 초기화 상태 확인
      try {
        const statusResponse = await axios.get(`${API_BASE_URL}/api/v1/rag/${numericFileId}/status`)
        if (statusResponse.data.rag_initialized) {
          setInitialized(true)
          setLoading(false)
          return
        }
      } catch (error) {
        console.log('RAG 상태 확인 실패:', error)
      }

      // 3. 초기화 시도
      setInitializing(true)
      try {
        await axios.post(`${API_BASE_URL}/api/v1/rag/${numericFileId}/initialize`)
        setInitialized(true)
      } catch (error) {
        console.error('RAG 초기화 실패:', error)
        if (error.response?.status === 400 || error.response?.status === 404) {
            const errorDetail = error.response?.data?.detail || ''
            if (errorDetail.includes('회의록이 아직 생성되지 않았습니다')) {
                setInitialized(false)
                setHasTranscript(false)
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
      console.error('RAG 로딩 실패:', error)
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
      
      // 에러 처리 및 자동 초기화 로직 (간소화)
      const errorMessage = {
        type: 'error',
        content: '답변 생성에 실패했습니다. 잠시 후 다시 시도해주세요.',
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
      <div className="flex items-center justify-center h-64 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl border border-bg-accent/30">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-blue mx-auto mb-2"></div>
          <p className="text-sm text-gray-600 dark:text-gray-300">RAG 시스템 준비 중...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl shadow-lg border border-bg-accent/30 flex flex-col h-[600px]">
      <div className="p-4 border-b border-bg-accent/30 flex justify-between items-center">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <span>💬</span> AI 질의응답 (RAG)
        </h2>
        
        {/* 화자 필터 */}
        <select
            value={selectedSpeaker || ''}
            onChange={(e) => setSelectedSpeaker(e.target.value || null)}
            className="px-3 py-1 text-sm border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-accent-blue"
        >
            <option value="">전체 화자</option>
            {speakers.map((speaker) => (
            <option key={speaker} value={speaker}>{speaker}</option>
            ))}
        </select>
      </div>

      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="text-center text-gray-500 dark:text-gray-400 mt-12">
            <p className="text-lg font-medium mb-2">회의 내용에 대해 질문해보세요!</p>
            <p className="text-sm">예: "김민서가 어떤 의견을 냈어?", "일정은 어떻게 돼?"</p>
          </div>
        ) : (
          messages.map((message, idx) => (
            <div key={idx} className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-xl p-3 ${
                message.type === 'user'
                  ? 'bg-accent-blue text-white'
                  : message.type === 'error'
                  ? 'bg-red-100 text-red-700'
                  : 'bg-bg-secondary dark:bg-bg-secondary-dark text-gray-900 dark:text-white'
              }`}>
                <div className="whitespace-pre-wrap break-words text-sm">{message.content}</div>
                {message.type === 'ai' && message.sources && (
                  <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-xs font-semibold mb-1 opacity-70">참고 발언:</p>
                    {message.sources.slice(0, 2).map((source, sidx) => (
                      <div key={sidx} className="text-xs opacity-80 mb-1">
                        <span className="font-bold">{source.speaker}</span>: {source.text.substring(0, 50)}...
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 입력 영역 */}
      <div className="p-4 border-t border-bg-accent/30">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={hasTranscript ? "질문을 입력하세요..." : "회의록이 없습니다"}
            disabled={isSending || !hasTranscript || !initialized}
            className="flex-1 px-4 py-2 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-accent-blue"
          />
          <button
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || isSending || !hasTranscript || !initialized}
            className="px-4 py-2 bg-accent-blue hover:bg-blue-600 text-white rounded-lg font-semibold transition-all disabled:opacity-50"
          >
            전송
          </button>
        </div>
      </div>
    </div>
  )
}
