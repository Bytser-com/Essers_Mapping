import type { Proposal } from "../types/proposal";

export const VERSION_CONTROL_API = import.meta.env.VITE_VERSION_CONTROL_API || "/api/version-control";

export type CompanyProposalOverviewDto = {
  company: string;
  latestVersion: string;
  filename?: string | null;
  fullPath?: string | null;
  createdDate?: string | null;
  createdBy?: string | null;
  description?: string | null;
  status?: string | null;
  aiStatus?: string | null;
  mappings?: Proposal["mappings"];
};

export type ProposalFileDetailsDto = {
  company: string;
  version: string;
  filename: string;
  fullPath: string;
  contentType: string;
  sizeBytes: number;
  createdDate: string;
  createdBy: string;
  description?: string | null;
  fileContentBase64: string;
};

export async function getProposal(company: string): Promise<Proposal> {
  const res = await fetch(`${VERSION_CONTROL_API}/proposals?company=${encodeURIComponent(company)}`);
  if (res.status === 502 || res.status === 503) {
    throw new Error(`De bestanden zijn tijdelijk niet bereikbaar (status ${res.status})`);
  }
  if (!res.ok) {
    throw new Error(`geen mapping gevonden (status ${res.status})`);
  }
  const data = await res.json();

  if (data && typeof data === "object" && "mappings" in data && "klant" in data) {
    return data as Proposal;
  }

  const items: CompanyProposalOverviewDto[] = Array.isArray(data)
    ? data
    : Array.isArray((data as { proposals?: unknown[] })?.proposals)
      ? (data as { proposals: CompanyProposalOverviewDto[] }).proposals
      : [data as CompanyProposalOverviewDto];

  const item = items.find((p) => p.company?.toLowerCase() === company.toLowerCase()) || items[0];
  if (!item) {
    throw new Error(`geen mapping gevonden (status 404)`);
  }

  const versionNum = parseInt(String(item.latestVersion ?? "1").replace(/^v/i, ""), 10) || 1;
  const statusLabel = item.status === "IN_REVIEW" ? "In review" : "Klaar om na te kijken";

  return {
    klant: item.company || company,
    versie: versionNum,
    status: statusLabel,
    geupload: item.createdDate || new Date().toISOString(),
    mappings: item.mappings || [],
  };
}

export async function getProposalFile(company: string, version: string): Promise<ProposalFileDetailsDto> {
  const params = new URLSearchParams({ company, version });
  const res = await fetch(`${VERSION_CONTROL_API}/proposals/file?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Bestand kon niet worden opgehaald (status ${res.status})`);
  }
  return res.json();
}
