import React, { createContext, useContext, useState, useEffect } from 'react'
import { getAccessToken, isTokenExpired, removeTokens } from '../utils/auth'
import { getCurrentUser, refreshToken as refreshAuthToken, logout as apiLogout } from '../services/authService'

const AuthContext = createContext(null)

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  // 초기 로드 시 토큰 확인 및 사용자 정보 가져오기
  useEffect(() => {
    const initAuth = async () => {
      const token = getAccessToken()

      if (!token) {
        setLoading(false)
        return
      }

      // 토큰 만료 확인
      if (isTokenExpired(token)) {
        try {
          // 토큰 갱신 시도
          await refreshAuthToken()
          const newToken = getAccessToken()
          const userData = await getCurrentUser(newToken)
          setUser(userData)
          setIsAuthenticated(true)
        } catch (error) {
          console.error('토큰 갱신 실패:', error)
          removeTokens()
          setIsAuthenticated(false)
        }
      } else {
        // 토큰 유효 - 사용자 정보 가져오기
        try {
          const userData = await getCurrentUser(token)
          setUser(userData)
          setIsAuthenticated(true)
        } catch (error) {
          console.error('사용자 정보 조회 실패:', error)
          removeTokens()
          setIsAuthenticated(false)
        }
      }

      setLoading(false)
    }

    initAuth()
  }, [])

  const logout = async () => {
    try {
      const token = getAccessToken()
      if (token) {
        await apiLogout(token)
      }
    } catch (error) {
      console.error('Logout failed:', error)
    } finally {
      removeTokens()
      setUser(null)
      setIsAuthenticated(false)
    }
  }

  const value = {
    user,
    setUser,
    loading,
    isAuthenticated,
    setIsAuthenticated,
    logout
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
