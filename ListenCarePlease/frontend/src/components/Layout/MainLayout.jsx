import React from 'react'
import Sidebar from './Sidebar'
import TopBar from './TopBar'

export default function MainLayout({ children }) {
  return (
    <div className="flex h-screen bg-bg-primary dark:bg-bg-primary-dark overflow-hidden">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        {/* Top Bar */}
        <TopBar />

        {/* Content */}
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
