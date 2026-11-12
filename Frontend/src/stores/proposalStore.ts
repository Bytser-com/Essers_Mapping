import { create } from "zustand";
import type { Proposal } from "../types/proposal";
import {
  getProposal,
  getProposalFile,
  uploadProposalFile,
  approveProposal,
  type ProposalFileDetailsDto,
} from "../services/proposalService";

type ProposalState = {
  proposal: Proposal | null;
  loading: boolean;
  error: string | null;
  actionError: string | null;
  fetchProposal: (company: string) => Promise<void>;
  downloadProposal: (company: string, version: string) => Promise<ProposalFileDetailsDto | null>;
  uploadProposal: (company: string, version: string, file: File) => Promise<boolean>;
  approveProposal: (company: string, version: string) => Promise<boolean>;
};

export const useProposalStore = create<ProposalState>()((set, get) => ({
  proposal: null,
  loading: false,
  error: null,
  actionError: null,

  fetchProposal: async (company) => {
    set({ loading: true, error: null });
    try {
      const proposal = await getProposal(company);
      set({ proposal: proposal, loading: false });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Onbekende fout", loading: false });
    }
  },

  downloadProposal: async (company, version) => {
    set({ actionError: null });
    try {
      return await getProposalFile(company, version);
    } catch (err) {
      console.error("Failed to download proposal Excel file:", err);
      set({ actionError: err instanceof Error ? err.message : "Onbekende fout" });
      return null;
    }
  },

  uploadProposal: async (company, version, file) => {
    set({ actionError: null });
    try {
      await uploadProposalFile(company, version, file);
      await get().fetchProposal(company);
      return true;
    } catch (err) {
      set({ actionError: err instanceof Error ? err.message : "Onbekende fout" });
      return false;
    }
  },

  approveProposal: async (company, version) => {
    set({ actionError: null });
    try {
      await approveProposal(company, version);
      await get().fetchProposal(company);
      return true;
    } catch (err) {
      set({ actionError: err instanceof Error ? err.message : "Onbekende fout" });
      return false;
    }
  },
}));
