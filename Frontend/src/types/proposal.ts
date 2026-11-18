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
  geupload: string;
  uploadDate?: string | null;
  uploadTime?: string | null;
  updatedDate?: string | null;
  updatedTime?: string | null;
  createdBy?: string | null;
  mappings: Mapping[];
};
