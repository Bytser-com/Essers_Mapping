import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useProposalStore } from "../stores/proposalStore";

type ProposalPageProps = {
  onDownload?: () => void;
  onUpload?: () => void;
  onApprove?: () => void;
};

type ConfidenceProps = {
  value: number | null;
};

const REVIEW_REQUIRED = "REVIEW_REQUIRED";

function formatUploadDate(isoDate: string): string {
  const date = new Date(isoDate);
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${day}/${month}/${date.getFullYear()} om ${hours}:${minutes}`;
}

function Confidence({ value }: ConfidenceProps) {
  if (value === null || value === undefined) {
    return null;
  }

  return (
    <div className="confidence">
      <span className="confidence__value">{value}%</span>
      <span className="confidence__track">
        <span className="confidence__fill" style={{ width: `${value}%` }} />
      </span>
    </div>
  );
}

export default function ProposalPage({ onDownload, onUpload, onApprove }: ProposalPageProps) {
  const { company } = useParams();
  const proposal = useProposalStore((state) => state.proposal);
  const loading = useProposalStore((state) => state.loading);
  const error = useProposalStore((state) => state.error);
  const fetchProposal = useProposalStore((state) => state.fetchProposal);

  useEffect(() => {
    if (company) {
      fetchProposal(company);
    }
  }, [company, fetchProposal]);

  if (loading) return <p>Voorstel wordt geladen...</p>;
  if (error) return <p>{error}</p>;
  if (!proposal) return null;

  const hasReviewFields = proposal.mappings.some((m) => !m.bronveld);

  return (
    <main className="flex-1 px-6 py-5 bg-background min-h-screen">
      <nav className="flex gap-1.5 mb-1.5 text-grey text-[11px]">
        <span>Home</span>
        <span>/</span>
        <span>{proposal.klant}</span>
      </nav>

      <header className="flex justify-between items-start gap-4 mb-3.5">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="m-0 font-title text-[22px] font-bold">
              {proposal.klant} · v{proposal.versie}
            </h1>
            <span className={`status ${proposal.status === "In review" ? "status--review" : "status--ready"}`}>{proposal.status}</span>
          </div>
          <p className="mt-1 text-grey text-xs">Geüpload op {formatUploadDate(proposal.geupload)}</p>
        </div>

        <div className="flex gap-2 flex-wrap">
          <button type="button" className="btn" onClick={onDownload}>
            Download Excel
          </button>
          <button type="button" className="btn" onClick={onUpload}>
            Aangepaste Excel uploaden
          </button>
          <button type="button" className="btn btn--primary" onClick={onApprove}>
            Goedkeuren
          </button>
        </div>
      </header>

      {hasReviewFields && (
        <div className="flex items-center gap-2.5 px-3 py-2.5 mb-4.5 border border-line-grey rounded-small bg-white text-xs">
          <span className="inline-flex justify-center items-center w-4 h-4 shrink-0 rounded-full bg-anthracite text-white text-[10px] font-bold">i</span>
          Velden met REVIEW_REQUIRED kon de AI niet invullen. Pas ze aan in de Excel en upload die opnieuw.
        </div>
      )}

      <h2 className="mb-2.5 font-title text-sm font-bold">Inhoud van het voorstel</h2>

      <div className="overflow-hidden border border-line-grey rounded-medium bg-white">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="px-3 py-2.5 border-b border-line-grey bg-background text-grey text-[10px] font-semibold tracking-wider text-left uppercase">Bronveld (klant)</th>
              <th className="px-3 py-2.5 border-b border-line-grey bg-background text-grey text-[10px] font-semibold tracking-wider text-left uppercase">Doelveld (H.Essers)</th>
              <th className="px-3 py-2.5 border-b border-line-grey bg-background text-grey text-[10px] font-semibold tracking-wider text-left uppercase">Zekerheid</th>
              <th className="px-3 py-2.5 border-b border-line-grey bg-background text-grey text-[10px] font-semibold tracking-wider text-left uppercase">Opmerking</th>
            </tr>
          </thead>
          <tbody>
            {proposal.mappings.map((mapping) => (
              <tr key={mapping.id}>
                <td className="p-3 border-b border-line-grey text-xs align-middle">
                  {!mapping.bronveld ? (
                    <span className="inline-block px-2.25 py-0.75 rounded-full bg-anthracite text-white font-mono text-[10px] font-medium">{REVIEW_REQUIRED}</span>
                  ) : (
                    <code className="font-mono text-xs">{mapping.bronveld}</code>
                  )}
                </td>
                <td className="p-3 border-b border-line-grey text-xs align-middle">{mapping.doelveld}</td>
                <td className="p-3 border-b border-line-grey text-xs align-middle">
                  <Confidence value={mapping.zekerheid} />
                </td>
                <td className="leading-snug, p-3 border-b border-line-grey text-xs align-middle">{mapping.opmerking}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
