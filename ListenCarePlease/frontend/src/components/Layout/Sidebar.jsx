import React, { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { getRecentFiles, getProcessingFilesFromDashboard, deleteAudioFile } from '../../services/api'

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuth()

  const [recentFiles, setRecentFiles] = useState([])
  const [processingFiles, setProcessingFiles] = useState([])
  const [isLoading, setIsLoading] = useState(true)

  // 파일 목록 로드
  useEffect(() => {
    if (user?.id) {
      loadFiles()
      // 5초마다 처리 중인 파일 업데이트
      const interval = setInterval(loadFiles, 5000)
      return () => clearInterval(interval)
    }
  }, [user])

  const loadFiles = async () => {
    try {
      const [recent, processing] = await Promise.all([
        getRecentFiles(user.id, 10),
        getProcessingFilesFromDashboard(user.id)
      ])
      setRecentFiles(recent.filter(file => file.status !== 'processing'))
      setProcessingFiles(processing)
    } catch (error) {
      console.error('파일 목록 로드 실패:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileClick = (file) => {
    if (file.status === 'processing') {
      const fileId = file.file_uuid || file.id
      navigate(`/processing/${fileId}`)
    } else if (file.status === 'completed') {
      // 단계별 이동 로직
      if (!file.has_user_confirmation) {
        // 1. 화자 정보 확정 전 -> 확정 페이지로
        navigate(`/confirm/${file.id}`)
      } else if (!file.has_tagging) {
        // 2. 화자 정보 확정 후, 태깅 완료 전 -> 태깅 페이지로
        navigate(`/tagging/${file.id}`)
      } else {
        // 3. 모든 과정 완료 -> 결과 페이지로
        navigate(`/result/${file.id}`)
      }
    }
  }

  const handleNewUpload = () => {
    navigate('/upload')
  }

  const handleDeleteFile = async (e, fileId, filename) => {
    e.stopPropagation() // 파일 클릭 이벤트 방지

    if (!confirm(`"${filename}" 파일을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) {
      return
    }

    try {
      await deleteAudioFile(fileId)
      alert('파일이 삭제되었습니다.')
      loadFiles() // 목록 새로고침

      // 삭제된 파일 페이지에 있다면 대시보드로 이동
      if (location.pathname.includes(`/result/${fileId}`) ||
        location.pathname.includes(`/processing/${fileId}`)) {
        navigate('/')
      }
    } catch (error) {
      console.error('파일 삭제 실패:', error)
      alert('파일 삭제에 실패했습니다.')
    }
  }

  return (
    <div className="w-64 h-screen bg-bg-secondary dark:bg-bg-secondary-dark border-r border-bg-accent/30 flex flex-col">
      {/* 로고 */}
      <div className="p-4 border-b border-bg-accent/30">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <span className="text-2xl">🎧</span>
          ListenCarePlease
        </h1>
      </div>

      {/* 새 파일 업로드 버튼 */}
      <div className="p-4">
        <button
          onClick={handleNewUpload}
          className="w-full py-2.5 px-4 bg-accent-sage dark:bg-accent-teal hover:opacity-90 text-gray-900 dark:text-white rounded-lg font-medium transition-all flex items-center justify-center gap-2"
        >
          <span className="text-xl">+</span>
          새 파일 업로드
        </button>
      </div>

      {/* 파일 목록 */}
      <div className="flex-1 overflow-y-auto">
        {/* 처리 중인 파일 */}
        {processingFiles.length > 0 && (
          <div className="px-4 py-2">
            <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
              처리 중
            </h3>
            {processingFiles.map((file) => (
              <div
                key={file.id}
                className="relative group mb-2"
              >
                <button
                  onClick={() => handleFileClick(file)}
                  className="w-full text-left p-3 rounded-lg hover:bg-bg-tertiary dark:hover:bg-bg-tertiary-dark transition-colors"
                >
                  <div className="flex items-start gap-2">
                    <span className="text-accent-orange mt-0.5">◉</span>
                    <div className="flex-1 min-w-0 pr-6">
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                        {file.original_filename}
                      </p>
                      <p className="text-xs text-accent-orange">
                        진행 중 {file.progress || 0}%
                      </p>
                    </div>
                  </div>
                </button>
                <button
                  onClick={(e) => handleDeleteFile(e, file.id, file.original_filename)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-all"
                  title="삭제"
                >
                  <svg className="w-4 h-4 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 최근 파일 */}
        <div className="px-4 py-2">
          <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
            최근 파일
          </h3>
          {isLoading ? (
            <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
              로딩 중...
            </div>
          ) : recentFiles.length === 0 ? (
            <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
              파일이 없습니다
            </div>
          ) : (
            recentFiles.map((file) => (
              <div
                key={file.id}
                className="relative group mb-2"
              >
                <button
                  onClick={() => handleFileClick(file)}
                  className={`w-full text-left p-3 rounded-lg transition-colors ${location.pathname.includes(`/result/${file.id}`)
                    ? 'bg-bg-tertiary dark:bg-bg-tertiary-dark'
                    : 'hover:bg-bg-tertiary dark:hover:bg-bg-tertiary-dark'
                    }`}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-accent-green mt-0.5">✓</span>
                    <div className="flex-1 min-w-0 pr-6">
                      <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                        {file.original_filename}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {new Date(file.created_at).toLocaleDateString('ko-KR', {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </p>
                    </div>
                  </div>
                </button>
                <button
                  onClick={(e) => handleDeleteFile(e, file.id, file.original_filename)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-all"
                  title="삭제"
                >
                  <svg className="w-4 h-4 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 하단 네비게이션 */}
      <div className="p-4 border-t border-bg-accent/30 space-y-1">
        <button
          onClick={() => navigate('/')}
          className={`w-full text-left px-3 py-2 rounded-lg transition-colors flex items-center gap-2 ${location.pathname === '/'
            ? 'bg-bg-tertiary dark:bg-bg-tertiary-dark text-gray-900 dark:text-white'
            : 'text-gray-600 dark:text-gray-400 hover:bg-bg-tertiary dark:hover:bg-bg-tertiary-dark'
            }`}
        >
          <span>🏠</span>
          <span className="text-sm font-medium">메인</span>
        </button>
      </div>
    </div>
  )
}
