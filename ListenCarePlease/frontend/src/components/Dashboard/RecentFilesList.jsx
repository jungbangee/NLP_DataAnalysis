import React from 'react'
import { useNavigate } from 'react-router-dom'

export default function RecentFilesList({ files, onRefresh, onFileClick, onDelete }) {
  const navigate = useNavigate()

  // 시간 포맷팅
  const formatDuration = (seconds) => {
    if (!seconds) return '-'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (hours > 0) {
      return `${hours}시간 ${minutes}분`
    }
    return `${minutes}분`
  }

  // 상태 뱃지
  const StatusBadge = ({ status, processingStep }) => {
    const styles = {
      completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
      processing: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
      failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
      uploaded: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
      tagging_pending: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
      tagging_done: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
    }

    const labels = {
      completed: '완료',
      processing: '처리 중',
      failed: '실패',
      uploaded: '대기',
      tagging_pending: '태깅 대기',
      tagging_done: '태깅 완료'
    }

    // processing_step에 따른 세부 상태
    let displayStatus = status
    if (status === 'completed' && processingStep === 'tagging_pending') {
      displayStatus = 'tagging_pending'
    } else if (status === 'completed' && processingStep === 'tagging_done') {
      displayStatus = 'tagging_done'
    }

    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[displayStatus] || styles.uploaded}`}>
        {labels[displayStatus] || status}
      </span>
    )
  }

  // 파일 클릭 핸들러 - 진행 단계에 따라 적절한 페이지로 이동
  const handleFileClick = (file) => {
    if (file.status === 'completed') {
      // processing_step에 따라 분기
      if (file.processing_step === 'tagging_pending' || !file.has_tagging) {
        // 태깅이 안 된 경우 → 태깅 페이지로
        navigate(`/tagging/${file.id}`)
      } else {
        // 태깅 완료된 경우 → 결과 팝업
        if (onFileClick) {
          onFileClick(file)
        } else {
          navigate(`/result/${file.id}`)
        }
      }
    } else if (file.status === 'processing') {
      // 처리 중인 파일은 UUID로 접근 (메모리에서 상태 추적)
      const fileId = file.file_uuid || file.id
      navigate(`/processing/${fileId}`)
    }
  }

  if (!files || files.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
          최근 파일
        </h2>
        <div className="text-center py-12">
          <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">파일이 없습니다</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            첫 파일을 업로드해보세요
          </p>
          <div className="mt-6">
            <button
              onClick={() => navigate('/upload')}
              className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700"
            >
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              파일 업로드
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
      <div className="px-4 py-5 sm:px-6 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white">
            최근 파일
          </h2>
          <button
            onClick={onRefresh}
            className="text-sm text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
          >
            새로고침
          </button>
        </div>
      </div>

      <ul className="divide-y divide-gray-200 dark:divide-gray-700">
        {files.map((file) => (
          <li
            key={file.id}
            className="px-4 py-4 sm:px-6 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition"
            onClick={() => handleFileClick(file)}
          >
            <div className="flex items-center justify-between">
              <div className="flex-1 min-w-0">
                {/* 파일명 & 상태 */}
                <div className="flex items-center space-x-3">
                  <svg className="flex-shrink-0 w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                  </svg>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {file.filename}
                    </p>
                    <div className="mt-1 flex items-center space-x-2">
                      <StatusBadge status={file.status} processingStep={file.processing_step} />
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {file.time_ago}
                      </span>
                      {file.duration && (
                        <>
                          <span className="text-gray-300 dark:text-gray-600">•</span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {formatDuration(file.duration)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* 참여자 정보 */}
                {file.participants && file.participants.length > 0 && (
                  <div className="mt-2 flex items-center text-sm text-gray-500 dark:text-gray-400">
                    <svg className="flex-shrink-0 mr-1.5 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    <span>{file.participants.join(', ')} ({file.participant_count}명)</span>
                  </div>
                )}

                {/* 처리 진행률 */}
                {file.status === 'processing' && file.processing_progress !== null && (
                  <div className="mt-2">
                    <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                      <span>{file.processing_message || '처리 중...'}</span>
                      <span>{file.processing_progress}%</span>
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                      <div
                        className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${file.processing_progress}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* 에러 메시지 */}
                {file.error_message && (
                  <div className="mt-2 text-sm text-red-600 dark:text-red-400">
                    <svg className="inline w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {file.error_message}
                  </div>
                )}
              </div>

              {/* 액션 버튼 */}
              <div className="ml-4 flex-shrink-0 flex items-center space-x-2">
                {file.status === 'completed' && file.has_tagging && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      if (onFileClick) {
                        onFileClick(file)
                      } else {
                        navigate(`/result/${file.id}`)
                      }
                    }}
                    className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200 dark:bg-indigo-900 dark:text-indigo-200 dark:hover:bg-indigo-800"
                  >
                    결과보기
                  </button>
                )}
                {file.status === 'completed' && !file.has_tagging && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/tagging/${file.id}`)
                    }}
                    className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md text-orange-700 bg-orange-100 hover:bg-orange-200 dark:bg-orange-900 dark:text-orange-200 dark:hover:bg-orange-800"
                  >
                    태깅하기
                  </button>
                )}
                {file.status === 'processing' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      const fileId = file.file_uuid || file.id
                      navigate(`/processing/${fileId}`)
                    }}
                    className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700"
                  >
                    상태확인
                  </button>
                )}
                {file.status === 'uploaded' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/processing/${file.id}`)
                    }}
                    className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded-md text-green-700 bg-green-100 hover:bg-green-200 dark:bg-green-900 dark:text-green-200 dark:hover:bg-green-800"
                  >
                    처리하기
                  </button>
                )}
                {/* 삭제 버튼 */}
                {onDelete && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      if (window.confirm(`"${file.filename}" 파일을 삭제하시겠습니까?`)) {
                        onDelete(file.id)
                      }
                    }}
                    className="inline-flex items-center px-2 py-1.5 text-xs font-medium rounded-md text-red-600 hover:bg-red-100 dark:text-red-400 dark:hover:bg-red-900/30"
                    title="삭제"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
