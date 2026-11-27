import { useState, useEffect } from 'react'
import { useLocation, useInRouterContext } from 'react-router-dom'
import InterfaceUpload from '../components/InterfaceUpload'
import ProposalOverview from '../components/ProposalOverview'
import { useProposalStore, type ApprovalMessage } from '../stores/proposalStore'
import iconSuccess from '../assets/home/icon-success.svg'
import iconError from '../assets/home/icon-error.svg'

function RouterLocationListener({
  onLocationDeleteMessage,
  onLocationApprovalMessage,
}: {
  onLocationDeleteMessage: (msg: string) => void
  onLocationApprovalMessage: (msg: ApprovalMessage) => void
}) {
  const location = useLocation()
  useEffect(() => {
    const stateObj = location?.state as {
      deleteSuccessMessage?: string
      approvalMessage?: ApprovalMessage
    } | null
    if (stateObj?.deleteSuccessMessage) {
      onLocationDeleteMessage(stateObj.deleteSuccessMessage)
    }
    if (stateObj?.approvalMessage) {
      onLocationApprovalMessage(stateObj.approvalMessage)
    }
  }, [location, onLocationDeleteMessage, onLocationApprovalMessage])
  return null
}

function Home() {
  const storeDeleteMessage = useProposalStore((state) => state.deleteSuccessMessage)
  const clearDeleteSuccessMessage = useProposalStore((state) => state.clearDeleteSuccessMessage)

  const storeApprovalMessage = useProposalStore((state) => state.approvalMessage)
  const clearApprovalMessage = useProposalStore((state) => state.clearApprovalMessage)

  const [routerDeleteMessage, setRouterDeleteMessage] = useState<string | null>(null)
  const [routerApprovalMessage, setRouterApprovalMessage] = useState<ApprovalMessage | null>(null)

  const inRouter = useInRouterContext()

  const deleteMessage = storeDeleteMessage || routerDeleteMessage
  const approvalBanner = storeApprovalMessage || routerApprovalMessage

  function handleDismissDelete() {
    clearDeleteSuccessMessage()
    setRouterDeleteMessage(null)
    if (typeof window !== 'undefined' && window.history?.replaceState) {
      window.history.replaceState({}, '')
    }
  }

  function handleDismissApproval() {
    clearApprovalMessage()
    setRouterApprovalMessage(null)
    if (typeof window !== 'undefined' && window.history?.replaceState) {
      window.history.replaceState({}, '')
    }
  }

  return (
    <div data-testid="home-page" className="flex flex-col gap-4 px-8 py-7">
      {inRouter && (
        <RouterLocationListener
          onLocationDeleteMessage={setRouterDeleteMessage}
          onLocationApprovalMessage={setRouterApprovalMessage}
        />
      )}
      <div className="flex flex-col gap-[6px]">
        <h1 className="font-['Montserrat',sans-serif] text-[24px] font-bold">Home</h1>
        <p className="text-[13px] text-[#6b6b73]">
          Upload een interface van een klant. De AI maakt er een mapping proposal van.
        </p>
      </div>

      {deleteMessage && (
        <div
          role="status"
          data-testid="delete-success-banner"
          className="flex items-center justify-between gap-3 rounded-lg border border-[#1c1c1f] bg-white px-4 py-3"
        >
          <div className="flex items-center gap-3">
            <img src={iconSuccess} alt="" width={18} height={18} />
            <div className="flex flex-col gap-[2px]">
              <p className="text-[13px] font-semibold">Voorstel succesvol verwijderd.</p>
              <p className="text-[12px] text-[#6b6b73]">{deleteMessage}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleDismissDelete}
            className="cursor-pointer text-xs font-semibold text-[#6b6b73] hover:text-[#1c1c1f] px-2 py-1"
            aria-label="Melding sluiten"
          >
            ✕
          </button>
        </div>
      )}

      {approvalBanner && (
        <div
          role={approvalBanner.type === 'error' ? 'alert' : 'status'}
          data-testid={approvalBanner.type === 'error' ? 'approval-error-banner' : 'approval-success-banner'}
          className={`flex items-center justify-between gap-3 rounded-lg border bg-white px-4 py-3 ${
            approvalBanner.type === 'error' ? 'border-red bg-[#fee2e2]/40' : 'border-[#1c1c1f]'
          }`}
        >
          <div className="flex items-center gap-3">
            <img
              src={approvalBanner.type === 'error' ? iconError : iconSuccess}
              alt=""
              width={18}
              height={18}
            />
            <div className="flex flex-col gap-[2px]">
              <p className="text-[13px] font-semibold text-anthracite">{approvalBanner.title}</p>
              <p className="text-[12px] text-[#6b6b73]">{approvalBanner.message}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleDismissApproval}
            className="cursor-pointer text-xs font-semibold text-[#6b6b73] hover:text-[#1c1c1f] px-2 py-1"
            aria-label="Melding sluiten"
          >
            ✕
          </button>
        </div>
      )}

      <InterfaceUpload />
      <ProposalOverview />
    </div>
  )
}

export default Home