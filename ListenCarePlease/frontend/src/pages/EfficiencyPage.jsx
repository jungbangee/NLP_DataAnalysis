import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getEfficiencyAnalysis, triggerEfficiencyAnalysis, getTaggingResult } from '../services/api'
import { Line, Bar, Radar, Doughnut } from 'react-chartjs-2'
import ReactMarkdown from 'react-markdown'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  RadialLinearScale,
  ArcElement,
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
  BarElement,
  RadialLinearScale,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

export default function EfficiencyPage() {
  const { fileId } = useParams()
  const navigate = useNavigate()
  const [analysis, setAnalysis] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [selectedSpeaker, setSelectedSpeaker] = useState(null)
  const [error, setError] = useState(null)
  const [pollingAttempts, setPollingAttempts] = useState(0)
  const [showDetails, setShowDetails] = useState(false)
  const MAX_POLLING_ATTEMPTS = 600
  const timeoutRef = React.useRef(null)

  useEffect(() => {
    loadAnalysis()

    // 컴포넌트 언마운트 시 타임아웃 정리
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [fileId])

  // 전체 회의 통합 지표 계산
  const calculateOverallMetrics = (speakerMetrics, analysisData) => {
    if (!speakerMetrics || speakerMetrics.length === 0) return null

    // 발화 빈도 통합
    const totalTurnCount = speakerMetrics.reduce((sum, s) => sum + (s.turn_frequency?.turn_count || 0), 0)
    const totalDuration = speakerMetrics.reduce((sum, s) => sum + (s.turn_frequency?.total_duration || 0), 0)

    // 백엔드의 전체 회의 지표 사용 (인사이트 포함)
    return {
      speaker_label: 'OVERALL',
      speaker_name: '전체 회의',
      turn_frequency: {
        turn_count: totalTurnCount,
        total_duration: totalDuration,
        avg_turn_length: totalTurnCount > 0 ? totalDuration / totalTurnCount : 0
      },
      // 백엔드에서 계산한 전체 회의 지표 사용 (AI 인사이트 포함)
      ttr: analysisData?.overall_ttr || {
        ttr_avg: 0,
        ttr_std: 0,
        ttr_values: []
      },
      information_content: analysisData?.overall_information_content || {
        avg_similarity: 0,
        information_score: 0
      },
      sentence_probability: analysisData?.overall_sentence_probability || {
        avg_probability: 0,
        outlier_ratio: 0
      },
      perplexity: analysisData?.overall_perplexity || {
        ppl_avg: 0,
        ppl_std: 0,
        ppl_values: []
      }
    }
  }

  const loadAnalysis = async () => {
    try {
      // 첫 로딩시에만 로딩 스피너 표시
      if (!analysis && pollingAttempts === 0) setIsLoading(true)
      setError(null)

      const data = await getEfficiencyAnalysis(fileId)
      setAnalysis(data)

      if (data.speaker_metrics && data.speaker_metrics.length > 0) {
        const overall = calculateOverallMetrics(data.speaker_metrics, data)
        setSelectedSpeaker(overall)
      }

      // 성공하면 폴링 종료 (재귀 호출 안함)
      setIsAnalyzing(false)
      setIsLoading(false)

    } catch (error) {
      if (error.response?.status === 404) {
        // 404일 경우: 아직 분석 중이거나 시작되지 않음.
        if (pollingAttempts === 0) {
          console.log("Analysis not found, triggering new analysis...");
          try {
            await triggerEfficiencyAnalysis(fileId);
          } catch (e) {
            console.error("Failed to trigger analysis:", e);
            // 파일이 없거나 트리거 실패 시 폴링 중단
            setError('analysis_failed');
            setIsAnalyzing(false);
            setIsLoading(false);
            return;
          }
        }

        try {
          const taggingData = await getTaggingResult(fileId)
          if (taggingData && taggingData.final_transcript) {
            const speakerStats = {};
            taggingData.final_transcript.forEach(t => {
              const name = t.speaker_name || 'Unknown';
              if (!speakerStats[name]) {
                speakerStats[name] = { duration: 0, count: 0 };
              }
              speakerStats[name].duration += (t.end_time - t.start_time);
              speakerStats[name].count += 1;
            });

            const localMetrics = Object.keys(speakerStats).map(name => ({
              speaker_name: name,
              speaker_label: name,
              turn_frequency: {
                turn_count: speakerStats[name].count,
                total_duration: speakerStats[name].duration
              }
            }));

            setAnalysis(prev => ({
              ...prev,
              speaker_metrics: localMetrics,
              qualitative_analysis: "AI 심층 분석이 진행 중입니다... 잠시만 기다려주세요.",
            }));
          }
        } catch (tagError) {
          console.log("Failed to fetch tagging result for local metrics:", tagError);
        }

        // 최대 시도 횟수 초과 체크
        if (pollingAttempts >= MAX_POLLING_ATTEMPTS) {
          setError('timeout')
          setIsAnalyzing(false)
        } else {
          // 분석 중 상태 유지 및 다음 폴링 예약
          setIsAnalyzing(true)
          setPollingAttempts(prev => prev + 1)
          setIsLoading(false)

          // 재귀적 setTimeout 사용: 현재 요청이 끝난 후 3초 뒤에 다음 요청
          timeoutRef.current = setTimeout(() => {
            loadAnalysis()
          }, 3000)
        }
      } else {
        console.error('Failed to load efficiency analysis:', error)
        // 네트워크 에러 등이 발생해도 잠시 후 재시도 (리소스 부족 에러 방지 위해 5초 대기)
        if (pollingAttempts < MAX_POLLING_ATTEMPTS) {
          timeoutRef.current = setTimeout(() => {
            loadAnalysis()
          }, 5000)
        } else {
          setError('error')
          setIsLoading(false)
        }
      }
    }
  }

  // 분석 중이거나 초기 로딩 중
  if (isLoading || isAnalyzing) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-accent-blue mx-auto"></div>
          <p className="mt-6 text-xl font-medium text-gray-900 dark:text-white">
            효율성 분석 중입니다...
          </p>
          <p className="mt-2 text-gray-600 dark:text-gray-400">
            {isAnalyzing ? '분석이 완료될 때까지 기다려주세요 (자동 새로고침)' : '분석 결과 로딩 중...'}
          </p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <div className="animate-pulse w-2 h-2 bg-accent-blue rounded-full"></div>
            <div className="animate-pulse w-2 h-2 bg-accent-blue rounded-full" style={{ animationDelay: '0.2s' }}></div>
            <div className="animate-pulse w-2 h-2 bg-accent-blue rounded-full" style={{ animationDelay: '0.4s' }}></div>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="max-w-2xl mx-auto text-center">
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg p-8">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
              오류 발생
            </h2>
            <p className="text-gray-600 dark:text-gray-400">
              효율성 분석 결과를 불러오는데 실패했습니다.
            </p>
          </div>
        </div>
      </div>
    )
  }

  // 엔트로피 차트 데이터
  const entropyChartData = {
    labels: analysis?.entropy?.values?.map((_, i) => i) || [],
    datasets: [
      {
        label: '엔트로피',
        data: analysis?.entropy?.values?.map(v => v.entropy) || [],
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        fill: true,
        tension: 0.4
      }
    ]
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        labels: {
          color: 'rgb(156, 163, 175)'
        }
      }
    },
    scales: {
      y: {
        ticks: { color: 'rgb(156, 163, 175)' },
        grid: { color: 'rgba(156, 163, 175, 0.1)' }
      },
      x: {
        ticks: { color: 'rgb(156, 163, 175)' },
        grid: { color: 'rgba(156, 163, 175, 0.1)' }
      }
    }
  }

  return (
    <div className="p-8">
      {/* 헤더 */}
      <div className="mb-8 flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          회의 효율성 분석
        </h1>
        <button
          onClick={() => navigate(`/result/${fileId}`)}
          className="px-4 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg font-medium transition-colors"
        >
          ← 결과 페이지로
        </button>
      </div>
      {/* 1. 정성적 평가 (Qualitative Evaluation) */}
      {analysis?.qualitative_analysis && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-lg border border-gray-200 dark:border-gray-700 mb-8">
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-3 pb-4 border-b-2 border-accent-sage dark:border-accent-teal">
            <span className="text-4xl">🤖</span>
            <span className="text-gray-900 dark:text-white">
              AI 종합 평가
            </span>
          </h2>
          <div className="bg-gradient-to-br from-green-50/50 to-teal-50/50 dark:from-gray-700/30 dark:to-gray-600/30 rounded-lg p-6">
            <div className="space-y-4">
              <ReactMarkdown
                components={{
                  h1: ({ node, ...props }) => (
                    <h1 className="text-2xl font-bold mt-6 mb-4 pb-3 border-b-2 px-3 py-2 rounded-t-lg text-[#F2C9B3] dark:text-[#D4A89A] border-[#F2C9B3]/30 dark:border-[#D4A89A]/30 bg-[#F2C9B3]/10 dark:bg-[#D4A89A]/10" {...props} />
                  ),
                  h2: ({ node, ...props }) => (
                    <h2 className="text-xl font-bold mt-6 mb-3 pb-2 border-b-2 text-[#F5A623] dark:text-[#F5A623] border-[#F5A623]/30 dark:border-[#F5A623]/30" {...props} />
                  ),
                  h3: ({ node, ...props }) => (
                    <h3 className="text-lg font-semibold mt-5 mb-2 text-[#7AC943] dark:text-[#7AC943]" {...props} />
                  ),
                  p: ({ node, ...props }) => (
                    <p className="text-gray-700 dark:text-gray-300 leading-7 mb-4 pl-1" {...props} />
                  ),
                  ul: ({ node, ...props }) => (
                    <ul className="space-y-2 mb-4 ml-1" {...props} />
                  ),
                  ol: ({ node, ...props }) => (
                    <ol className="space-y-2 mb-4 ml-1" {...props} />
                  ),
                  li: ({ node, ...props }) => (
                    <li className="text-gray-700 dark:text-gray-300 leading-7 pl-1" {...props} />
                  ),
                  strong: ({ node, ...props }) => (
                    <strong className="font-bold text-[#D4A89A] dark:text-[#F2C9B3]" {...props} />
                  ),
                  em: ({ node, ...props }) => (
                    <em className="italic text-[#7AC943] dark:text-[#7AC943]" {...props} />
                  ),
                  code: ({ node, inline, ...props }) => inline
                    ? <code className="bg-[#7AC943]/10 dark:bg-[#7AC943]/20 px-2 py-1 rounded text-sm font-mono text-[#7AC943] dark:text-[#7AC943]" {...props} />
                    : <code className="block bg-[#7AC943]/10 dark:bg-[#7AC943]/20 p-4 rounded-lg text-sm font-mono overflow-x-auto mb-4" {...props} />,
                  blockquote: ({ node, ...props }) => (
                    <blockquote className="border-l-4 border-[#D4A89A] dark:border-[#F2C9B3] pl-4 italic bg-[#D4A89A]/10 dark:bg-[#F2C9B3]/10 py-3 my-4 text-gray-700 dark:text-gray-300" {...props} />
                  )
                }}
              >
                {analysis.qualitative_analysis}
              </ReactMarkdown>
            </div>
          </div>
        </div>
      )}

      {/* 2. 침묵 구간 분석 (Silence Analysis) */}
      {analysis?.silence_analysis && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-lg border border-gray-200 dark:border-gray-700 mb-8">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
            <span>🔇</span> 침묵 구간 분석
          </h2>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">총 침묵 시간</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {analysis.silence_analysis.stats?.total_silence?.toFixed(1)}s
              </p>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">평균 침묵 길이</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {analysis.silence_analysis.stats?.mean_silence?.toFixed(1)}s
              </p>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">최대 침묵 길이</p>
              <p className="text-2xl font-bold text-red-500">
                {analysis.silence_analysis.stats?.max_silence?.toFixed(1)}s
              </p>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700 p-4 rounded-lg text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">침묵 횟수</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {analysis.silence_analysis.stats?.count}회
              </p>
            </div>
          </div>

          {/* Silence Gaps Chart */}
          {analysis.silence_analysis.gaps && analysis.silence_analysis.gaps.length > 0 && (
            <div className="h-64">
              <Bar
                data={{
                  labels: analysis.silence_analysis.gaps.map((_, i) => `Gap ${i + 1}`),
                  datasets: [{
                    label: 'Silence Duration (s)',
                    data: analysis.silence_analysis.gaps.map(g => g.duration),
                    backgroundColor: 'rgba(239, 68, 68, 0.5)',
                    borderColor: 'rgb(239, 68, 68)',
                    borderWidth: 1
                  }]
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: { display: false },
                    tooltip: {
                      callbacks: {
                        label: (ctx) => {
                          const gap = analysis.silence_analysis.gaps[ctx.dataIndex];
                          return `Duration: ${gap.duration.toFixed(1)}s (${gap.prev_speaker} -> ${gap.next_speaker})`;
                        }
                      }
                    }
                  },
                  scales: {
                    y: { title: { display: true, text: 'Duration (s)' } }
                  }
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* 3. 화자 간 상호작용 (Interaction Network) */}
      {analysis?.interaction_analysis && analysis.interaction_analysis.nodes && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-lg border border-gray-200 dark:border-gray-700 mb-8">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
            <span>🕸️</span> 화자 간 상호작용 (Interaction Network)
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            화살표는 발언권 전환을 나타내며, 진할수록 빈도가 높습니다.
          </p>

          <div className="flex justify-center items-center min-h-[400px] bg-gray-50 dark:bg-gray-900/30 rounded-lg p-8">
            <svg width="100%" height="400" viewBox="0 0 600 400" className="max-w-full">
              <defs>
                <marker
                  id="arrowhead"
                  markerWidth="10"
                  markerHeight="10"
                  refX="9"
                  refY="3"
                  orient="auto"
                  fill="#D4A89A"
                >
                  <polygon points="0 0, 10 3, 0 6" />
                </marker>
              </defs>

              {(() => {
                const nodes = analysis.interaction_analysis.nodes;
                const links = analysis.interaction_analysis.links;
                const maxCount = Math.max(...links.map(l => l.value), 1);

                // Position nodes in a circle
                const centerX = 300;
                const centerY = 200;
                const radius = 120;
                const nodePositions = nodes.map((node, i) => {
                  const angle = (i / nodes.length) * 2 * Math.PI - Math.PI / 2;
                  return {
                    ...node,
                    x: centerX + radius * Math.cos(angle),
                    y: centerY + radius * Math.sin(angle)
                  };
                });

                return (
                  <>
                    {/* Draw arrows (links) */}
                    {links.map((link, idx) => {
                      const source = nodePositions.find(n => n.id === link.source);
                      const target = nodePositions.find(n => n.id === link.target);
                      if (!source || !target) return null;

                      // Calculate arrow position (from edge of source circle to edge of target circle)
                      const dx = target.x - source.x;
                      const dy = target.y - source.y;
                      const dist = Math.sqrt(dx * dx + dy * dy);
                      const nodeRadius = 40;

                      const startX = source.x + (dx / dist) * nodeRadius;
                      const startY = source.y + (dy / dist) * nodeRadius;
                      const endX = target.x - (dx / dist) * (nodeRadius + 10);
                      const endY = target.y - (dy / dist) * (nodeRadius + 10);

                      // Calculate curve for better visibility
                      const midX = (startX + endX) / 2;
                      const midY = (startY + endY) / 2;
                      const offsetX = -(dy / dist) * 30;
                      const offsetY = (dx / dist) * 30;

                      const intensity = link.value / maxCount;
                      const strokeWidth = 1 + intensity * 4;
                      const opacity = 0.3 + intensity * 0.7;

                      return (
                        <g key={`link-${idx}`}>
                          <path
                            d={`M ${startX} ${startY} Q ${midX + offsetX} ${midY + offsetY} ${endX} ${endY}`}
                            fill="none"
                            stroke="#D4A89A"
                            strokeWidth={strokeWidth}
                            opacity={opacity}
                            markerEnd="url(#arrowhead)"
                          />
                          <text
                            x={midX + offsetX}
                            y={midY + offsetY - 5}
                            className="fill-gray-700 dark:fill-gray-300 text-xs font-semibold"
                            textAnchor="middle"
                          >
                            {link.value}
                          </text>
                        </g>
                      );
                    })}

                    {/* Draw nodes (speakers) */}
                    {nodePositions.map((node, idx) => (
                      <g key={`node-${idx}`}>
                        <circle
                          cx={node.x}
                          cy={node.y}
                          r="40"
                          fill="#D4A89A"
                          stroke="#C9B59C"
                          strokeWidth="3"
                        />
                        <text
                          x={node.x}
                          y={node.y}
                          className="fill-white dark:fill-white text-sm font-bold"
                          textAnchor="middle"
                          dominantBaseline="middle"
                        >
                          {node.label}
                        </text>
                      </g>
                    ))}
                  </>
                );
              })()}
            </svg>
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-center justify-center gap-6 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex items-center gap-2">
              <div className="w-8 h-1" style={{ backgroundColor: '#D4A89A', opacity: 0.3 }}></div>
              <span>낮은 빈도</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-1" style={{ backgroundColor: '#D4A89A', opacity: 0.7 }}></div>
              <span>중간 빈도</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-2" style={{ backgroundColor: '#D4A89A', opacity: 1 }}></div>
              <span>높은 빈도</span>
            </div>
          </div>
        </div>
      )}

      {/* 3. 발화 점유율 비교 (Share of Voice Comparison) */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-lg border border-gray-200 dark:border-gray-700 mb-8">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
          <span>📊</span> 발화 점유율 비교 (Share of Voice)
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* 시간 기반 */}
          <div>
            <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-4 text-center">
              시간 기반 (Time-based)
            </h3>
            <div className="h-[300px] flex justify-center">
              <Doughnut
                data={{
                  labels: analysis?.speaker_metrics?.map(s => s.speaker_name) || [],
                  datasets: [{
                    data: analysis?.speaker_metrics?.map(s => s.turn_frequency?.total_duration || 0) || [],
                    backgroundColor: [
                      'rgba(99, 102, 241, 0.7)', 'rgba(236, 72, 153, 0.7)', 'rgba(34, 197, 94, 0.7)',
                      'rgba(251, 146, 60, 0.7)', 'rgba(168, 85, 247, 0.7)', 'rgba(234, 179, 8, 0.7)'
                    ],
                    borderWidth: 2,
                    borderColor: 'rgba(255, 255, 255, 1)'
                  }]
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: { position: 'bottom' },
                    tooltip: {
                      callbacks: {
                        label: (context) => {
                          const total = context.dataset.data.reduce((a, b) => a + b, 0);
                          const percentage = ((context.parsed / total) * 100).toFixed(1);
                          return `${context.label}: ${percentage}% (${(context.parsed / 60).toFixed(1)}분)`;
                        }
                      }
                    }
                  }
                }}
              />
            </div>
          </div>

          {/* 토큰 기반 */}
          <div>
            <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-4 text-center">
              토큰 기반 (Token-based)
            </h3>
            <div className="h-[300px] flex justify-center">
              <Doughnut
                data={{
                  labels: analysis?.speaker_metrics?.map(s => s.speaker_name) || [],
                  datasets: [{
                    data: analysis?.speaker_metrics?.map(s => {
                      // 각 화자의 모든 텍스트를 합쳐서 토큰 수 계산 (간단히 단어 수로 근사)
                      const transcripts = s.transcripts || [];
                      const totalTokens = transcripts.reduce((sum, t) => sum + (t.text?.split(/\s+/).length || 0), 0);
                      return totalTokens || s.turn_frequency?.turn_count || 0;
                    }) || [],
                    backgroundColor: [
                      'rgba(99, 102, 241, 0.7)', 'rgba(236, 72, 153, 0.7)', 'rgba(34, 197, 94, 0.7)',
                      'rgba(251, 146, 60, 0.7)', 'rgba(168, 85, 247, 0.7)', 'rgba(234, 179, 8, 0.7)'
                    ],
                    borderWidth: 2,
                    borderColor: 'rgba(255, 255, 255, 1)'
                  }]
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: { position: 'bottom' },
                    tooltip: {
                      callbacks: {
                        label: (context) => {
                          const total = context.dataset.data.reduce((a, b) => a + b, 0);
                          const percentage = ((context.parsed / total) * 100).toFixed(1);
                          return `${context.label}: ${percentage}% (${context.parsed}토큰)`;
                        }
                      }
                    }
                  }
                }}
              />
            </div>
          </div>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-4 text-center">
          시간 기반은 발화 시간, 토큰 기반은 발화량(단어 수)을 기준으로 합니다
        </p>
      </div>

      {/* 상세 분석 토글 버튼 */}
      <div className="flex justify-center mb-8">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-2 px-6 py-3 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-full font-bold text-gray-700 dark:text-gray-200 transition-all transform hover:scale-105"
        >
          <span>{showDetails ? '🔽' : '▶️'}</span>
          {showDetails ? '상세 분석 접기' : '상세 분석 보기 (Entropy, TTR, PPL)'}
        </button>
      </div>

      {/* 3. 상세 분석 (Detailed Analysis) - 토글됨 */}
      {showDetails && (
        <div className="animate-fade-in-down space-y-8">
          {/* 전체 회의 통계 (기존 내용) */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                평균 엔트로피
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">
                {analysis?.entropy?.avg?.toFixed(2) || 'N/A'}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                표준편차: {analysis?.entropy?.std?.toFixed(2) || 'N/A'}
              </p>
            </div>

            <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                총 화자 수
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">
                {analysis?.total_speakers || 0}명
              </p>
            </div>

            <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                총 발화 수
              </p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">
                {analysis?.total_turns || 0}회
              </p>
            </div>
          </div>

          {/* 전체 회의 엔트로피 차트 */}
          {analysis?.entropy?.values && analysis.entropy.values.length > 0 && (
            <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30 mb-8">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2 border-b-2 border-green-500 pb-2">
                담화 엔트로피 (Entropy)
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                높은 엔트로피 = 다양한 주제, 낮은 엔트로피 = 집중된 논의
              </p>
              <div style={{ height: '400px' }}>
                <Line
                  data={{
                    labels: analysis.entropy.values.map((_, i) => i + 1),
                    datasets: [
                      {
                        label: 'Original Entropy',
                        data: analysis.entropy.values.map(v => v.entropy),
                        borderColor: 'rgba(75, 192, 192, 0.3)',
                        backgroundColor: 'rgba(75, 192, 192, 0.1)',
                        fill: true,
                        tension: 0.4,
                        borderWidth: 1,
                        pointRadius: 0
                      },
                      {
                        label: 'Moving Avg (10)',
                        data: analysis.entropy.values.map((v, i, arr) => {
                          const start = Math.max(0, i - 5)
                          const end = Math.min(arr.length, i + 5)
                          const slice = arr.slice(start, end).map(item => item.entropy)
                          return slice.reduce((a, b) => a + b, 0) / slice.length
                        }),
                        borderColor: 'rgb(75, 192, 192)',
                        borderWidth: 2,
                        fill: false,
                        tension: 0.4,
                        pointRadius: 0
                      },
                      {
                        label: 'Moving Avg (30)',
                        data: analysis.entropy.values.map((v, i, arr) => {
                          const start = Math.max(0, i - 15)
                          const end = Math.min(arr.length, i + 15)
                          const slice = arr.slice(start, end).map(item => item.entropy)
                          return slice.reduce((a, b) => a + b, 0) / slice.length
                        }),
                        borderColor: 'rgb(0, 128, 128)',
                        borderWidth: 2.5,
                        fill: false,
                        tension: 0.4,
                        pointRadius: 0
                      }
                    ]
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: {
                        display: true,
                        position: 'top',
                        labels: { color: 'rgb(156, 163, 175)', font: { size: 11 } }
                      }
                    },
                    scales: {
                      y: {
                        beginAtZero: false,
                        title: {
                          display: true,
                          text: 'Entropy (bits)',
                          color: 'rgb(156, 163, 175)',
                          font: { weight: 'bold' }
                        },
                        ticks: { color: 'rgb(156, 163, 175)' },
                        grid: { color: 'rgba(156, 163, 175, 0.1)' }
                      },
                      x: {
                        title: {
                          display: true,
                          text: 'Window Index',
                          color: 'rgb(156, 163, 175)',
                          font: { weight: 'bold' }
                        },
                        ticks: { color: 'rgb(156, 163, 175)' },
                        grid: { color: 'rgba(156, 163, 175, 0.1)' }
                      }
                    }
                  }}
                />
              </div>
              {analysis.entropy.insight && (
                <div className="bg-gradient-to-r from-green-50 to-teal-50 dark:from-green-900/20 dark:to-teal-900/20 border border-green-200 dark:border-green-700 rounded-lg p-4 mt-4">
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">💡</span>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-green-900 dark:text-green-100 mb-1">AI 분석 결과</p>
                      <p className="text-sm text-green-800 dark:text-green-200">
                        {analysis.entropy.insight}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 화자별 분석 */}
          <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl p-6 border border-bg-accent/30">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
              화자별 효율성 지표
            </h2>

            {/* 화자 선택 탭 */}
            <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
              {/* 전체 회의 버튼 */}
              <button
                onClick={() => setSelectedSpeaker(calculateOverallMetrics(analysis?.speaker_metrics, analysis))}
                className={`px-4 py-2 rounded-lg font-medium transition-colors whitespace-nowrap ${selectedSpeaker?.speaker_label === 'OVERALL'
                    ? 'bg-accent-blue text-white'
                    : 'bg-bg-secondary dark:bg-bg-secondary-dark text-gray-700 dark:text-gray-300 hover:bg-bg-accent/20'
                  }`}
              >
                📊 전체 회의
              </button>

              {/* 개별 화자 버튼 */}
              {analysis?.speaker_metrics?.map((speaker) => (
                <button
                  key={speaker.speaker_label}
                  onClick={() => setSelectedSpeaker(speaker)}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors whitespace-nowrap ${selectedSpeaker?.speaker_label === speaker.speaker_label
                      ? 'bg-accent-sage dark:bg-accent-teal text-gray-900 dark:text-white'
                      : 'bg-bg-secondary dark:bg-bg-secondary-dark text-gray-700 dark:text-gray-300 hover:bg-bg-accent/20'
                    }`}
                >
                  {speaker.speaker_name}
                </button>
              ))}
            </div>

            {/* 선택된 화자의 지표 */}
            {selectedSpeaker && (
              <div className="space-y-8">
                {/* 1. TTR */}
                <div>
                  <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2 border-b-2 border-orange-500 pb-2">
                    1. TTR (Type-Token Ratio)
                  </h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                    고유 단어 수 / 전체 단어 수. 높을수록 어휘가 다양합니다.
                  </p>
                  <div className="bg-bg-secondary dark:bg-bg-secondary-dark rounded-lg p-6">
                    <div className="grid grid-cols-2 gap-6 mb-6">
                      <div className="text-center p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg">
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">평균 TTR</p>
                        <p className="text-4xl font-bold text-orange-600 dark:text-orange-400">
                          {selectedSpeaker.ttr?.ttr_avg?.toFixed(3) || 'N/A'}
                        </p>
                      </div>
                      <div className="text-center p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg">
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">표준편차</p>
                        <p className="text-4xl font-bold text-red-600 dark:text-red-400">
                          {selectedSpeaker.ttr?.ttr_std?.toFixed(3) || 'N/A'}
                        </p>
                      </div>
                    </div>

                    {selectedSpeaker.ttr?.ttr_values && selectedSpeaker.ttr.ttr_values.length > 0 && (
                      <div style={{ height: '350px' }}>
                        <Line
                          data={{
                            labels: selectedSpeaker.ttr.ttr_values.map((_, i) => i + 1),
                            datasets: [
                              {
                                label: 'Original TTR',
                                data: selectedSpeaker.ttr.ttr_values,
                                borderColor: 'rgba(255, 159, 64, 0.3)',
                                backgroundColor: 'rgba(255, 159, 64, 0.1)',
                                fill: true,
                                tension: 0.4,
                                borderWidth: 1,
                                pointRadius: 0
                              },
                              {
                                label: 'Moving Avg (10)',
                                data: selectedSpeaker.ttr.ttr_values.map((v, i, arr) => {
                                  const start = Math.max(0, i - 5)
                                  const end = Math.min(arr.length, i + 5)
                                  const slice = arr.slice(start, end)
                                  return slice.reduce((a, b) => a + b, 0) / slice.length
                                }),
                                borderColor: 'rgb(255, 159, 64)',
                                borderWidth: 2,
                                fill: false,
                                tension: 0.4,
                                pointRadius: 0
                              }
                            ]
                          }}
                          options={{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                              legend: {
                                display: true,
                                position: 'top',
                                labels: { color: 'rgb(156, 163, 175)', font: { size: 11 } }
                              }
                            },
                            scales: {
                              y: {
                                beginAtZero: true,
                                max: 1,
                                title: {
                                  display: true,
                                  text: 'TTR (Type-Token Ratio)',
                                  color: 'rgb(156, 163, 175)',
                                  font: { weight: 'bold' }
                                },
                                ticks: { color: 'rgb(156, 163, 175)' },
                                grid: { color: 'rgba(156, 163, 175, 0.1)' }
                              },
                              x: {
                                title: {
                                  display: true,
                                  text: 'Segment Index',
                                  color: 'rgb(156, 163, 175)',
                                  font: { weight: 'bold' }
                                },
                                ticks: { color: 'rgb(156, 163, 175)' },
                                grid: { color: 'rgba(156, 163, 175, 0.1)' }
                              }
                            }
                          }}
                        />
                      </div>
                    )}
                    {selectedSpeaker.ttr?.insight && (
                      <div className="bg-gradient-to-r from-orange-50 to-yellow-50 dark:from-orange-900/20 dark:to-yellow-900/20 border border-orange-200 dark:border-orange-700 rounded-lg p-4 mt-4">
                        <div className="flex items-start gap-3">
                          <span className="text-2xl">💡</span>
                          <div className="flex-1">
                            <p className="text-sm font-semibold text-orange-900 dark:text-orange-100 mb-1">AI 분석 결과</p>
                            <p className="text-sm text-orange-800 dark:text-orange-200">
                              {selectedSpeaker.ttr.insight}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* 2. 정보량 */}
                <div>
                  <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2 border-b-2 border-purple-500 pb-2">
                    2. 정보량 (Information Content)
                  </h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                    낮은 유사도 = 높은 정보량, 높은 유사도 = 반복적인 내용
                  </p>
                  <div className="bg-bg-secondary dark:bg-bg-secondary-dark rounded-lg p-6">
                    <div className="grid grid-cols-2 gap-6">
                      <div className="text-center p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg">
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">평균 유사도</p>
                        <p className="text-4xl font-bold text-purple-600 dark:text-purple-400">
                          {selectedSpeaker.information_content?.avg_similarity?.toFixed(3) || 'N/A'}
                        </p>
                      </div>
                      <div className="text-center p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg">
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">정보 점수</p>
                        <p className="text-4xl font-bold text-yellow-600 dark:text-yellow-400">
                          {selectedSpeaker.information_content?.information_score?.toFixed(3) || 'N/A'}
                        </p>
                      </div>
                    </div>
                    {selectedSpeaker.information_content?.insight && (
                      <div className="bg-gradient-to-r from-purple-50 to-yellow-50 dark:from-purple-900/20 dark:to-yellow-900/20 border border-purple-200 dark:border-purple-700 rounded-lg p-4 mt-4">
                        <div className="flex items-start gap-3">
                          <span className="text-2xl">💡</span>
                          <div className="flex-1">
                            <p className="text-sm font-semibold text-purple-900 dark:text-purple-100 mb-1">AI 분석 결과</p>
                            <p className="text-sm text-purple-800 dark:text-purple-200">
                              {selectedSpeaker.information_content.insight}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* 3. 문장 확률 */}
                <div>
                  <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2 border-b-2 border-teal-500 pb-2">
                    3. 문장 확률 (Sentence Probability)
                  </h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                    낮은 확률 = 비정상적 패턴, 높은 이상치 비율 = 예측 불가능
                  </p>
                  <div className="bg-bg-secondary dark:bg-bg-secondary-dark rounded-lg p-6">
                    {!selectedSpeaker.sentence_probability ? (
                      <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded-lg p-6 text-center">
                        <span className="text-4xl mb-3 block">📊</span>
                        <p className="text-lg font-semibold text-yellow-900 dark:text-yellow-100 mb-2">
                          데이터 없음
                        </p>
                        <p className="text-sm text-yellow-800 dark:text-yellow-200">
                          문장 확률 분석 데이터가 없습니다.
                        </p>
                      </div>
                    ) : (
                      <>
                        <div className="grid grid-cols-2 gap-6">
                          <div className="text-center p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg">
                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">평균 확률</p>
                            <p className="text-4xl font-bold text-teal-600 dark:text-teal-400">
                              {selectedSpeaker.sentence_probability?.avg_probability?.toFixed(3) || '0.000'}
                            </p>
                          </div>
                          <div className="text-center p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg">
                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">이상치 비율</p>
                            <p className="text-4xl font-bold text-red-600 dark:text-red-400">
                              {selectedSpeaker.sentence_probability?.outlier_ratio?.toFixed(3) || '0.000'}
                            </p>
                          </div>
                        </div>
                        {selectedSpeaker.sentence_probability?.total_sentences < 5 && (
                          <div className="mt-3 text-center text-xs text-yellow-600 dark:text-yellow-400">
                            ⚠️ 문장 수가 적어 정확도가 낮을 수 있습니다 ({selectedSpeaker.sentence_probability.total_sentences}개 문장)
                          </div>
                        )}
                      </>
                    )}
                    {selectedSpeaker.sentence_probability?.insight && (
                      <div className="bg-gradient-to-r from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20 border border-teal-200 dark:border-teal-700 rounded-lg p-4 mt-4">
                        <div className="flex items-start gap-3">
                          <span className="text-2xl">💡</span>
                          <div className="flex-1">
                            <p className="text-sm font-semibold text-teal-900 dark:text-teal-100 mb-1">AI 분석 결과</p>
                            <p className="text-sm text-teal-800 dark:text-teal-200">
                              {selectedSpeaker.sentence_probability.insight}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* 4. PPL (Perplexity) */}
                <div>
                  <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2 border-b-2 border-red-500 pb-2">
                    4. Perplexity (PPL)
                  </h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                    낮은 PPL = 유창한 흐름, 높은 PPL = 주제 전환 또는 예측 불가능
                  </p>
                  <div className="bg-bg-secondary dark:bg-bg-secondary-dark rounded-lg p-6">
                    {!selectedSpeaker.perplexity ? (
                      <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded-lg p-6 text-center">
                        <span className="text-4xl mb-3 block">⚠️</span>
                        <p className="text-lg font-semibold text-yellow-900 dark:text-yellow-100 mb-2">
                          Perplexity 데이터 없음
                        </p>
                        <p className="text-sm text-yellow-800 dark:text-yellow-200">
                          화자의 발화가 부족하여 PPL 계산이 불가능합니다. (최소 3개 문장 필요)
                        </p>
                      </div>
                    ) : (
                      <>
                        <div className="grid grid-cols-2 gap-6 mb-6">
                          <div className="text-center p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg">
                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">평균 PPL</p>
                            <p className="text-4xl font-bold text-red-600 dark:text-red-400">
                              {selectedSpeaker.perplexity?.ppl_avg?.toFixed(2) || '0.00'}
                            </p>
                          </div>
                          <div className="text-center p-4 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg">
                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">표준편차</p>
                            <p className="text-4xl font-bold text-blue-600 dark:text-blue-400">
                              {selectedSpeaker.perplexity?.ppl_std?.toFixed(2) || '0.00'}
                            </p>
                          </div>
                        </div>
                      </>
                    )}

                    {selectedSpeaker.perplexity?.ppl_values && selectedSpeaker.perplexity.ppl_values.length > 0 && (
                      <div style={{ height: '350px' }}>
                        <Line
                          data={{
                            labels: selectedSpeaker.perplexity.ppl_values.map((v, i) => i + 1),
                            datasets: [
                              {
                                label: 'Original PPL',
                                data: selectedSpeaker.perplexity.ppl_values.map(v => v.ppl),
                                borderColor: 'rgba(255, 99, 132, 0.3)',
                                backgroundColor: 'rgba(255, 99, 132, 0.1)',
                                fill: true,
                                tension: 0.4,
                                borderWidth: 1,
                                pointRadius: 0
                              },
                              {
                                label: 'Moving Avg (5)',
                                data: selectedSpeaker.perplexity.ppl_values.map((v, i, arr) => {
                                  const start = Math.max(0, i - 2)
                                  const end = Math.min(arr.length, i + 3)
                                  const slice = arr.slice(start, end).map(item => item.ppl)
                                  return slice.reduce((a, b) => a + b, 0) / slice.length
                                }),
                                borderColor: 'rgb(255, 99, 132)',
                                borderWidth: 2.5,
                                fill: false,
                                tension: 0.4,
                                pointRadius: 0
                              }
                            ]
                          }}
                          options={{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                              legend: {
                                display: true,
                                position: 'top',
                                labels: { color: 'rgb(156, 163, 175)', font: { size: 11 } }
                              }
                            },
                            scales: {
                              y: {
                                beginAtZero: true,
                                title: {
                                  display: true,
                                  text: 'Perplexity (PPL)',
                                  color: 'rgb(156, 163, 175)',
                                  font: { weight: 'bold' }
                                },
                                ticks: { color: 'rgb(156, 163, 175)' },
                                grid: { color: 'rgba(156, 163, 175, 0.1)' }
                              },
                              x: {
                                title: {
                                  display: true,
                                  text: 'Segment Index',
                                  color: 'rgb(156, 163, 175)',
                                  font: { weight: 'bold' }
                                },
                                ticks: { color: 'rgb(156, 163, 175)' },
                                grid: { color: 'rgba(156, 163, 175, 0.1)' }
                              }
                            }
                          }}
                        />
                      </div>
                    )}
                    {selectedSpeaker.perplexity?.insight && (
                      <div className="bg-gradient-to-r from-red-50 to-pink-50 dark:from-red-900/20 dark:to-pink-900/20 border border-red-200 dark:border-red-700 rounded-lg p-4 mt-4">
                        <div className="flex items-start gap-3">
                          <span className="text-2xl">💡</span>
                          <div className="flex-1">
                            <p className="text-sm font-semibold text-red-900 dark:text-red-100 mb-1">AI 분석 결과</p>
                            <p className="text-sm text-red-800 dark:text-red-200">
                              {selectedSpeaker.perplexity.insight}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
