import { createBrowserRouter } from 'react-router-dom'
import App from '../App'
import Home from '../pages/Home'
import ProposalPage from '../pages/ProposalPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      {
        index: true,
        element: <Home />,
      },
    ],
  },
  {
    path: '/proposals/:company',
    element: <App />,
    children: [
      {
        index: true,
        element: <ProposalPage />,
      },
    ],
  },
])

export default router