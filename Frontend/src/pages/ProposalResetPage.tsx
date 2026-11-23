import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useHomeStore } from '../stores/homeStore'

export default function ProposalResetPage() {
  const navigate = useNavigate()
  const fetchProposals = useHomeStore((state) => state.fetchProposals)
  const [, setStatus] = useState<'resetting' | 'done'>('resetting')

  useEffect(() => {
    let mounted = true

    async function executeReset() {
      try {
        await Promise.allSettled([
          fetch('/api/proposal/ai-retry', { method: 'POST' }),
          fetch('/api/converter/ai-retry', { method: 'POST' }),
        ])
        await fetchProposals()
      } catch (err) {
        console.error('Error resetting stuck AI proposals:', err)
      } finally {
        if (mounted) {
          setStatus('done')
          navigate('/', { replace: true })
        }
      }
    }

    void executeReset()

    return () => {
      mounted = false
    }
  }, [navigate, fetchProposals])

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-8">
      <div className="flex flex-col items-center gap-4 p-8 bg-white border border-[#e3e3e8] rounded-[16px] shadow-sm max-w-md w-full text-center">
        <div data-testid="reset-spinner" className="w-8 h-8 border-4 border-[#1c1c1f] border-t-transparent rounded-full animate-spin" />
        <h2 className="font-['Montserrat',sans-serif] text-[18px] font-bold text-[#1c1c1f]">
          AI processen opnieuw opstarten…
        </h2>
        <p className="font-['Inter',sans-serif] text-[14px] text-[#6b6b73]">
          Vastgelopen voorstellen worden opnieuw gestart. Je wordt doorgestuurd naar de voorstellenpagina.
        </p>
      </div>
    </div>
  )
}
