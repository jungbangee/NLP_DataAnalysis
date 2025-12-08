import React, { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { setTokens } from '../utils/auth'
import { useAuth } from '../contexts/AuthContext'
import { getCurrentUser } from '../services/authService'

const OAuthCallbackPage = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { setIsAuthenticated, setUser } = useAuth()

  useEffect(() => {
    const handleOAuthCallback = async () => {
      const accessToken = searchParams.get('access_token')
      const refreshToken = searchParams.get('refresh_token')

      if (accessToken && refreshToken) {
        try {
          // 토큰 저장
          setTokens(accessToken, refreshToken)

          // 사용자 정보 가져오기
          const userData = await getCurrentUser(accessToken)
          setUser(userData)
          setIsAuthenticated(true)

          // 메인 페이지로 이동
          navigate('/', { replace: true })
        } catch (error) {
          console.error('OAuth 콜백 처리 실패:', error)
          navigate('/login', { replace: true })
        }
      } else {
        // 토큰이 없으면 로그인 페이지로
        navigate('/login', { replace: true })
      }
    }

    handleOAuthCallback()
  }, [searchParams, navigate, setIsAuthenticated, setUser])

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent mb-4"></div>
        <p className="text-gray-600">로그인 처리 중...</p>
      </div>
    </div>
  )
}

export default OAuthCallbackPage
