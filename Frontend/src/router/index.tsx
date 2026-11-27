import { createBrowserRouter } from 'react-router-dom'
import App from '../App'
import Home from '../pages/Home'
import VersionControl from '../pages/VersionControl'
import ProposalPage from '../pages/ProposalPage'
import ProposalResetPage from '../pages/ProposalResetPage'
import PackageVersions from '../pages/PackageVersions'

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
      {
        path: 'package-versions/:company/:packageType',
        element: <PackageVersions />,
      },
      {
        path: 'proposals/reset',
        element: <ProposalResetPage />,
      },
    ],
  },
  {
    path: '/proposals/reset',
    element: <App />,
    children: [
      {
        index: true,
        element: <ProposalResetPage />,
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