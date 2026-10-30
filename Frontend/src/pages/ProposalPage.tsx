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
const IN_REVIEW = "In review";

// Tabel (Figma: "Tabel – mappings"): 16px rand links/rechts, 12px tussen de kolommen
const thClass =
  "px-1.5 py-2.5 first:pl-4 last:pr-4 text-left font-bold text-[11px] tracking-[0.06em] uppercase text-grey";
const tdClass = "px-1.5 py-[13px] first:pl-4 last:pr-4 align-middle text-[13px]";

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
    <div className="flex items-center gap-2">
      <span className="font-semibold">{value}%</span>
      <span className="relative w-17.5 h-1.5 overflow-hidden rounded-[3px] bg-line-grey">
        <span className="absolute inset-y-0 left-0 rounded-[3px] bg-anthracite" style={{ width: `${value}%` }} />
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

  if (loading) return <p className="px-8 py-7 text-grey">Voorstel wordt geladen...</p>;
  if (error) return <p className="px-8 py-7">{error}</p>;
  if (!proposal) return null;

  const hasReviewFields = proposal.mappings.some((m) => !m.bronveld);

  return (
    <main className="flex flex-1 flex-col gap-4 min-h-screen px-8 py-7 bg-background">
      <header className="flex items-end gap-4">
        <div className="flex flex-1 flex-col gap-1.5">
          <nav className="flex gap-2 text-xs text-grey">
            <span>Home</span>
            <span>/</span>
            <span>{proposal.klant}</span>
          </nav>

          <div className="flex items-center gap-3">
            <h1 className="m-0 font-title text-2xl font-bold">
              {proposal.klant} · v{proposal.versie}
            </h1>
            <span className={`status ${proposal.status === IN_REVIEW ? "status--review" : "status--ready"}`}>
              {proposal.status}
            </span>
          </div>

          <p className="m-0 text-[13px] text-grey">Geüpload op {formatUploadDate(proposal.geupload)}</p>
        </div>

        <div className="flex items-center gap-2.5">
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
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 border border-mid-grey rounded-small bg-white text-[13px]">
          <span className="inline-flex justify-center items-center size-4.5 shrink-0 rounded-full bg-anthracite text-white text-[11px] font-bold">
            i
          </span>
          Velden met REVIEW_REQUIRED kon de AI niet invullen. Pas ze aan in de Excel en upload die opnieuw.
        </div>
      )}

      <h2 className="m-0 font-title text-base font-bold">Inhoud van het voorstel</h2>

      <div className="overflow-hidden border border-line-grey rounded-medium bg-white">
        <table className="w-full table-fixed border-collapse">
          <colgroup>
            <col className="w-65.5" />
            <col className="w-63" />
            <col className="w-48" />
            <col />
          </colgroup>
          <thead className="bg-background border-b border-line-grey">
            <tr>
              <th className={thClass}>Bronveld (klant)</th>
              <th className={thClass}>Doelveld (H.Essers)</th>
              <th className={thClass}>Zekerheid</th>
              <th className={thClass}>Opmerking</th>
            </tr>
          </thead>
          <tbody>
            {proposal.mappings.map((mapping) => (
              <tr key={mapping.id} className="border-b border-line-grey last:border-b-0">
                <td className={tdClass}>
                  {!mapping.bronveld ? (
                    <span className="status status--required">{REVIEW_REQUIRED}</span>
                  ) : (
                    <code className="font-mono text-xs">{mapping.bronveld}</code>
                  )}
                </td>
                <td className={tdClass}>{mapping.doelveld}</td>
                <td className={tdClass}>
                  <Confidence value={mapping.zekerheid} />
                </td>
                <td className={tdClass}>{mapping.opmerking}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
