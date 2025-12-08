/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 배경색 시스템
        'bg-primary': '#F9F8F6',    // Light mode
        'bg-secondary': '#EFE9E3',
        'bg-tertiary': '#D9CFC7',
        'bg-accent': '#C9B59C',

        // Dark mode 배경색
        'bg-primary-dark': '#37353E',
        'bg-secondary-dark': '#2D2B34',
        'bg-tertiary-dark': '#413F48',
        'bg-accent-dark': '#4B4952',

        // 액센트 컬러 (버튼, 링크 등)
        accent: {
          blue: '#4A90E2',
          green: '#7AC943',
          orange: '#F5A623',
          red: '#E94B3C',
          teal: '#D4A89A',  // 다크 모드 선택 색상 (라이트 모드와 조화)
          sage: '#F2C9B3',  // 라이트 모드 선택 색상
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
