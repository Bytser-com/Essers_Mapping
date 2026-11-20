export type Mapping = {
  id: string;
  bronveld: string | null;
  doelveld: string;
  zekerheid: number | null;
  opmerking: string | null;
};

export type Proposal = {
  klant: string;
  versie: number;
  status: string;
  /** Raw backend status code (e.g. "AI_CHECKING_REVIEW"); use this for logic, `status` is the Dutch label. */
  statusCode?: string | undefined;
  proposalType?: string | null;
  geupload: string;
  uploadDate?: string | null;
  uploadTime?: string | null;
  updatedDate?: string | null;
  updatedTime?: string | null;
  createdBy?: string | null;
  mappings: Mapping[];
};
