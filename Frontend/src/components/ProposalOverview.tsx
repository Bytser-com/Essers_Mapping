import { useEffect } from 'react'
import ProposalTable from './ProposalTable'
import { POLL_INTERVAL_MS } from '../services/proposals'
import { useHomeStore } from '../stores/homeStore'

// "Proposals" section of the Home page: loads the list and shows it in a table.
function ProposalOverview() {
  const proposalList = useHomeStore((state) => state.proposalList)
  const loading = useHomeStore((state) => state.loading)
  const error = useHomeStore((state) => state.error)
  const waitUntil = useHomeStore((state) => state.waitUntil)
  const fetchProposals = useHomeStore((state) => state.fetchProposals)

  // Load the list when the page opens
  useEffect(() => {
    void fetchProposals()
  }, [fetchProposals])

  // While the AI is busy ("Bezig") or right after an upload, refresh quietly so the status updates by itself.
  const aiBusy = proposalList?.proposals.some((proposal) => proposal.ai_status === 'RUNNING') ?? false
  useEffect(() => {
    if (!aiBusy && Date.now() >= waitUntil) return
    const timer = setTimeout(() => void fetchProposals(true), POLL_INTERVAL_MS)
    return () => clearTimeout(timer)
  }, [aiBusy, waitUntil, proposalList, fetchProposals])

  return (
    <section data-testid="proposal-overview" className="flex flex-col gap-4">
      <div className="flex items-center gap-2 leading-[normal]">
        <h2 className="font-['Montserrat',sans-serif] text-[16px] font-bold text-[#1c1c1f]">Proposals</h2>
        {proposalList && (
          <span
            data-testid="proposal-count"
            className="rounded-full bg-[#a1a1ab] px-[9px] py-[3px] font-['Inter',sans-serif] text-[12px] font-medium text-white"
          >
            {proposalList.total}
          </span>
        )}
      </div>

      {loading && (
        <div className="rounded-[12px] border border-[#e3e3e8] bg-white px-4 py-6 font-['Inter',sans-serif] text-[13px] text-[#6b6b73]">
          Proposals laden…
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-center justify-between gap-4 rounded-[12px] border border-[#1c1c1f] bg-[#fee2e2] px-4 py-[13px] font-['Inter',sans-serif] text-[13px] text-[#1c1c1f]"
        >
          <span>De proposals konden niet geladen worden.</span>
          <button
            type="button"
            onClick={() => void fetchProposals()}
            className="rounded-[8px] border border-[#1c1c1f] bg-white px-4 py-[10px] text-[14px] leading-[normal] font-semibold text-[#1c1c1f] hover:bg-[#f4f4f6]"
          >
            Opnieuw proberen
          </button>
        </div>
      )}

      {!loading && proposalList && proposalList.proposals.length === 0 && (
        <div className="rounded-[12px] border border-[#e3e3e8] bg-white px-4 py-6 font-['Inter',sans-serif] text-[13px] text-[#6b6b73]">
          Er zijn nog geen proposals. Upload een interface om te beginnen.
        </div>
      )}

      {!loading && proposalList && proposalList.proposals.length > 0 && (
        <ProposalTable proposals={proposalList.proposals} />
      )}
    </section>
  )
}

export default ProposalOverview