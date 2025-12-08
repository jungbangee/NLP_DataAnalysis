import axios from 'axios'
import { setTokens, getRefreshToken, removeTokens } from '../utils/auth'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// 회원가입
export const register = async (email, password, fullName) => {
  const response = await axios.post(`${API_BASE_URL}/api/v1/auth/register`, {
    email,
    password,
    full_name: fullName
  })
  return response.data
}

// 로그인
export const login = async (email, password) => {
  const response = await axios.post(`${API_BASE_URL}/api/v1/auth/login`, {
    email,
    password
  })

  const { access_token, refresh_token } = response.data
  setTokens(access_token, refresh_token)

  return response.data
}

// 토큰 갱신
export const refreshToken = async () => {
  const refresh = getRefreshToken()
  if (!refresh) {
    throw new Error('No refresh token')
  }

  const response = await axios.post(`${API_BASE_URL}/api/v1/auth/refresh`, {
    refresh_token: refresh
  })

  const { access_token, refresh_token } = response.data
  setTokens(access_token, refresh_token)

  return response.data
}

// 현재 사용자 정보 조회
export const getCurrentUser = async (accessToken) => {
  const response = await axios.get(`${API_BASE_URL}/api/v1/auth/me`, {
    headers: {
      Authorization: `Bearer ${accessToken}`
    }
  })
  return response.data
}

// 로그아웃
export const logout = async (accessToken) => {
  try {
    await axios.post(
      `${API_BASE_URL}/api/v1/auth/logout`,
      {},
      {
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
      }
    )
  } finally {
    removeTokens()
  }
}

// OAuth 로그인 URL
export const getGoogleLoginUrl = () => {
  return `${API_BASE_URL}/api/v1/auth/google/login`
}

export const getKakaoLoginUrl = () => {
  return `${API_BASE_URL}/api/v1/auth/kakao/login`
}
