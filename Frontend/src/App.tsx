import { Outlet } from 'react-router-dom'

function App() {
  return (
    <div className="min-h-screen bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
      <Outlet />
    </div>
  )
}

export default App
