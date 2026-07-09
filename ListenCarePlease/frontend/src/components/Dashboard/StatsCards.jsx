import React from 'react'

export default function StatsCards({ stats, period, onPeriodChange }) {
  if (!stats) return null

  const { current, comparison } = stats

  // 시간 포맷팅 (초 → 시간/분)
  const formatDuration = (seconds) => {
    if (!seconds) return '0분'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (hours > 0) {
      return `${hours}시간 ${minutes}분`
    }
    return `${minutes}분`
  }

  const cards = [
    {
      title: '총 파일',
      value: current.total_files,
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
      bgColor: 'bg-blue-500',
      change: comparison.files_diff,
      unit: '개'
    },
    {
      title: '처리 중',
      value: current.processing,
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      bgColor: 'bg-yellow-500',
      change: null,
      unit: '개'
    },
    {
      title: '완료',
      value: current.completed,
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      bgColor: 'bg-green-500',
      change: null,
      unit: '개'
    },
    {
      title: '총 처리시간',
      value: formatDuration(current.total_duration),
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      bgColor: 'bg-gray-500',
      change: comparison.duration_diff > 0 ? `+${formatDuration(comparison.duration_diff)}` : null,
      unit: ''
    }
  ]

  return (
    <div>
      {/* 기간 선택 */}
      <div className="flex justify-end mb-4">
        <div className="inline-flex rounded-md shadow-sm" role="group">
          {['day', 'week', 'month'].map((p) => (
            <button
              key={p}
              onClick={() => onPeriodChange(p)}
              className={`px-4 py-2 text-sm font-medium border ${
                period === p
                  ? 'bg-accent-blue text-white border-accent-blue'
                  : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
              } ${
                p === 'day' ? 'rounded-l-lg' : p === 'month' ? 'rounded-r-lg' : ''
              }`}
            >
              {p === 'day' ? '일별' : p === 'week' ? '주별' : '월별'}
            </button>
          ))}
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card, index) => (
          <div
            key={index}
            className="bg-white dark:bg-gray-800 overflow-hidden shadow rounded-lg"
          >
            <div className="p-5">
              <div className="flex items-center">
                <div className={`flex-shrink-0 ${card.bgColor} rounded-md p-3`}>
                  <div className="text-white">
                    {card.icon}
                  </div>
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 dark:text-gray-400 truncate">
                      {card.title}
                    </dt>
                    <dd className="flex items-baseline">
                      <div className="text-2xl font-semibold text-gray-900 dark:text-white">
                        {card.value}
                        {card.unit && <span className="text-sm ml-1">{card.unit}</span>}
                      </div>
                      {card.change !== null && card.change !== undefined && (
                        <div className={`ml-2 flex items-baseline text-sm font-semibold ${
                          typeof card.change === 'number'
                            ? card.change > 0
                              ? 'text-green-600'
                              : card.change < 0
                              ? 'text-red-600'
                              : 'text-gray-500'
                            : 'text-green-600'
                        }`}>
                          {typeof card.change === 'number' && card.change > 0 && '+'}
                          {card.change}
                          {typeof card.change === 'number' && card.unit}
                          <span className="ml-1 text-gray-500 dark:text-gray-400">vs {period === 'day' ? '어제' : period === 'week' ? '지난주' : '지난달'}</span>
                        </div>
                      )}
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
