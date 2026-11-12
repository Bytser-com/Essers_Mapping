import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useProposalStore } from "../stores/proposalStore";
import iconUpload from "../assets/home/icon-upload.svg";
import iconError from "../assets/home/icon-error.svg";
import iconSuccess from "../assets/home/icon-success.svg";


type ProposalPageProps = {
  onDownload?: () => void;
  onApprove?: () => void;
};

type ConfidenceProps = {
  value: number | null;
};

const REVIEW_REQUIRED = "REVIEW_REQUIRED";
const IN_REVIEW = "In review";

const thClass =
  "px-3 py-2.5 first:pl-4 last:pr-4 text-left font-bold text-[11px] tracking-[0.06em] uppercase text-grey select-none";
const tdClass = "px-3 py-[13px] first:pl-4 last:pr-4 align-middle text-[13px]";

function formatUploadDate(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${day}/${month}/${date.getFullYear()} om ${hours}:${minutes}`;
}

function formatDateOnly(dateStr?: string | null): string {
  if (!dateStr) return "—";
  const parts = dateStr.split("-");
  if (parts.length === 3) {
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
  return dateStr;
}

function Confidence({ value }: Readonly<ConfidenceProps>) {
  if (value === null || value === undefined) {
    return <span className="text-grey text-xs">—</span>;
  }

  // Color-coded certainty: >= 80% anthracite/bold, 50-79% mid-grey, < 50% red accent
  let barColor = "bg-anthracite";
  if (value < 50) {
    barColor = "bg-red";
  } else if (value < 80) {
    barColor = "bg-mid-grey";
  }

  return (
    <div className="flex items-center gap-2" title={`Betrouwbaarheid: ${value}%`}>
      <span className="font-semibold text-xs tabular-nums w-8">{value}%</span>
      <span className="relative w-16 h-1.5 overflow-hidden rounded-[3px] bg-line-grey">
        <span className={`absolute inset-y-0 left-0 rounded-[3px] ${barColor}`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </span>
    </div>
  );
}

export default function ProposalPage({ onDownload, onApprove }: Readonly<ProposalPageProps>) {
  const { company } = useParams();
  const proposal = useProposalStore((state) => state.proposal);
  const loading = useProposalStore((state) => state.loading);
  const error = useProposalStore((state) => state.error);
  const fetchProposal = useProposalStore((state) => state.fetchProposal);
  const downloadProposal = useProposalStore((state) => state.downloadProposal);
  const uploadProposal = useProposalStore((state) => state.uploadProposal);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const actionError = useProposalStore((state) => state.actionError);

  const [searchTerm, setSearchTerm] = useState("");
  const [filterMissingOnly, setFilterMissingOnly] = useState(false);
  const [uploadSucceeded, setUploadSucceeded] = useState(false);

  useEffect(() => {
    if (company) {
      void fetchProposal(company);
    }
  }, [company, fetchProposal]);

  async function handleDownload() {
    if (onDownload) {
      onDownload();
      return;
    }
    if (!proposal || !company) return;

    const file = await downloadProposal(company, `v${proposal.versie}`);
    if (!file?.fileContentBase64) return;
    const byteCharacters = atob(file.fileContentBase64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.codePointAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], {
      type: file.contentType || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = file.filename || `MProposal-${proposal.klant}_v${proposal.versie}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function closeUploadDialog() {
    setShowUploadDialog(false);
    setSelectedFile(null);
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(e.target.files?.[0] ?? null);
    e.target.value = "";
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setSelectedFile(e.dataTransfer.files[0] ?? null);
  }

  async function handleUpload() {
    if (!selectedFile || !proposal || !company) return;
    setUploadSucceeded(false);
    const succeeded = await uploadProposal(company, `v${proposal.versie}`, selectedFile);
    setUploadSucceeded(succeeded);
    closeUploadDialog();
  }

  if (loading) return <p className="px-8 py-7 text-grey">Voorstel wordt geladen...</p>;
  if (error) return <p className="px-8 py-7 text-red font-medium">{error}</p>;
  if (!proposal) return null;

  const totalMappings = proposal.mappings.length;
  const reviewCount = proposal.mappings.filter((m) => !m.bronveld).length;
  const matchedCount = totalMappings - reviewCount;
  const hasReviewFields = reviewCount > 0;

  const filteredMappings = proposal.mappings.filter((mapping) => {
    if (filterMissingOnly && mapping.bronveld) {
      return false;
    }
    if (!searchTerm.trim()) {
      return true;
    }
    const q = searchTerm.toLowerCase();
    const sourceMatch = (mapping.bronveld || "").toLowerCase().includes(q);
    const targetMatch = (mapping.doelveld || "").toLowerCase().includes(q);
    const commentMatch = (mapping.opmerking || "").toLowerCase().includes(q);
    return sourceMatch || targetMatch || commentMatch;
  });

  return (
    <main className="flex flex-1 flex-col gap-5 min-h-screen px-8 py-7 bg-background">
      {/* Top Header */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-1 min-w-[280px] flex-col gap-1.5">
          <nav className="flex items-center gap-2 text-xs text-grey" aria-label="Kruimelpad">
            <Link to="/" className="text-grey hover:underline">
              Home
            </Link>
            <span>/</span>
            <span>{proposal.klant}</span>
          </nav>

          <div className="flex flex-wrap items-center gap-3">
            <h1 className="m-0 font-title text-2xl font-bold">
              {proposal.klant} · v{proposal.versie}
            </h1>
            <span
              className={`status ${proposal.status === IN_REVIEW
                ? "status--review"
                : proposal.status === "Klaar om na te kijken"
                  ? "status--ready"
                  : "status--success"
                }`}
            >
              {proposal.status}
            </span>
          </div>

          <p className="m-0 text-[13px] text-grey">Geüpload op {formatUploadDate(proposal.geupload)} door {proposal.uploadUser ?? "onbekend"}</p>
        </div>

        <div className="flex items-center gap-2.5">
          <button type="button" className="btn" onClick={handleDownload} title="Download mappingproposal.xlsx">
            Download Excel
          </button>
          <button type="button" className="btn" onClick={() => setShowUploadDialog(true)}>
            Aangepaste Excel uploaden
          </button>
          <button type="button" className="btn btn--primary" onClick={onApprove} disabled={hasReviewFields}>
            Goedkeuren
          </button>
        </div>
      </header>

      {/* Info / Metadata Card Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
        <div className="flex flex-col gap-1 p-3.5 bg-white border border-line-grey rounded-small">
          <span className="text-[11px] font-bold tracking-[0.06em] uppercase text-grey">Totaal velden</span>
          <span className="font-title text-xl font-bold text-anthracite">{totalMappings}</span>
        </div>

        <div className="flex flex-col gap-1 p-3.5 bg-white border border-line-grey rounded-small">
          <span className="text-[11px] font-bold tracking-[0.06em] uppercase text-grey">Automatisch gematcht</span>
          <span className="font-title text-xl font-bold text-anthracite">
            {matchedCount} <span className="text-xs font-normal text-grey">van {totalMappings}</span>
          </span>
        </div>

        <div className="flex flex-col gap-1 p-3.5 bg-white border border-line-grey rounded-small">
          <span className="text-[11px] font-bold tracking-[0.06em] uppercase text-grey">Nazicht vereist</span>
          <span className={`font-title text-xl font-bold ${reviewCount > 0 ? "text-red" : "text-anthracite"}`}>
            {reviewCount}
          </span>
        </div>

        <div className="flex flex-col gap-1 p-3.5 bg-white border border-line-grey rounded-small">
          <span className="text-[11px] font-bold tracking-[0.06em] uppercase text-grey">Laatst bijgewerkt</span>
          <span className="text-xs font-medium text-anthracite mt-1 truncate" title={proposal.updatedDate || "Niet bijgewerkt"}>
            {proposal.updatedDate ? `${formatDateOnly(proposal.updatedDate)} ${proposal.updatedTime ? proposal.updatedTime.slice(0, 5) : ""}` : "—"}
          </span>
          {proposal.uploadUser && (
            <span className="text-[11px] text-grey truncate">Door: {proposal.uploadUser}</span>
          )}
        </div>
      </div>

      {/* Error banner when downloading or uploading failed */}
      {actionError && (
        <div role="alert" className="flex items-center gap-3 rounded-small border border-anthracite bg-white px-4 py-3">
          <img src={iconError} alt="" width={18} height={18} />
          <p className="m-0 text-[13px] font-semibold">{actionError}</p>
        </div>
      )}

      {uploadSucceeded && (
        <output className="flex items-center gap-3 rounded-small border border-anthracite bg-white px-4 py-3">
          <img src={iconSuccess} alt="" width={18} height={18} />
          <p className="m-0 text-[13px] font-semibold">Upload gelukt. De aangepaste Excel is opgeslagen.</p>
        </output>
      )}

      {/* Action banner if review is required */}
      {hasReviewFields && (
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 border border-mid-grey rounded-small bg-white text-[13px]">
          <span className="inline-flex justify-center items-center size-4.5 shrink-0 rounded-full bg-anthracite text-white text-[11px] font-bold" aria-hidden="true">
            i
          </span>
          <span>Velden met REVIEW_REQUIRED kon de AI niet invullen. Pas ze aan in de Excel en upload die opnieuw.</span>
        </div>
      )}

      {/* Table section header & search filter toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
        <h2 className="m-0 font-title text-base font-bold">Inhoud van het voorstel</h2>

        <div className="flex flex-wrap items-center gap-2">
          {reviewCount > 0 && (
            <button
              type="button"
              className={`text-xs px-2.5 py-1.5 rounded-small font-medium border cursor-pointer transition-colors ${filterMissingOnly
                ? "bg-anthracite text-white border-anthracite"
                : "bg-white text-anthracite border-line-grey hover:bg-background"
                }`}
              onClick={() => setFilterMissingOnly(!filterMissingOnly)}
              aria-pressed={filterMissingOnly}
            >
              {filterMissingOnly ? "Toon alle velden" : `Alleen vereist nazicht (${reviewCount})`}
            </button>
          )}

          <input
            type="search"
            placeholder="Zoek in velden of opmerkingen…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="px-3 py-1.5 text-xs bg-white border border-line-grey rounded-small text-anthracite placeholder:text-mid-grey focus:outline-none focus:border-anthracite w-56 sm:w-64"
            aria-label="Zoek in velden"
          />
        </div>
      </div>

      {/* Data Table */}
      <div className="overflow-x-auto border border-line-grey rounded-medium bg-white">
        <table className="w-full table-fixed border-collapse">
          <colgroup>
            <col className="w-1/4 min-w-[200px]" />
            <col className="w-1/4 min-w-[200px]" />
            <col className="w-40" />
            <col className="w-auto min-w-[220px]" />
          </colgroup>
          <thead className="bg-background border-b border-line-grey">
            <tr>
              <th scope="col" className={thClass}>Bronveld (klant)</th>
              <th scope="col" className={thClass}>Doelveld (H.Essers)</th>
              <th scope="col" className={thClass}>Zekerheid</th>
              <th scope="col" className={thClass}>Opmerking</th>
            </tr>
          </thead>
          <tbody>
            {filteredMappings.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-xs text-grey">
                  Geen velden gevonden die voldoen aan de zoekcriteria.
                </td>
              </tr>
            ) : (
              filteredMappings.map((mapping) => (
                <tr key={mapping.id} className="border-b border-line-grey last:border-b-0 hover:bg-background/40 transition-colors">
                  <td className={tdClass}>
                    {!mapping.bronveld ? (
                      <span className="status status--required">{REVIEW_REQUIRED}</span>
                    ) : (
                      <code className="font-mono text-xs px-1.5 py-0.5 rounded bg-background border border-line-grey text-anthracite break-all">
                        {mapping.bronveld}
                      </code>
                    )}
                  </td>
                  <td className={tdClass}>
                    <code className="font-mono text-xs text-anthracite font-medium break-all">
                      {mapping.doelveld}
                    </code>
                  </td>
                  <td className={tdClass}>
                    <Confidence value={mapping.zekerheid} />
                  </td>
                  <td className={`${tdClass} text-grey text-xs break-words`}>
                    {mapping.opmerking || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {showUploadDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-anthracite/45">
          <dialog
            open
            aria-labelledby="upload-dialog-title"
            className="static flex flex-col gap-4 w-140 max-w-[calc(100vw-32px)] m-0 p-7 rounded-large bg-white"
          >
            <h2 id="upload-dialog-title" className="m-0 font-title text-xl font-bold">
              Aangepaste Excel uploaden
            </h2>

            <div
              className="flex flex-col items-center gap-2 px-5 py-4.5 border border-dashed border-mid-grey rounded-[10px] bg-background"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
            >
              <img src={iconUpload} alt="" width={26} height={26} />
              <span className="text-[13px] font-semibold">Sleep een Excel-bestand hierheen</span>
              <button type="button" className="btn" onClick={() => fileInputRef.current?.click()}>
                Bestanden kiezen
              </button>
              <span className="text-xs text-grey">
                {selectedFile ? selectedFile.name : "Alleen Excel-bestanden (.xlsx)"}
              </span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={handleFileChange}
              />
            </div>

            <div className="flex justify-end gap-2.5">
              <button type="button" className="btn" onClick={closeUploadDialog}>
                Annuleren
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void handleUpload()}
                disabled={!selectedFile}
              >
                Uploaden
              </button>
            </div>
          </dialog>
        </div>
      )
      }
    </main >
  );
}

