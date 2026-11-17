import { Outlet } from 'react-router-dom'
import Sidebar from './components/Sidebar'

function App() {
  return (
    <div className="flex min-h-screen bg-[#f4f4f6] text-[#1c1c1f]">
      <Sidebar />
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  )
}

export default App
