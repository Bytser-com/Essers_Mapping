import { useState, useEffect } from 'react'
import { useLocation, useInRouterContext } from 'react-router-dom'
import InterfaceUpload from '../components/InterfaceUpload'
import ProposalOverview from '../components/ProposalOverview'
import ApprovedNotices from '../components/ApprovedNotices'
import { useProposalStore } from '../stores/proposalStore'
import iconSuccess from '../assets/home/icon-success.svg'

function RouterLocationListener({ onLocationMessage }: { onLocationMessage: (msg: string) => void }) {
  const location = useLocation()
  useEffect(() => {
    const stateMsg = (location?.state as { deleteSuccessMessage?: string } | null)?.deleteSuccessMessage
    if (stateMsg) {
      onLocationMessage(stateMsg)
    }
  }, [location, onLocationMessage])
  return null
}

function Home() {
  const storeMessage = useProposalStore((state) => state.deleteSuccessMessage)
  const clearDeleteSuccessMessage = useProposalStore((state) => state.clearDeleteSuccessMessage)

  const [routerMessage, setRouterMessage] = useState<string | null>(null)
  const inRouter = useInRouterContext()

  const message = storeMessage || routerMessage

  function handleDismiss() {
    clearDeleteSuccessMessage()
    setRouterMessage(null)
    if (typeof window !== 'undefined' && window.history?.replaceState) {
      window.history.replaceState({}, '')
    }
  }

  return (
    <div data-testid="home-page" className="flex flex-col gap-4 px-8 py-7">
      {inRouter && <RouterLocationListener onLocationMessage={setRouterMessage} />}
      <div className="flex flex-col gap-[6px]">
        <h1 className="font-['Montserrat',sans-serif] text-[24px] font-bold">Home</h1>
        <p className="text-[13px] text-[#6b6b73]">
          Upload een interface van een klant. De AI maakt er een mapping proposal van.
        </p>
      </div>

      {message && (
        <div
          role="status"
          data-testid="delete-success-banner"
          className="flex items-center justify-between gap-3 rounded-lg border border-[#1c1c1f] bg-white px-4 py-3"
        >
          <div className="flex items-center gap-3">
            <img src={iconSuccess} alt="" width={18} height={18} />
            <div className="flex flex-col gap-[2px]">
              <p className="text-[13px] font-semibold">Voorstel succesvol verwijderd.</p>
              <p className="text-[12px] text-[#6b6b73]">{message}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleDismiss}
            className="cursor-pointer text-xs font-semibold text-[#6b6b73] hover:text-[#1c1c1f] px-2 py-1"
            aria-label="Melding sluiten"
          >
            ✕
          </button>
        </div>
      )}

      {inRouter && <ApprovedNotices />}

      <InterfaceUpload />
      <ProposalOverview />
    </div>
  )
}

export default Home