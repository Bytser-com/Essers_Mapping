import { create } from "zustand";
import type { Proposal } from "../types/proposal";
import {
  getProposal,
  getProposalFile,
  uploadProposalFile,
  approveProposal,
  deleteProposal,
  type ProposalFileDetailsDto,
} from "../services/proposalService";

type ProposalState = {
  proposal: Proposal | null;
  loading: boolean;
  error: string | null;
  actionError: string | null;
  deleteSuccessMessage: string | null;
  setDeleteSuccessMessage: (message: string | null) => void;
  clearDeleteSuccessMessage: () => void;
  fetchProposal: (company: string) => Promise<void>;
  downloadProposal: (company: string, version: string) => Promise<ProposalFileDetailsDto | null>;
  uploadProposal: (company: string, version: string, file: File) => Promise<boolean>;
  approveProposal: (company: string, version: string) => Promise<boolean>;
  deleteProposal: (company: string, version: string, deleteCheck: string) => Promise<boolean>;
};

export const useProposalStore = create<ProposalState>()((set, get) => ({
  proposal: null,
  loading: false,
  error: null,
  actionError: null,
  deleteSuccessMessage: null,

  setDeleteSuccessMessage: (message) => set({ deleteSuccessMessage: message }),
  clearDeleteSuccessMessage: () => set({ deleteSuccessMessage: null }),

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

  deleteProposal: async (company, version, deleteCheck) => {
    set({ actionError: null });
    try {
      await deleteProposal(company, version, deleteCheck);
      set({
        proposal: null,
        deleteSuccessMessage: `Voorstel voor ${company} (${version}) is succesvol verwijderd.`,
      });
      return true;
    } catch (err) {
      set({ actionError: err instanceof Error ? err.message : "Onbekende fout" });
      return false;
    }
  },
}));
