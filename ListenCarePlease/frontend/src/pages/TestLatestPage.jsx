import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { analyzeTagging, getTaggingSuggestion } from '../services/api'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function TestLatestPage() {
  console.log('🔵 TestLatestPage 렌더링 시작')
  
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [latestFile, setLatestFile] = useState(null)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState('')
  const [apiConnected, setApiConnected] = useState(false)

  const fetchLatestFile = async () => {
    try {
      setLoading(true)
      setError(null)
      setStatus('최신 파일 조회 중...')
      setApiConnected(false)
      
      console.log('API 호출 시도:', `${API_BASE_URL}/api/v1/files`)
      
      const response = await axios.get(`${API_BASE_URL}/api/v1/files`, {
        timeout: 5000
      })
      
      console.log('✅ API 응답 성공:', response.data)
      setApiConnected(true)
      
      if (response.data.files && response.data.files.length > 0) {
        const file = response.data.files[0]
        setLatestFile(file)
        setStatus(`✅ 최신 파일 찾음: ${file.filename}`)
      } else {
        setError('처리된 파일이 없습니다.')
        setStatus('')
      }
    } catch (err) {
      console.error('❌ 최신 파일 조회 실패:', err)
      setApiConnected(false)
      
      if (err.code === 'ECONNABORTED') {
        setError('요청 시간 초과. 백엔드 서버 확인 필요.')
      } else if (err.response) {
        setError(`서버 오류 (${err.response.status}): ${err.response?.data?.detail || '알 수 없는 오류'}`)
      } else if (err.request) {
        setError(`백엔드 서버 연결 실패. 서버가 실행 중인지 확인하세요. (${API_BASE_URL})`)
      } else {
        setError(`오류: ${err.message || '알 수 없는 오류'}`)
      }
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  const handleStartAnalysis = async () => {
    if (!latestFile) return

    try {
      setLoading(true)
      setStatus('Agent 실행 중...')
      
      const analyzeResponse = await analyzeTagging(latestFile.file_id)
      console.log('Agent 실행 시작:', analyzeResponse)
      
      setStatus('분석 진행 중...')
      
      let attempts = 0
      const maxAttempts = 60
      
      const checkResult = async () => {
        try {
          const result = await getTaggingSuggestion(latestFile.file_id)
          
          if (result.suggested_mappings && result.suggested_mappings.length > 0) {
            const hasSuggestions = result.suggested_mappings.some(
              m => m.suggested_name
            )
            
            if (hasSuggestions) {
              setStatus('분석 완료!')
              setTimeout(() => {
                navigate(`/tagging/${latestFile.file_id}`)
              }, 1000)
              return
            }
          }
          
          attempts++
          if (attempts < maxAttempts) {
            setTimeout(checkResult, 1000)
          } else {
            setError('분석 시간 초과')
            setLoading(false)
          }
        } catch (err) {
          console.error('결과 확인 실패:', err)
          attempts++
          if (attempts < maxAttempts) {
            setTimeout(checkResult, 1000)
          } else {
            setError('결과 확인 실패')
            setLoading(false)
          }
        }
      }
      
      setTimeout(checkResult, 3000)
      
    } catch (err) {
      console.error('Agent 실행 실패:', err)
      setError('Agent 실행 실패: ' + (err.response?.data?.detail || err.message))
      setLoading(false)
    }
  }

  const handleGoToTagging = () => {
    if (latestFile) {
      navigate(`/tagging/${latestFile.file_id}`)
    }
  }

  const handleGoToConfirm = () => {
    if (latestFile) {
      navigate(`/confirm/${latestFile.file_id}`)
    }
  }

  console.log('🟢 TestLatestPage 렌더링 완료, return 시작')

  return (
    <div style={{ minHeight: '100vh', padding: '2rem', backgroundColor: '#f0f4f8' }}>
      <div style={{ maxWidth: '800px', margin: '0 auto', backgroundColor: 'white', borderRadius: '1rem', padding: '2rem', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '1rem', color: '#1f2937' }}>
          🧪 최신 파일 테스트
        </h1>
        <p style={{ color: '#6b7280', marginBottom: '1.5rem' }}>
          DB에 저장된 최신 처리 파일로 Agent 테스트
        </p>
        
        <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: '0.5rem' }}>
          <h3 style={{ fontWeight: '600', marginBottom: '0.5rem' }}>📊 상태 정보</h3>
          <div style={{ fontSize: '0.875rem', fontFamily: 'monospace' }}>
            <p>로딩: <span style={{ color: loading ? '#2563eb' : '#6b7280' }}>{loading ? '진행 중' : '대기'}</span></p>
            <p>파일: <span style={{ color: latestFile ? '#16a34a' : '#6b7280' }}>{latestFile ? '있음' : '없음'}</span></p>
            <p>에러: <span style={{ color: error ? '#dc2626' : '#6b7280' }}>{error ? '있음' : '없음'}</span></p>
            <p>API 연결: <span style={{ color: apiConnected ? '#16a34a' : '#ea580c' }}>{apiConnected ? '연결됨' : '미연결'}</span></p>
            <p>API 주소: <span style={{ fontSize: '0.75rem' }}>{API_BASE_URL}</span></p>
          </div>
        </div>

        {loading && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#dbeafe', border: '1px solid #93c5fd', borderRadius: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ width: '1.5rem', height: '1.5rem', border: '2px solid #2563eb', borderTop: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
              <p style={{ color: '#1e40af' }}>{status || '로딩 중...'}</p>
            </div>
          </div>
        )}

        {error && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '0.5rem' }}>
            <p style={{ color: '#991b1b', fontWeight: '600', marginBottom: '0.5rem' }}>⚠️ 오류 발생</p>
            <p style={{ color: '#b91c1c', fontSize: '0.875rem' }}>{error}</p>
            <p style={{ color: '#dc2626', fontSize: '0.75rem', marginTop: '0.5rem' }}>
              💡 해결 방법: 백엔드 서버가 실행 중인지 확인하세요.
            </p>
          </div>
        )}

        {status && !loading && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#dbeafe', border: '1px solid #93c5fd', borderRadius: '0.5rem' }}>
            <p style={{ color: '#1e40af' }}>{status}</p>
          </div>
        )}

        {latestFile && (
          <div style={{ marginBottom: '1.5rem', padding: '1rem', backgroundColor: '#f9fafb', borderRadius: '0.5rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: '600', marginBottom: '0.75rem' }}>최신 파일 정보</h2>
            <div style={{ fontSize: '0.875rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <p><strong>파일명:</strong> {latestFile.filename}</p>
              <p><strong>File ID:</strong> {latestFile.file_id}</p>
              <p><strong>상태:</strong> {latestFile.status}</p>
              <p><strong>생성일:</strong> {new Date(latestFile.created_at).toLocaleString()}</p>
              <p><strong>STT 세그먼트:</strong> {latestFile.stt_segments}개</p>
              <p><strong>화자 분리 세그먼트:</strong> {latestFile.diarization_segments}개</p>
              <p><strong>감지된 이름:</strong> {latestFile.detected_names}개</p>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <button
            onClick={fetchLatestFile}
            disabled={loading}
            style={{
              width: '100%',
              padding: '0.75rem',
              backgroundColor: loading ? '#9ca3af' : '#4f46e5',
              color: 'white',
              fontWeight: '600',
              borderRadius: '0.5rem',
              border: 'none',
              cursor: loading ? 'not-allowed' : 'pointer'
            }}
          >
            {loading ? '⏳ 조회 중...' : '🔄 최신 파일 조회'}
          </button>

          {latestFile && (
            <>
              <button
                onClick={handleGoToConfirm}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  backgroundColor: '#9333ea',
                  color: 'white',
                  fontWeight: '600',
                  borderRadius: '0.5rem',
                  border: 'none',
                  cursor: 'pointer'
                }}
              >
                📝 화자 정보 확정 페이지로 이동
              </button>

              <button
                onClick={handleStartAnalysis}
                disabled={loading}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  backgroundColor: loading ? '#9ca3af' : '#16a34a',
                  color: 'white',
                  fontWeight: '600',
                  borderRadius: '0.5rem',
                  border: 'none',
                  cursor: loading ? 'not-allowed' : 'pointer'
                }}
              >
                {loading ? '⏳ 분석 중...' : '🤖 Agent 실행 시작'}
              </button>

              <button
                onClick={handleGoToTagging}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  backgroundColor: '#2563eb',
                  color: 'white',
                  fontWeight: '600',
                  borderRadius: '0.5rem',
                  border: 'none',
                  cursor: 'pointer'
                }}
              >
                🏷️ 태깅 페이지로 이동 (결과 확인)
              </button>
            </>
          )}
        </div>
      </div>
      
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
