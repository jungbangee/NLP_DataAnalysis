import React from 'react'
import { useNavigate } from 'react-router-dom'

export default function ProcessingTasks({ files }) {
  const navigate = useNavigate()

  if (!files || files.length === 0) {
    return null
  }

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
      <div className="px-4 py-5 sm:px-6 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-medium text-gray-900 dark:text-white">
          🔄 진행 중인 작업 ({files.length})
        </h2>
      </div>

      <div className="p-4 space-y-4">
        {files.map((file) => (
          <div
            key={file.id}
            className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition cursor-pointer"
            onClick={() => navigate(`/processing/${file.id}`)}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                  {file.filename}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {file.message || '처리 중...'}
                </p>
              </div>
              <div className="ml-4 flex-shrink-0">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200">
                  {file.progress}%
                </span>
              </div>
            </div>

            {/* 진행률 바 */}
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
              <div
                className="bg-indigo-600 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${file.progress}%` }}
              />
            </div>

            {/* 예상 완료 시간 - 숨김 처리
            {file.estimated_completion && (
              <div className="mt-2 flex items-center text-xs text-gray-500 dark:text-gray-400">
                <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                예상 완료: {new Date(file.estimated_completion).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
              </div>
            )}
            */}

            {/* 액션 버튼 */}
            <div className="mt-3 flex justify-end space-x-2">
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  navigate(`/processing/${file.id}`)
                }}
                className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                상세보기
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
