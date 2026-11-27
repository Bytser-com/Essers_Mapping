import { useNavigate } from 'react-router-dom'
import { useHomeStore } from '../stores/homeStore'
import iconSuccess from '../assets/home/icon-success.svg'

// Messages on Home after a proposal passed the AI review and became a mapping package
// (story IT2627T06-187). Needs the router for "Naar Version Control".
function ApprovedNotices() {
  const notices = useHomeStore((state) => state.approvedNotices)
  const dismiss = useHomeStore((state) => state.dismissApprovedNotice)
  const navigate = useNavigate()

  if (notices.length === 0) return null

  return (
    <div className="flex flex-col gap-2">
      {notices.map((notice) => (
        <output
          key={notice.id}
          data-testid="approved-notice"
          className="flex items-center justify-between gap-3 rounded-lg border border-[#1c1c1f] bg-white px-4 py-3"
        >
          <div className="flex items-center gap-3">
            <img src={iconSuccess} alt="" width={18} height={18} />
            <div className="flex flex-col gap-[2px]">
              <p className="text-[13px] font-semibold">De AI-controle is geslaagd.</p>
              <p className="text-[12px] text-[#6b6b73]">
                {notice.customer} is goedgekeurd en omgezet naar een mapping package. Je vindt het in Version
                Control.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                dismiss(notice.id)
                void navigate('/version-control')
              }}
              className="rounded-[8px] border border-[#1c1c1f] bg-white px-4 py-[10px] text-[14px] leading-[normal] font-semibold text-[#1c1c1f] hover:bg-[#f4f4f6]"
            >
              Naar Version Control
            </button>
            <button
              type="button"
              onClick={() => dismiss(notice.id)}
              className="cursor-pointer text-xs font-semibold text-[#6b6b73] hover:text-[#1c1c1f] px-2 py-1"
              aria-label="Melding sluiten"
            >
              ✕
            </button>
          </div>
        </output>
      ))}
    </div>
  )
}

export default ApprovedNotices
