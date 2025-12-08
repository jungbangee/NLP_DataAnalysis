import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login, getGoogleLoginUrl, getKakaoLoginUrl, getCurrentUser } from '../services/authService'
import { getAccessToken } from '../utils/auth'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/ThemeContext'

const LoginPage = () => {
  const navigate = useNavigate()
  const { setUser, setIsAuthenticated } = useAuth()
  const { isDark, toggleTheme } = useTheme()

  const [formData, setFormData] = useState({
    email: '',
    password: ''
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    })
    setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      await login(formData.email, formData.password)

      // 로그인 성공 - 사용자 정보 가져오기
      const token = getAccessToken()
      const userData = await getCurrentUser(token)
      setUser(userData)
      setIsAuthenticated(true)
      navigate('/')
    } catch (err) {
      console.error('로그인 실패:', err)
      setError(err.response?.data?.detail || '로그인에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const handleOAuthLogin = (provider) => {
    if (provider === 'google') {
      window.location.href = getGoogleLoginUrl()
    } else if (provider === 'kakao') {
      window.location.href = getKakaoLoginUrl()
    }
  }

  return (
    <div className="min-h-screen bg-bg-primary dark:bg-bg-primary-dark flex items-center justify-center p-4 transition-colors duration-300">
      <div className="w-full max-w-md">
        {/* 테마 토글 버튼 */}
        <div className="flex justify-end mb-4">
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg bg-bg-tertiary dark:bg-bg-tertiary-dark hover:opacity-80 transition-all"
            title={isDark ? '라이트 모드' : '다크 모드'}
          >
            {isDark ? (
              <svg className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-5 h-5 text-gray-700" fill="currentColor" viewBox="0 0 20 20">
                <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
              </svg>
            )}
          </button>
        </div>

        {/* 로고 및 제목 */}
        <div className="text-center mb-8">
          <div className="inline-block p-3 bg-accent-sage dark:bg-accent-teal rounded-2xl mb-4">
            <span className="text-4xl">🎧</span>
          </div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">ListenCarePlease</h1>
          <p className="text-gray-600 dark:text-gray-400">발화자 자동 태깅 및 요약 서비스</p>
        </div>

        {/* 로그인 폼 */}
        <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-3xl shadow-xl p-8 border border-bg-accent/30">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">로그인</h2>

          {error && (
            <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-xl text-red-600 dark:text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* 이메일 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                이메일
              </label>
              <input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                required
                className="w-full px-4 py-3 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark text-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-accent-sage dark:focus:ring-accent-teal focus:border-transparent transition"
                placeholder="your@email.com"
              />
            </div>

            {/* 비밀번호 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                비밀번호
              </label>
              <input
                type="password"
                name="password"
                value={formData.password}
                onChange={handleChange}
                required
                className="w-full px-4 py-3 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark text-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-accent-sage dark:focus:ring-accent-teal focus:border-transparent transition"
                placeholder="••••••••"
              />
            </div>

            {/* 로그인 버튼 */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent-sage dark:bg-accent-teal text-gray-900 dark:text-white py-3 rounded-xl font-semibold hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '로그인 중...' : '로그인'}
            </button>
          </form>

          {/* 구분선 */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-bg-accent/30"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-4 bg-bg-tertiary dark:bg-bg-tertiary-dark text-gray-500 dark:text-gray-400">또는</span>
            </div>
          </div>

          {/* 소셜 로그인 */}
          <div className="space-y-3">
            {/* 구글 로그인 */}
            <button
              onClick={() => handleOAuthLogin('google')}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 border border-bg-accent/30 bg-bg-secondary dark:bg-bg-secondary-dark rounded-xl hover:opacity-80 transition"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              <span className="text-gray-900 dark:text-white font-medium">Google로 로그인</span>
            </button>

            {/* 카카오 로그인 */}
            <button
              onClick={() => handleOAuthLogin('kakao')}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-[#FEE500] rounded-xl hover:bg-[#FDD835] transition"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="#000000"
                  d="M12 3C6.486 3 2 6.262 2 10.29c0 2.584 1.707 4.858 4.286 6.203-.177.651-.664 2.438-.769 2.83-.124.465.172.46.358.334.134-.09 2.23-1.518 3.073-2.09.527.074 1.068.113 1.62.113 5.514 0 9.932-3.262 9.932-7.29C21.5 6.262 17.514 3 12 3z"
                />
              </svg>
              <span className="text-gray-800 font-medium">카카오로 로그인</span>
            </button>
          </div>

          {/* 회원가입 링크 */}
          <div className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
            계정이 없으신가요?{' '}
            <Link
              to="/register"
              className="text-accent-sage dark:text-accent-teal font-semibold hover:underline"
            >
              회원가입
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

export default LoginPage
