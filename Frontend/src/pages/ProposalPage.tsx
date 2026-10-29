import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useProposalStore } from "../stores/proposalStore";
import "./ProposalPage.css";

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
    <main className="proposal">
      <nav className="proposal__breadcrumb">
        <span>Home</span>
        <span>/</span>
        <span>{proposal.klant}</span>
      </nav>

      <header className="proposal__header">
        <div>
          <div className="proposal__title-row">
            <h1 className="proposal__title">
              {proposal.klant} · v{proposal.versie}
            </h1>
            <span className={`status ${proposal.status === "In review" ? "status--review" : "status--ready"}`}>{proposal.status}</span>
          </div>
          <p className="proposal__meta">Geüpload op {formatUploadDate(proposal.geupload)}</p>
        </div>

        <div className="proposal__actions">
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
        <div className="proposal__notice">
          <span className="proposal__notice-icon">i</span>
          Velden met REVIEW_REQUIRED kon de AI niet invullen. Pas ze aan in de Excel en upload die opnieuw.
        </div>
      )}

      <h2 className="proposal__section-title">Inhoud van het voorstel</h2>

      <div className="mapping-table">
        <table>
          <thead>
            <tr>
              <th>Bronveld (klant)</th>
              <th>Doelveld (H.Essers)</th>
              <th>Zekerheid</th>
              <th>Opmerking</th>
            </tr>
          </thead>
          <tbody>
            {proposal.mappings.map((mapping) => (
              <tr key={mapping.id}>
                <td>
                  {!mapping.bronveld ? (
                    <span className="review-tag">{REVIEW_REQUIRED}</span>
                  ) : (
                    <code className="mapping-table__path">{mapping.bronveld}</code>
                  )}
                </td>
                <td>{mapping.doelveld}</td>
                <td>
                  <Confidence value={mapping.zekerheid} />
                </td>
                <td className="mapping-table__remark">{mapping.opmerking}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
