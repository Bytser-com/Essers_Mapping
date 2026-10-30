import { useInRouterContext, useNavigate } from 'react-router-dom'
import {
  AI_STATUS_LABELS,
  STATUS_LABELS,
  formatUploadedAt,
  proposalPath,
  type AiStatus,
  type Proposal,
  type ProposalStatus,
} from '../services/proposals'

type ProposalTableProps = {
  proposals: Proposal[]
}

// All sizes and colours below come from the Figma file "IT-Project Essers",
// frame "01 · Home" → "Lijst – proposals" (node 317:72) and its components.

// Label component variants (Figma "Label": Donker / Grijs / Omlijnd / Stippel).
type LabelStyle = 'dark' | 'grey' | 'outlined' | 'dotted'

const LABEL_STYLES: Record<LabelStyle, string> = {
  dark: 'bg-[#1c1c1f] text-white',
  grey: 'bg-[#a1a1ab] text-white',
  outlined: 'border border-[#1c1c1f] bg-white text-[#1c1c1f]',
  dotted: 'border border-dashed border-[#6b6b73] bg-white text-[#6b6b73]',
}

const STATUS_LABEL_STYLE: Record<ProposalStatus, LabelStyle> = {
  AI_GENERATING: 'outlined',
  READY_FOR_REVIEW: 'dark',
  IN_REVIEW: 'outlined',
  AI_CHECKING_REVIEW: 'outlined',
  RETURNED: 'dotted',
}

const AI_STATUS_LABEL_STYLE: Record<AiStatus, LabelStyle> = {
  RUNNING: 'grey',
  FAILED: 'dark',
}

// Column widths 220 / 80 / 170 / 213 / 150 px with a 12 px gap; the row has 16 px
// side padding. Each cell's width includes its padding (border-box).
const FIRST_CELL = 'w-[248px] pl-4 pr-3' // 16 + 220 + 12
const VERSION_CELL = 'w-[92px] pr-3' // 80 + 12
const DATE_CELL = 'w-[182px] pr-3' // 170 + 12
const STATUS_CELL = 'w-[225px] pr-3' // 213 + 12
const AI_CELL = 'w-[162px] pr-3' // 150 + 12
const ACTION_CELL = 'pr-4 text-right' // rest of the width

const HEADER_TEXT =
  "py-[10px] text-left align-middle font-['Inter',sans-serif] text-[11px] font-bold tracking-[0.66px] text-[#6b6b73]"
const BODY_CELL = 'py-[13px] align-middle'

function Label({ style, children }: { style: LabelStyle; children: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-[9px] py-[3px] leading-[normal] font-['Inter',sans-serif] text-[12px] font-medium whitespace-nowrap ${LABEL_STYLES[style]}`}
    >
      {children}
    </span>
  )
}

function AiStatusCell({ status }: { status: AiStatus | null }) {
  if (!status) return <span className="text-[13px] text-[#6b6b73]">—</span>
  return <Label style={AI_STATUS_LABEL_STYLE[status]}>{AI_STATUS_LABELS[status]}</Label>
}

// Figma "Knop": Secundair when enabled, Uitgeschakeld when disabled.
const OPEN_BUTTON =
  'rounded-[8px] border border-[#e3e3e8] bg-white px-4 py-[10px] text-[14px] leading-[normal] font-semibold text-[#1c1c1f] hover:bg-[#f4f4f6] disabled:cursor-not-allowed disabled:border-0 disabled:bg-[#e3e3e8] disabled:text-[#a1a1ab]'

// "Openen" goes to /proposals/<customer>. Inside the app this uses the router (no page
// reload); without a router (e.g. a component test of Home) it is a normal page load.
function OpenButton({ proposal }: { proposal: Proposal }) {
  const inRouter = useInRouterContext()
  if (inRouter) return <RouterOpenButton proposal={proposal} />
  return (
    <button
      type="button"
      disabled={!proposal.can_open}
      onClick={() => window.location.assign(proposalPath(proposal))}
      className={OPEN_BUTTON}
    >
      Openen
    </button>
  )
}

function RouterOpenButton({ proposal }: { proposal: Proposal }) {
  const navigate = useNavigate()
  return (
    <button
      type="button"
      disabled={!proposal.can_open}
      onClick={() => navigate(proposalPath(proposal))}
      className={OPEN_BUTTON}
    >
      Openen
    </button>
  )
}

// Table of proposals (Home page). Only shows data; ProposalOverview loads it.
function ProposalTable({ proposals }: ProposalTableProps) {
  return (
    <div className="overflow-hidden rounded-[12px] border border-[#e3e3e8] bg-white">
      <table className="w-full table-fixed border-collapse leading-[normal] font-['Inter',sans-serif] text-[13px] text-[#1c1c1f]">
        <thead className="border-b border-[#e3e3e8] bg-[#f4f4f6]">
          <tr>
            <th className={`${FIRST_CELL} ${HEADER_TEXT}`}>KLANT</th>
            <th className={`${VERSION_CELL} ${HEADER_TEXT}`}>VERSIE</th>
            <th className={`${DATE_CELL} ${HEADER_TEXT}`}>GEÜPLOAD OP</th>
            <th className={`${STATUS_CELL} ${HEADER_TEXT}`}>STATUS</th>
            <th className={`${AI_CELL} ${HEADER_TEXT}`}>AI-STATUS</th>
            <th className={`${ACTION_CELL} ${HEADER_TEXT} text-right`}>ACTIE</th>
          </tr>
        </thead>
        <tbody>
          {proposals.map((proposal) => (
            <tr key={proposal.id} className="border-b border-[#e3e3e8] last:border-b-0">
              <td className={`${FIRST_CELL} ${BODY_CELL} truncate font-semibold`}>{proposal.customer}</td>
              <td className={`${VERSION_CELL} ${BODY_CELL}`}>v{proposal.version}</td>
              <td className={`${DATE_CELL} ${BODY_CELL} whitespace-nowrap`}>
                {formatUploadedAt(proposal.uploaded_at)}
              </td>
              <td className={`${STATUS_CELL} ${BODY_CELL}`}>
                <Label style={STATUS_LABEL_STYLE[proposal.status]}>{STATUS_LABELS[proposal.status]}</Label>
              </td>
              <td className={`${AI_CELL} ${BODY_CELL}`}>
                <AiStatusCell status={proposal.ai_status} />
              </td>
              <td className={`${ACTION_CELL} ${BODY_CELL}`}>
                <OpenButton proposal={proposal} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ProposalTable
