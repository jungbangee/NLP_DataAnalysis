import React from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { useTheme } from '../../contexts/ThemeContext'
import { useNavigate } from 'react-router-dom'

export default function TopBar() {
  const { user, logout } = useAuth()
  const { isDark, toggleTheme } = useTheme()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="h-16 bg-bg-secondary dark:bg-bg-secondary-dark border-b border-bg-accent/30 flex items-center justify-between px-6">
      {/* 검색 영역 (향후 구현) */}
      <div className="flex-1">
        {/* <input
          type="text"
          placeholder="검색..."
          className="max-w-md px-4 py-2 rounded-lg border border-bg-accent/30 bg-bg-tertiary text-gray-900 dark:text-white"
        /> */}
      </div>

      {/* 우측 액션 */}
      <div className="flex items-center gap-4">
        {/* 테마 토글 */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg hover:bg-bg-tertiary dark:hover:bg-bg-tertiary-dark transition-colors"
          title={isDark ? '라이트 모드' : '다크 모드'}
        >
          {isDark ? (
            <svg className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"
                clipRule="evenodd"
              />
            </svg>
          ) : (
            <svg className="w-5 h-5 text-gray-700" fill="currentColor" viewBox="0 0 20 20">
              <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
            </svg>
          )}
        </button>

        {/* 사용자 정보 */}
        <div className="relative group">
          <button className="flex items-center gap-2 p-2 rounded-lg hover:bg-bg-tertiary dark:hover:bg-bg-tertiary-dark transition-colors">
            <div className="w-8 h-8 rounded-full bg-accent-sage dark:bg-accent-teal text-gray-900 dark:text-white flex items-center justify-center font-medium">
              {user?.full_name ? user.full_name[0] : (user?.email ? user.email[0].toUpperCase() : 'U')}
            </div>
            <span className="text-sm font-medium text-gray-900 dark:text-white hidden md:block">
              {user?.full_name || user?.email || 'User'}
            </span>
          </button>

          {/* 드롭다운 메뉴 */}
          <div className="absolute right-0 mt-2 w-48 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-lg shadow-lg border border-bg-accent/30 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all">
            <div className="py-1">
              <button
                onClick={handleLogout}
                className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-bg-accent/20"
              >
                로그아웃
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
