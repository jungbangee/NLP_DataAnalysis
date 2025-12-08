import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getTaggingResult } from '../../services/api'

export default function ResultModal({ fileId, filename, onClose }) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [stats, setStats] = useState(null)

  useEffect(() => {
    if (fileId) {
      fetchResult()
    }
  }, [fileId])

  const fetchResult = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await getTaggingResult(fileId)
      setData(response)
      calculateStats(response)
    } catch (err) {
      console.error('결과 조회 실패:', err)
      setError(err.response?.data?.detail || '결과를 불러올 수 없습니다')
    } finally {
      setLoading(false)
    }
  }

  const calculateStats = (resultData) => {
    if (!resultData?.final_transcript) return

    const speakerStats = {}
    resultData.final_transcript.forEach((segment) => {
      const speaker = segment.speaker_name
      const duration = segment.end_time - segment.start_time

      if (!speakerStats[speaker]) {
        speakerStats[speaker] = { count: 0, totalDuration: 0 }
      }
      speakerStats[speaker].count += 1
      speakerStats[speaker].totalDuration += duration
    })
    setStats(speakerStats)
  }

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}분 ${secs}초`
  }

  const handleDownload = () => {
    if (!data) return

    const text = data.final_transcript
      .map(seg => `[${formatTime(seg.start_time)} - ${formatTime(seg.end_time)}] ${seg.speaker_name}:\n${seg.text}\n`)
      .join('\n')

    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `회의록_${filename || fileId}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ESC 키로 닫기
  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* 배경 오버레이 */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />

      {/* 모달 컨테이너 */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden">
          {/* 헤더 */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                {filename || '회의록'}
              </h2>
              {data && (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  총 {data.total_segments}개 발화
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition"
            >
              <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* 내용 */}
          <div className="overflow-y-auto max-h-[calc(90vh-140px)] p-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600"></div>
              </div>
            ) : error ? (
              <div className="text-center py-12">
                <div className="text-red-500 mb-2">
                  <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p className="text-gray-600 dark:text-gray-400">{error}</p>
              </div>
            ) : (
              <>
                {/* 통계 */}
                {stats && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    {Object.entries(stats).map(([speaker, stat]) => (
                      <div key={speaker} className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                        <div className="font-semibold text-gray-900 dark:text-white truncate">{speaker}</div>
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          {stat.count}회 / {formatDuration(stat.totalDuration)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* 대본 */}
                <div className="space-y-3">
                  {data?.final_transcript.map((segment, index) => (
                    <div
                      key={index}
                      className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-indigo-600 dark:text-indigo-400">
                          {segment.speaker_name}
                        </span>
                        <span className="text-xs text-gray-400">
                          {formatTime(segment.start_time)} - {formatTime(segment.end_time)}
                        </span>
                      </div>
                      <p className="text-gray-700 dark:text-gray-200 text-sm">{segment.text}</p>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* 푸터 */}
          {!loading && !error && (
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={handleDownload}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition"
              >
                다운로드
              </button>
              <button
                onClick={() => {
                  onClose()
                  navigate(`/tagging/${fileId}`)
                }}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition"
              >
                수정하기
              </button>
              <button
                onClick={onClose}
                className="px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 text-gray-700 dark:text-gray-200 rounded-lg font-medium transition"
              >
                닫기
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
