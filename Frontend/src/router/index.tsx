import { createBrowserRouter } from 'react-router-dom'
import App from '../App'
import Home from '../pages/Home'
import VersionControl from '../pages/VersionControl'
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
      {
        path: 'version-control',
        element: <VersionControl />,
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