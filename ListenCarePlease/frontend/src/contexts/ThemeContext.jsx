import { createContext, useContext, useState, useEffect } from 'react'

const ThemeContext = createContext(undefined)

export const useTheme = () => {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error('useTheme must be used within ThemeProvider')
  }
  return context
}

export const ThemeProvider = ({ children }) => {
  const [isDark, setIsDark] = useState(() => {
    // 초기값을 함수로 설정하여 한 번만 실행되도록
    if (typeof window === 'undefined') return false

    const saved = localStorage.getItem('theme')
    if (saved === 'dark') return true
    if (saved === 'light') return false

    // 저장된 값이 없으면 시스템 설정 확인
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  // DOM 업데이트는 별도 useEffect로 처리
  useEffect(() => {
    const root = document.documentElement

    if (isDark) {
      root.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      root.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [isDark])

  const toggleTheme = () => {
    setIsDark(prev => !prev)
  }

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
