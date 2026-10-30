import { useEffect, useState } from 'react'
import ProposalTable from './ProposalTable'
import { POLL_INTERVAL_MS, fetchProposals, type ProposalList } from '../services/proposals'

type ProposalOverviewProps = {
  // Tests pass a fake loader and a short interval; the app uses the real API.
  loadProposals?: (signal: AbortSignal) => Promise<ProposalList>
  pollIntervalMs?: number
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'loaded'; data: ProposalList }

// "Proposals" section of the Home page: loads the list and shows it in a table.
function ProposalOverview({
  loadProposals = fetchProposals,
  pollIntervalMs = POLL_INTERVAL_MS,
}: ProposalOverviewProps) {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    loadProposals(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ kind: 'loaded', data })
      })
      .catch(() => {
        if (controller.signal.aborted) return
        // A failed background refresh keeps the table that is already shown.
        // (A new object, so polling keeps going and tries again later.)
        setState((previous) => (previous.kind === 'loaded' ? { ...previous } : { kind: 'error' }))
      })
    // Cancel the request when the page is left before it finishes.
    return () => controller.abort()
  }, [loadProposals, attempt])

  // While the AI is busy ("Bezig"), refresh quietly so the status updates by itself.
  const aiBusy =
    state.kind === 'loaded' && state.data.proposals.some((proposal) => proposal.ai_status === 'RUNNING')
  useEffect(() => {
    if (!aiBusy) return
    const timer = setTimeout(() => setAttempt((count) => count + 1), pollIntervalMs)
    return () => clearTimeout(timer)
  }, [aiBusy, pollIntervalMs, state])

  function retry() {
    setState({ kind: 'loading' })
    setAttempt((count) => count + 1)
  }

  return (
    <section data-testid="proposal-overview" className="flex flex-col gap-4">
      <div className="flex items-center gap-2 leading-[normal]">
        <h2 className="font-['Montserrat',sans-serif] text-[16px] font-bold text-[#1c1c1f]">Proposals</h2>
        {state.kind === 'loaded' && (
          <span
            data-testid="proposal-count"
            className="rounded-full bg-[#a1a1ab] px-[9px] py-[3px] font-['Inter',sans-serif] text-[12px] font-medium text-white"
          >
            {state.data.total}
          </span>
        )}
      </div>

      {state.kind === 'loading' && (
        <div className="rounded-[12px] border border-[#e3e3e8] bg-white px-4 py-6 font-['Inter',sans-serif] text-[13px] text-[#6b6b73]">
          Proposals laden…
        </div>
      )}

      {state.kind === 'error' && (
        <div
          role="alert"
          className="flex items-center justify-between gap-4 rounded-[12px] border border-[#e3e3e8] bg-white px-4 py-[13px] font-['Inter',sans-serif] text-[13px] text-[#1c1c1f]"
        >
          <span>De proposals konden niet geladen worden.</span>
          <button
            type="button"
            onClick={retry}
            className="rounded-[8px] border border-[#e3e3e8] bg-white px-4 py-[10px] text-[14px] leading-[normal] font-semibold text-[#1c1c1f] hover:bg-[#f4f4f6]"
          >
            Opnieuw proberen
          </button>
        </div>
      )}

      {state.kind === 'loaded' && state.data.proposals.length === 0 && (
        <div className="rounded-[12px] border border-[#e3e3e8] bg-white px-4 py-6 font-['Inter',sans-serif] text-[13px] text-[#6b6b73]">
          Er zijn nog geen proposals. Upload een interface om te beginnen.
        </div>
      )}

      {state.kind === 'loaded' && state.data.proposals.length > 0 && (
        <ProposalTable proposals={state.data.proposals} />
      )}
    </section>
  )
}

export default ProposalOverview
