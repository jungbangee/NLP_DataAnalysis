import React from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import ProtectedRoute from './components/ProtectedRoute'
import MainLayout from './components/Layout/MainLayout'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import OAuthCallbackPage from './pages/OAuthCallbackPage'
import DashboardPageNew from './pages/DashboardPageNew'
import UploadPage from './pages/UploadPage'
import ProcessingPage from './pages/ProcessingPage'
import SpeakerInfoConfirmPage from './pages/SpeakerInfoConfirmPage'
import TaggingAnalyzingPage from './pages/TaggingAnalyzingPage'
import TaggingPageNew from './pages/TaggingPageNew'
import ResultPageNew from './pages/ResultPageNew'
import RagPage from './pages/RagPage'
import TodoPage from './pages/TodoPage'
import EfficiencyPage from './pages/EfficiencyPage'
import TestLatestPage from './pages/TestLatestPage'

function App() {
  return (
    <ThemeProvider>
      <Router future={{
        v7_relativeSplatPath: true,
        v7_startTransition: true
      }}>
        <AuthProvider>
          <Routes>
            {/* 공개 라우트 */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/oauth/callback" element={<OAuthCallbackPage />} />
            <Route path="/test-latest" element={<TestLatestPage />} />

            {/* 보호된 라우트 - MainLayout 적용 */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <DashboardPageNew />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/upload"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <UploadPage />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/processing/:fileId"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <ProcessingPage />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/confirm/:fileId"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <SpeakerInfoConfirmPage />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/analyzing/:fileId"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <TaggingAnalyzingPage />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/tagging/:fileId"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <TaggingPageNew />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/result/:fileId"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <ResultPageNew />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/rag/:fileId"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <RagPage />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/todo/:fileId"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <TodoPage />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/efficiency/:fileId"
              element={
                <ProtectedRoute>
                  <MainLayout>
                    <EfficiencyPage />
                  </MainLayout>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </Router>
    </ThemeProvider>
  )
}

export default App
