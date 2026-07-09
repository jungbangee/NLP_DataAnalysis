import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Doughnut, Bar } from 'react-chartjs-2'
import { Chart as ChartJS, ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement } from 'chart.js'

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement)

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function ResultPageNew() {
  const { fileId } = useParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [efficiency, setEfficiency] = useState(null)
  const [sections, setSections] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [activeSection, setActiveSection] = useState(null)
  const [keywords, setKeywords] = useState([])
  const [activeKeyword, setActiveKeyword] = useState(null)
  const [showMeetingMinutesMenu, setShowMeetingMinutesMenu] = useState(false)
  const [showDownloadMenu, setShowDownloadMenu] = useState(false)

  useEffect(() => {
    fetchResult()
  }, [fileId])

  // 효율성 분석 결과 폴링
  // 효율성 분석 결과 폴링 (재귀적 setTimeout 사용)
  useEffect(() => {
    if (efficiency) return

    let timeoutId = null;

    const pollEfficiency = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/api/v1/efficiency/${fileId}`)
        if (response.data) {
          setEfficiency(response.data)
          // 성공하면 더 이상 폴링하지 않음
        }
      } catch (error) {
        // 404는 아직 분석 중일 수 있으므로 무시하고 재시도
        if (error.response?.status === 404) {
          timeoutId = setTimeout(pollEfficiency, 3000)
        } else {
          console.error('Efficiency polling error:', error)
          // 다른 에러(네트워크 등)가 나도 잠시 후 재시도 (안정성 확보)
          timeoutId = setTimeout(pollEfficiency, 5000)
        }
      }
    }

    pollEfficiency()

    return () => {
      if (timeoutId) clearTimeout(timeoutId)
    }
  }, [fileId, efficiency])

  const fetchResult = async () => {
    try {
      setEfficiency(null) // 초기화
      // 1. 회의록 결과 조회
      const response = await axios.get(`${API_BASE_URL}/api/v1/tagging/${fileId}/result`)
      setData(response.data)

      // 2. 효율성 분석 결과 조회 (초기 시도)
      try {
        const effResponse = await axios.get(`${API_BASE_URL}/api/v1/efficiency/${fileId}`)
        setEfficiency(effResponse.data)
      } catch (effError) {
        console.log('효율성 분석 결과 없음 (폴링 시작):', effError)
      }

      // 3. 구간 분석 결과 조회 (자동 로드)
      if (response.data?.audio_file_id) {
        handleAnalyzeSections(response.data.audio_file_id)

        // 4. 핵심 용어 조회
        try {
          console.log('Fetching keywords for audio_file_id:', response.data.audio_file_id);
          const kwResponse = await axios.get(`${API_BASE_URL}/api/v1/keyword/${response.data.audio_file_id}`)
          console.log('Keywords response:', kwResponse.data);
          setKeywords(kwResponse.data)
        } catch (kwError) {
          console.log('핵심 용어 조회 실패:', kwError)
        }

      } else {
        handleAnalyzeSections()
      }

      setLoading(false)
    } catch (error) {
      console.error('결과 조회 실패:', error)
      if (error.response?.status === 404) {
        navigate(`/tagging/${fileId}`)
      } else {
        setLoading(false)
      }
    }
  }

  const handleAnalyzeSections = async (explicitId) => {
    // explicitId가 이벤트 객체이거나 유효하지 않으면 무시
    const validExplicitId = (typeof explicitId === 'number' || (typeof explicitId === 'string' && !isNaN(explicitId))) ? explicitId : null
    const targetId = validExplicitId || data?.audio_file_id

    console.log('DEBUG CHECK: handleAnalyzeSections targetId:', targetId, 'explicitId:', explicitId, 'data.id:', data?.audio_file_id)

    if (!targetId || isNaN(targetId)) {
      console.error('유효한 audio_file_id가 없습니다. UUID는 사용할 수 없습니다:', fileId)
      // 데이터가 아직 로드되지 않았거나 ID가 없는 경우 중단
      if (!data) return
      alert('오디오 파일 ID를 찾을 수 없습니다.')
      return
    }

    if (analyzing) return
    setAnalyzing(true)
    try {
      // 기본값 'd' (Plan & Design)으로 요청
      const response = await axios.post(`${API_BASE_URL}/api/v1/template/${targetId}/generate`, {
        meeting_type: 'd'
      })
      if (response.data.status === 'success') {
        setSections(response.data.data.sections)
      }
    } catch (error) {
      console.error('구간 분석 실패:', error)
      let errorMsg = error.response?.data?.message || error.message || '알 수 없는 오류'
      if (error.response?.status === 422 && error.response?.data?.detail) {
        errorMsg = JSON.stringify(error.response.data.detail)
      }
      alert(`구간 분석에 실패했습니다: ${errorMsg}`)
    } finally {
      setAnalyzing(false)
    }
  }

  // 일반 녹취록 다운로드 (DOCX, XLSX, PDF)
  const handleDownload = async (format) => {
    if (!data?.audio_file_id) return
    try {
      const response = await axios.get(`${API_BASE_URL}/api/v1/export/${data.audio_file_id}/${format}`, {
        responseType: 'blob'
      })

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url

      // 파일명 추출
      const contentDisposition = response.headers['content-disposition']
      let fileName = `녹취록_${data.audio_file_id}.${format}`
      if (contentDisposition) {
        const fileNameMatch = contentDisposition.match(/filename\*=UTF-8''(.+)/)
        if (fileNameMatch) {
          fileName = decodeURIComponent(fileNameMatch[1])
        }
      }

      link.setAttribute('download', fileName)
      document.body.appendChild(link)
      link.click()
      link.remove()
      setShowDownloadMenu(false)
    } catch (error) {
      console.error('Download failed:', error)
      alert('다운로드에 실패했습니다.')
    }
  }

  // AI 회의록 다운로드
  const handleMeetingMinutesDownload = async (templateType) => {
    if (!data?.audio_file_id) return
    try {
      const response = await axios.get(`${API_BASE_URL}/api/v1/export/${data.audio_file_id}/meeting-minutes?template_type=${templateType}`, {
        responseType: 'blob'
      })

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url

      // 파일명 추출 (Content-Disposition 헤더에서)
      const contentDisposition = response.headers['content-disposition']
      let fileName = `회의록_${data.audio_file_id}.docx`
      if (contentDisposition) {
        const fileNameMatch = contentDisposition.match(/filename\*=UTF-8''(.+)/)
        if (fileNameMatch) {
          fileName = decodeURIComponent(fileNameMatch[1])
        }
      }

      link.setAttribute('download', fileName)
      document.body.appendChild(link)
      link.click()
      link.remove()
      setShowMeetingMinutesMenu(false)
    } catch (error) {
      console.error('회의록 생성 실패:', error)
      alert('회의록 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.')
    }
  }

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  // 현재 발화가 활성화된 섹션에 포함되는지 확인
  const isHighlighted = (index) => {
    if (!activeSection) return false
    return index >= activeSection.start_index && index <= activeSection.end_index
  }

  // 현재 발화에 활성화된 키워드가 포함되는지 확인
  const isKeywordHighlighted = (text) => {
    if (!activeKeyword) return false
    const synonyms = Array.isArray(activeKeyword.synonyms) ? activeKeyword.synonyms : []
    const targets = [activeKeyword.term, ...synonyms]

    const normalize = (str) => str.replace(/\s+/g, '').toLowerCase()
    const normalizedText = normalize(text)

    return targets.some(target => normalizedText.includes(normalize(target)))
  }

  // 텍스트 하이라이팅 컴포넌트
  const HighlightText = ({ text, keyword }) => {
    if (!keyword || !text) return <>{text}</>

    const synonyms = Array.isArray(keyword.synonyms) ? keyword.synonyms : []
    const targets = [keyword.term, ...synonyms].filter(t => t && t.trim())

    // 정규식 생성을 위해 특수문자 이스케이프 및 OR 조건 연결
    // 대소문자 무시 (i), 전역 검색 (g)
    const pattern = new RegExp(`(${targets.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')

    const parts = text.split(pattern)

    return (
      <>
        {parts.map((part, i) => {
          // part가 targets 중 하나와 일치하는지 확인 (대소문자 무시)
          const isMatch = targets.some(t => t.toLowerCase() === part.toLowerCase())
          return isMatch ? (
            <span key={i} className="bg-yellow-200 dark:bg-yellow-900/60 text-yellow-900 dark:text-yellow-100 font-bold px-1 rounded">
              {part}
            </span>
          ) : (
            <span key={i}>{part}</span>
          )
        })}
      </>
    )
  }

  // 차트 데이터 계산
  const getChartData = () => {
    // 1. 효율성 분석 결과가 있는 경우
    if (efficiency?.speaker_metrics && Array.isArray(efficiency.speaker_metrics)) {
      // 화자 이름 매핑 (효율성 분석 결과의 이름보다 data.mappings의 확정된 이름을 우선 사용)
      const getSpeakerName = (metric) => {
        const label = metric.speaker_label;
        if (data?.mappings && data.mappings[label]) {
          return data.mappings[label];
        }
        return metric.speaker_name || 'Unknown';
      };

      const doughnutData = {
        labels: efficiency.speaker_metrics.map(s => getSpeakerName(s)),
        datasets: [{
          data: efficiency.speaker_metrics.map(s => s.turn_frequency?.total_duration || 0),
          backgroundColor: [
            'rgba(99, 102, 241, 0.7)', 'rgba(236, 72, 153, 0.7)', 'rgba(34, 197, 94, 0.7)',
            'rgba(251, 146, 60, 0.7)', 'rgba(168, 85, 247, 0.7)'
          ],
          borderWidth: 1
        }]
      };

      const barData = {
        labels: efficiency.speaker_metrics.map(s => getSpeakerName(s)),
        datasets: [{
          label: '발화 횟수',
          data: efficiency.speaker_metrics.map(s => s.turn_frequency?.turn_count || 0),
          backgroundColor: 'rgba(59, 130, 246, 0.7)',
          borderRadius: 4
        }]
      };

      return { doughnutData, barData };
    }
    // 2. 효율성 분석은 없지만 회의록 데이터가 있는 경우 (로컬 계산)
    else if (data?.final_transcript && Array.isArray(data.final_transcript)) {
      const speakerStats = {};
      data.final_transcript.forEach(t => {
        const name = t.speaker_name || 'Unknown';
        if (!speakerStats[name]) {
          speakerStats[name] = { duration: 0, count: 0 };
        }
        speakerStats[name].duration += (t.end_time - t.start_time);
        speakerStats[name].count += 1;
      });
      const labels = Object.keys(speakerStats);

      const doughnutData = {
        labels: labels,
        datasets: [{
          data: labels.map(l => speakerStats[l].duration),
          backgroundColor: [
            'rgba(99, 102, 241, 0.7)', 'rgba(236, 72, 153, 0.7)', 'rgba(34, 197, 94, 0.7)',
            'rgba(251, 146, 60, 0.7)', 'rgba(168, 85, 247, 0.7)'
          ],
          borderWidth: 1
        }]
      };

      const barData = {
        labels: labels,
        datasets: [{
          label: '발화 횟수',
          data: labels.map(l => speakerStats[l].count),
          backgroundColor: 'rgba(59, 130, 246, 0.7)',
          borderRadius: 4
        }]
      };

      return { doughnutData, barData };
    }

    // 3. 데이터 없음
    const emptyData = { labels: [], datasets: [] };
    return { doughnutData: emptyData, barData: emptyData };
  };

  const { doughnutData, barData } = getChartData();

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-accent-blue"></div>
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
              회의 분석 결과
            </h1>
            <p className="text-gray-600 dark:text-gray-400">
              통합 대시보드에서 모든 정보를 확인하세요
            </p>
          </div>
          <button
            onClick={() => navigate(`/tagging/${fileId}`)}
            className="flex items-center gap-2 px-4 py-2 bg-accent-sage dark:bg-accent-teal hover:opacity-90 text-gray-900 dark:text-white rounded-lg font-medium transition-all"
          >
            <span>✏️</span> 수정하기
          </button>
        </div>

        {/* 1. 효율성 차트 (점유율 & 빈도) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* 발화 점유율 (Doughnut) */}
          <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl shadow-lg p-6 border border-bg-accent/30">
            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">발화 점유율 (시간)</h3>
            <div className="h-[300px] flex justify-center">
              <Doughnut
                data={doughnutData}
                options={{ responsive: true, maintainAspectRatio: false }}
              />
            </div>
          </div>

          {/* 발화 빈도 (Bar) */}
          <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl shadow-lg p-6 border border-bg-accent/30">
            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">발화 빈도 (횟수)</h3>
            <div className="h-[300px]">
              <Bar
                data={barData}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  scales: { y: { beginAtZero: true } }
                }}
              />
            </div>
          </div>
        </div>

        {/* 2. 추가 기능 버튼 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <button
            onClick={() => navigate(`/efficiency/${fileId}`)}
            className="flex items-center justify-center gap-3 p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark hover:bg-bg-accent/20 border border-bg-accent/30 rounded-xl transition-all group"
          >
            <span className="text-2xl group-hover:scale-110 transition-transform">📊</span>
            <div className="text-left">
              <p className="font-bold text-gray-900 dark:text-white">효율성 상세</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">더 자세한 지표 확인</p>
            </div>
          </button>

          <button
            onClick={() => navigate(`/rag/${data?.audio_file_id || fileId}`, { state: { resultFileId: fileId } })}
            className="flex items-center justify-center gap-3 p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark hover:bg-bg-accent/20 border border-bg-accent/30 rounded-xl transition-all group"
          >
            <span className="text-2xl group-hover:scale-110 transition-transform">💬</span>
            <div className="text-left">
              <p className="font-bold text-gray-900 dark:text-white">AI 질의응답</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">회의록 기반 RAG</p>
            </div>
          </button>

          <button
            onClick={() => navigate(`/todo/${data?.audio_file_id || fileId}`)}
            className="flex items-center justify-center gap-3 p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark hover:bg-bg-accent/20 border border-bg-accent/30 rounded-xl transition-all group"
          >
            <span className="text-2xl group-hover:scale-110 transition-transform">✅</span>
            <div className="text-left">
              <p className="font-bold text-gray-900 dark:text-white">TODO 관리</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">할 일 자동 추출</p>
            </div>
          </button>

          <button
            onClick={() => handleAnalyzeSections()}
            disabled={analyzing}
            className={`flex items-center justify-center gap-3 p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark hover:bg-bg-accent/20 border border-bg-accent/30 rounded-xl transition-all group ${analyzing ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <span className="text-2xl group-hover:scale-110 transition-transform">📋</span>
            <div className="text-left">
              <p className="font-bold text-gray-900 dark:text-white">
                {analyzing ? '분석 중...' : '구간 분석'}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">주제별 구간 나누기</p>
            </div>
          </button>
        </div>

        {/* 3. 전체 회의록 & 구간 분석 결과 (Split View) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 왼쪽: 회의록 (2/3) */}
          <div className="lg:col-span-2 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl shadow-lg p-6 border border-bg-accent/30">

            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">📝 전체 회의록</h2>

              <div className="flex items-center gap-3">
                {/* 일반 녹취록 다운로드 */}
                <div className="relative">
                  <button
                    onClick={() => setShowDownloadMenu(!showDownloadMenu)}
                    className="flex items-center gap-2 px-4 py-2 bg-bg-secondary dark:bg-bg-secondary-dark hover:bg-bg-accent/20 text-gray-700 dark:text-gray-200 rounded-lg font-medium transition-colors disabled:opacity-50"
                    disabled={!data?.audio_file_id}
                  >
                    <span>💾</span> 녹취록 다운로드
                  </button>

                  {showDownloadMenu && (
                    <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 z-10 overflow-hidden">
                      <button
                        onClick={() => handleDownload('docx')}
                        className="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2 transition-colors"
                      >
                        <span>📝</span> Word (DOCX)
                      </button>
                      <button
                        onClick={() => handleDownload('xlsx')}
                        className="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2 transition-colors"
                      >
                        <span>📊</span> Excel (XLSX)
                      </button>
                      <button
                        onClick={() => handleDownload('pdf')}
                        className="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2 transition-colors"
                      >
                        <span>📄</span> PDF
                      </button>
                    </div>
                  )}
                </div>

                {/* AI 회의록 생성 */}
                <div className="relative">
                  <button
                    onClick={() => setShowMeetingMinutesMenu(!showMeetingMinutesMenu)}
                    className="flex items-center gap-2 px-4 py-2 bg-bg-secondary dark:bg-bg-secondary-dark hover:bg-bg-accent/20 text-gray-700 dark:text-gray-200 rounded-lg font-medium transition-colors disabled:opacity-50"
                    disabled={!data?.audio_file_id}
                  >
                    <span>🤖</span> AI 회의록 생성
                  </button>

                  {showMeetingMinutesMenu && (
                    <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 z-10 overflow-hidden">
                      <button
                        onClick={() => handleMeetingMinutesDownload(1)}
                        className="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2 transition-colors"
                      >
                        <span>📋</span> 기본형 (한 줄 요약)
                      </button>
                      <button
                        onClick={() => handleMeetingMinutesDownload(2)}
                        className="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2 transition-colors"
                      >
                        <span>💭</span> 의견 중심형
                      </button>
                      <button
                        onClick={() => handleMeetingMinutesDownload(4)}
                        className="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 flex items-center gap-2 transition-colors"
                      >
                        <span>📊</span> 상세 관리형 (추천)
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4 max-h-[800px] overflow-y-auto pr-2">
              {data?.final_transcript?.map((segment, index) => (
                <div
                  key={index}
                  className={`p-4 rounded-lg transition-all duration-300 ${isHighlighted(index)
                      ? 'bg-teal-50 dark:bg-teal-900/30 border-b-4 border-teal-400 dark:border-teal-500' // 민트색 밑줄 강조
                      : isKeywordHighlighted(segment.text)
                        ? 'bg-yellow-50 dark:bg-yellow-900/30 border-b-4 border-yellow-400 dark:border-yellow-500' // 노란색 밑줄 강조 (키워드)
                        : 'bg-bg-secondary dark:bg-bg-secondary-dark hover:bg-bg-accent/20'
                    }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className={`font-bold ${isHighlighted(index) ? 'text-teal-700 dark:text-teal-300' : 'text-accent-blue dark:text-blue-300'}`}>
                      {segment.speaker_name}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {formatTime(segment.start_time)} - {formatTime(segment.end_time)}
                    </span>
                  </div>
                  <p className="text-gray-700 dark:text-gray-200 leading-relaxed">
                    {activeKeyword ? (
                      <HighlightText text={segment.text} keyword={activeKeyword} />
                    ) : (
                      segment.text
                    )}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* 오른쪽: 구간 정보 (1/3) */}
          {/* 오른쪽: 구간 정보 & 핵심 용어 (1/3) */}
          <div className="lg:col-span-1 space-y-6 h-fit sticky top-8">
            {sections && Array.isArray(sections) && (
              <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl shadow-lg p-6 border border-bg-accent/30">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                  <span>📑</span> 구간 분석 결과
                </h2>
                <div className="space-y-3">
                  {sections.map((section, idx) => (
                    <div
                      key={idx}
                      onClick={() => setActiveSection(prev => prev === section ? null : section)}
                      className={`p-4 rounded-xl cursor-pointer transition-all border-2 ${activeSection === section
                          ? 'border-teal-400 bg-teal-50 dark:bg-teal-900/20 shadow-md'
                          : 'border-transparent bg-bg-secondary dark:bg-bg-secondary-dark hover:bg-bg-accent/10'
                        }`}
                    >
                      <h3 className="font-bold text-gray-900 dark:text-white mb-2">
                        {section.section_title || `섹션 ${idx + 1}`}
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-2 whitespace-pre-wrap">
                        {section.discussion_summary}
                      </p>
                      <div className="flex items-center justify-between text-xs text-gray-500">
                        <span>{section.meeting_type}</span>
                        <span className="px-2 py-1 bg-gray-200 dark:bg-gray-700 rounded text-gray-700 dark:text-gray-300">
                          발화 {section.start_index} ~ {section.end_index}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 핵심 용어 (Key Words) */}
            {/* 핵심 용어 (Key Words) */}
            <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl shadow-lg p-6 border border-bg-accent/30">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                <span>🔑</span> 핵심 용어
              </h2>
              {keywords && Array.isArray(keywords) && keywords.length > 0 ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    {keywords.map((kw) => (
                      <button
                        key={kw.id}
                        onClick={() => setActiveKeyword(prev => prev === kw ? null : kw)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all border ${activeKeyword === kw
                            ? 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-200 border-yellow-400'
                            : 'bg-bg-secondary dark:bg-bg-secondary-dark text-gray-700 dark:text-gray-300 border-transparent hover:bg-bg-accent/10'
                          }`}
                        title={kw.meaning}
                      >
                        {kw.term}
                        {kw.importance >= 9 && <span className="ml-1 text-xs">🔥</span>}
                      </button>
                    ))}
                  </div>
                  {activeKeyword && (
                    <div className="mt-4 p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-700">
                      <h4 className="font-bold text-yellow-900 dark:text-yellow-100 mb-1">
                        {activeKeyword.term}
                        <span className="ml-2 text-xs font-normal text-yellow-700 dark:text-yellow-300">
                          ({activeKeyword.glossary_display})
                        </span>
                      </h4>
                      <p className="text-sm text-yellow-800 dark:text-yellow-200">
                        {activeKeyword.meaning}
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-gray-500 dark:text-gray-400 text-sm">
                  추출된 핵심 용어가 없습니다.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
