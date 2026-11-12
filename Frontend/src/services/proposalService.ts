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

export type ProposalFileDataDto = {
  version: string;
  companyname: string;
  upload_date?: string | null;
  upload_time?: string | null;
  updated_time?: string | null;
  updated_date?: string | null;
  upload_user?: string | null;
  status?: string | null;
  rows: Array<{
    source_field?: string | null;
    target_field: string;
    score?: string | number | null;
    comment?: string | null;
  }>;
};

export async function getProposalFileData(company: string, version: string): Promise<ProposalFileDataDto> {
  const params = new URLSearchParams({ company, version });
  const res = await fetch(`${VERSION_CONTROL_API}/proposals/filedata?${params.toString()}`);
  if (res.status === 502 || res.status === 503) {
    throw new Error(`De bestanden zijn tijdelijk niet bereikbaar (status ${res.status})`);
  }
  if (!res.ok) {
    throw new Error(`geen mapping gevonden (status ${res.status})`);
  }
  return res.json();
}

function parseScore(score: string | number | null | undefined): number | null {
  if (score === null || score === undefined || score === '') return null;
  const num = typeof score === 'number' ? score : parseFloat(String(score).replace('%', '').trim());
  return Number.isFinite(num) ? Math.round(num) : null;
}

function mapStatusLabel(rawStatus?: string | null): string {
  if (!rawStatus) return "Klaar om na te kijken";
  const s = rawStatus.toUpperCase();
  if (s === "IN_REVIEW" || rawStatus.toLowerCase() === "in review") return "In review";
  if (s === "READY_FOR_REVIEW") return "Klaar om na te kijken";
  if (s === "AI_GENERATING") return "Wordt gegenereerd";
  if (s === "AI_CHECKING_REVIEW") return "AI controleert";
  if (s === "RETURNED") return "Teruggestuurd";
  return rawStatus;
}

export async function getProposal(company: string, version?: string): Promise<Proposal> {
  // If version is provided, we can directly fetch filedata
  if (version) {
    try {
      const fileData = await getProposalFileData(company, version);
      const versionNum = parseInt(String(fileData.version ?? version).replace(/^v/i, ""), 10) || 1;
      const isoUpload = fileData.upload_date
        ? `${fileData.upload_date}T${fileData.upload_time || "00:00:00"}`
        : new Date().toISOString();

      return {
        klant: fileData.companyname || company,
        versie: versionNum,
        status: mapStatusLabel(fileData.status),
        geupload: isoUpload,
        uploadDate: fileData.upload_date || null,
        uploadTime: fileData.upload_time || null,
        updatedDate: fileData.updated_date || null,
        updatedTime: fileData.updated_time || null,
        uploadUser: fileData.upload_user || null,
        mappings: (fileData.rows || []).map((row, index) => ({
          id: `row-${index + 1}`,
          bronveld: row.source_field || null,
          doelveld: row.target_field,
          zekerheid: parseScore(row.score),
          opmerking: row.comment || null,
        })),
      };
    } catch (err) {
      // Fallback to overview lookup if filedata specifically fails with non-network error
      if (err instanceof Error && err.message.includes("De bestanden zijn tijdelijk niet bereikbaar")) {
        throw err;
      }
    }
  }

  // Fetch overview to find latest version and proposal metadata
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

  const resolvedVersion = item.latestVersion || "v1";

  // Now attempt to load detailed rows and metadata via getProposalFileData
  try {
    const fileData = await getProposalFileData(item.company || company, resolvedVersion);
    const versionNum = parseInt(String(fileData.version ?? resolvedVersion).replace(/^v/i, ""), 10) || 1;
    const isoUpload = fileData.upload_date
      ? `${fileData.upload_date}T${fileData.upload_time || "00:00:00"}`
      : item.createdDate || new Date().toISOString();

    return {
      klant: fileData.companyname || item.company || company,
      versie: versionNum,
      status: mapStatusLabel(fileData.status || item.status),
      geupload: isoUpload,
      uploadDate: fileData.upload_date || null,
      uploadTime: fileData.upload_time || null,
      updatedDate: fileData.updated_date || null,
      updatedTime: fileData.updated_time || null,
      uploadUser: fileData.upload_user || item.createdBy || null,
      mappings: (fileData.rows || []).map((row, index) => ({
        id: `row-${index + 1}`,
        bronveld: row.source_field || null,
        doelveld: row.target_field,
        zekerheid: parseScore(row.score),
        opmerking: row.comment || null,
      })),
    };
  } catch (err) {
    // If filedata call fails (e.g. backend error or test mock only mocking /proposals), fall back gracefully
    if (err instanceof Error && err.message.includes("De bestanden zijn tijdelijk niet bereikbaar")) {
      throw err;
    }
    const versionNum = parseInt(String(item.latestVersion ?? "1").replace(/^v/i, ""), 10) || 1;
    return {
      klant: item.company || company,
      versie: versionNum,
      status: mapStatusLabel(item.status),
      geupload: item.createdDate || new Date().toISOString(),
      uploadUser: item.createdBy || null,
      mappings: item.mappings || [],
    };
  }
}

export async function getProposalFile(company: string, version: string): Promise<ProposalFileDetailsDto> {
  const params = new URLSearchParams({ company, version });
  const res = await fetch(`${VERSION_CONTROL_API}/proposals/file?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Bestand kon niet worden opgehaald (status ${res.status})`);
  }
  return res.json();
}

export async function uploadProposalFile(company: string, version: string, file: File): Promise<void> {
  const params = new URLSearchParams({ company, version });

  const res = await fetch(`${VERSION_CONTROL_API}/proposals/file?${params.toString()}`, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });

  if (res.status === 502 || res.status === 503) {
    throw new Error(`De bestanden zijn tijdelijk niet bereikbaar (status ${res.status})`);         
  }
  if (!res.ok) {
    throw new Error(`Bestand kon niet worden geüpload (status ${res.status})`);
  }
}
