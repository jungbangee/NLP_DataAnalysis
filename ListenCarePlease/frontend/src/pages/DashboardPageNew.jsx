import React, { useState, useEffect } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { getDashboardStats, getEfficiencyOverview } from '../services/api'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

export default function DashboardPageNew() {
  const { user } = useAuth()
  const [stats, setStats] = useState(null)
  const [period, setPeriod] = useState('week')
  const [isLoading, setIsLoading] = useState(true)
  const [efficiencyData, setEfficiencyData] = useState(null)

  useEffect(() => {
    if (user?.id) {
      loadStats()
      loadEfficiency()
    }
  }, [user, period])

  const loadStats = async () => {
    try {
      setIsLoading(true)
      console.log('DashboardPageNew - Loading stats for user:', user.id, 'period:', period)
      const statsData = await getDashboardStats(user.id, period)
      console.log('DashboardPageNew - Received stats:', statsData)
      setStats(statsData)
    } catch (error) {
      console.error('Failed to load stats:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const loadEfficiency = async () => {
    try {
      const data = await getEfficiencyOverview(100)
      console.log('[DashboardPageNew] Efficiency data received:', data)
      console.log('[DashboardPageNew] Number of analyses:', data?.analyses?.length)
      setEfficiencyData(data)
    } catch (error) {
      console.error('Failed to load efficiency data:', error)
    }
  }

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-blue mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">로딩 중...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8">
      {/* 헤더 */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          대시보드
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          전체 파일 통계를 확인하세요
        </p>
      </div>

      {/* 기간 선택 */}
      <div className="mb-6 flex gap-2">
        {[
          { value: 'day', label: '오늘' },
          { value: 'week', label: '이번 주' },
          { value: 'month', label: '이번 달' },
          { value: 'all', label: '전체' }
        ].map((item) => (
          <button
            key={item.value}
            onClick={() => setPeriod(item.value)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              period === item.value
                ? 'bg-accent-sage dark:bg-accent-teal text-gray-900 dark:text-white'
                : 'bg-bg-tertiary dark:bg-bg-tertiary-dark text-gray-700 dark:text-gray-300 hover:bg-bg-accent/20'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* 총 파일 수 */}
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                총 파일 수
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white mt-2">
                {stats?.current?.total_files || 0}
              </p>
            </div>
            <div className="p-3 bg-teal-100 dark:bg-teal-900/30 rounded-lg">
              <svg className="w-8 h-8 text-accent-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
          </div>
        </div>

        {/* 기간별 처리 */}
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                {period === 'day' ? '오늘' : period === 'week' ? '이번 주' : period === 'month' ? '이번 달' : '전체'} 처리
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white mt-2">
                {stats?.current?.total_files || 0}
              </p>
            </div>
            <div className="p-3 bg-teal-100 dark:bg-teal-900/30 rounded-lg">
              <svg className="w-8 h-8 text-accent-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
        </div>

        {/* 처리 중인 파일 */}
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                처리 중
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white mt-2">
                {stats?.current?.processing || 0}
              </p>
            </div>
            <div className="p-3 bg-teal-100 dark:bg-teal-900/30 rounded-lg">
              <svg className="w-8 h-8 text-accent-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
        </div>

        {/* 평균 처리 시간 */}
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
                평균 처리 시간
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white mt-2">
                {stats?.current?.total_duration ? `${Math.round(stats.current.total_duration / 60)}분` : '-'}
              </p>
            </div>
            <div className="p-3 bg-teal-100 dark:bg-teal-900/30 rounded-lg">
              <svg className="w-8 h-8 text-accent-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* 최근 활동 */}
      <div className="mt-8 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
          📈 최근 활동
        </h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between py-3 border-b border-bg-accent/20">
            <span className="text-gray-700 dark:text-gray-300">완료된 파일</span>
            <span className="font-semibold text-gray-900 dark:text-white">{stats?.current?.completed || 0}개</span>
          </div>
          <div className="flex items-center justify-between py-3 border-b border-bg-accent/20">
            <span className="text-gray-700 dark:text-gray-300">실패한 파일</span>
            <span className="font-semibold text-gray-900 dark:text-white">{stats?.current?.failed || 0}개</span>
          </div>
          <div className="flex items-center justify-between py-3">
            <span className="text-gray-700 dark:text-gray-300">총 처리 시간</span>
            <span className="font-semibold text-gray-900 dark:text-white">
              {stats?.current?.total_duration ? `${Math.round(stats.current.total_duration / 60)}분` : '-'}
            </span>
          </div>
        </div>
      </div>

      {/* 전체 회의 엔트로피 차트 */}
      <div className="mt-8">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            전체 회의 엔트로피 (시간대별 추이)
          </h2>
          {efficiencyData && efficiencyData.analyses && efficiencyData.analyses.length > 0 ? (
            <>
              <div style={{ height: '400px' }}>
                <Line
                  data={{
                    datasets: efficiencyData.analyses.map((analysis, idx) => {
                      // 각 회의의 정규화된 엔트로피 데이터
                      const normalizedData = analysis.entropy_values_normalized || []

                      // 색상 배열 (회의별로 다른 색상)
                      const colors = [
                        'rgb(99, 102, 241)',   // 인디고
                        'rgb(236, 72, 153)',   // 핑크
                        'rgb(34, 197, 94)',    // 그린
                        'rgb(251, 146, 60)',   // 오렌지
                        'rgb(168, 85, 247)',   // 퍼플
                        'rgb(14, 165, 233)',   // 하늘색
                        'rgb(234, 179, 8)',    // 노랑
                        'rgb(239, 68, 68)',    // 빨강
                      ]

                      const color = colors[idx % colors.length]

                      return {
                        label: analysis.filename.length > 25 ? analysis.filename.substring(0, 25) + '...' : analysis.filename,
                        data: normalizedData.map(d => ({
                          x: d.time_percentage,
                          y: d.entropy
                        })),
                        borderColor: color,
                        backgroundColor: color.replace('rgb', 'rgba').replace(')', ', 0.1)'),
                        fill: false,
                        tension: 0.4,
                        pointRadius: 2,
                        pointHoverRadius: 5
                      }
                    })
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: {
                        display: true,
                        position: 'top',
                        labels: {
                          color: 'rgb(156, 163, 175)',
                          usePointStyle: true,
                          padding: 15,
                          font: {
                            size: 11
                          }
                        }
                      },
                      tooltip: {
                        mode: 'nearest',
                        intersect: false,
                        callbacks: {
                          title: (context) => {
                            const datasetIndex = context[0].datasetIndex
                            return efficiencyData.analyses[datasetIndex].filename
                          },
                          label: (context) => {
                            return [
                              `시간 진행률: ${context.parsed.x.toFixed(1)}%`,
                              `엔트로피: ${context.parsed.y.toFixed(3)}`
                            ]
                          },
                          afterLabel: (context) => {
                            const analysis = efficiencyData.analyses[context.datasetIndex]
                            return [
                              `화자 수: ${analysis.total_speakers}명`,
                              `발화 수: ${analysis.total_turns}회`,
                              `평균 엔트로피: ${analysis.entropy_avg.toFixed(3)}`
                            ]
                          }
                        }
                      }
                    },
                    scales: {
                      y: {
                        beginAtZero: false,
                        title: {
                          display: true,
                          text: '엔트로피',
                          color: 'rgb(156, 163, 175)'
                        },
                        ticks: {
                          color: 'rgb(156, 163, 175)'
                        },
                        grid: {
                          color: 'rgba(156, 163, 175, 0.1)'
                        }
                      },
                      x: {
                        type: 'linear',
                        min: 0,
                        max: 100,
                        title: {
                          display: true,
                          text: '회의 진행률 (%)',
                          color: 'rgb(156, 163, 175)'
                        },
                        ticks: {
                          color: 'rgb(156, 163, 175)',
                          callback: function(value) {
                            return value + '%'
                          }
                        },
                        grid: {
                          color: 'rgba(156, 163, 175, 0.1)'
                        }
                      }
                    }
                  }}
                />
              </div>
              <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
                * 회의 시간을 0-100%로 정규화하여 표시합니다. 여러 회의를 통해 어떤 시간대에 엔트로피가 높은지 패턴을 파악할 수 있습니다.
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                * 엔트로피가 높을수록 대화의 다양성이 높습니다.
              </p>
            </>
          ) : (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p>아직 효율성 분석이 완료된 회의가 없습니다.</p>
              <p className="text-sm mt-2">회의 결과 페이지에서 "효율성 분석" 버튼을 클릭하여 분석을 시작하세요.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
