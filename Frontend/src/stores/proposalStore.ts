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

export type ApprovalMessage = {
  type: "success" | "error";
  title: string;
  message: string;
};

type ProposalState = {
  proposal: Proposal | null;
  loading: boolean;
  error: string | null;
  actionError: string | null;
  deleteSuccessMessage: string | null;
  setDeleteSuccessMessage: (message: string | null) => void;
  clearDeleteSuccessMessage: () => void;
  approvalMessage: ApprovalMessage | null;
  setApprovalMessage: (message: ApprovalMessage | null) => void;
  clearApprovalMessage: () => void;
  fetchProposal: (company: string) => Promise<void>;
  downloadProposal: (company: string, version: string) => Promise<ProposalFileDetailsDto | null>;
  uploadProposal: (company: string, version: string, file: File) => Promise<boolean>;
  approveProposal: (company: string, version: string, description: string) => Promise<boolean>;
  deleteProposal: (company: string, version: string, deleteCheck: string) => Promise<boolean>;
};

export const useProposalStore = create<ProposalState>()((set, get) => ({
  proposal: null,
  loading: false,
  error: null,
  actionError: null,
  deleteSuccessMessage: null,
  approvalMessage: null,

  setDeleteSuccessMessage: (message) => set({ deleteSuccessMessage: message }),
  clearDeleteSuccessMessage: () => set({ deleteSuccessMessage: null }),
  setApprovalMessage: (message) => set({ approvalMessage: message }),
  clearApprovalMessage: () => set({ approvalMessage: null }),

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
      const proposalType = get().proposal?.proposalType ?? "";
      return await getProposalFile(company, version, proposalType);
    } catch (err) {
      console.error("Failed to download proposal Excel file:", err);
      set({ actionError: err instanceof Error ? err.message : "Onbekende fout" });
      return null;
    }
  },

  uploadProposal: async (company, version, file) => {
    set({ actionError: null });
    try {
      const proposalType = get().proposal?.proposalType ?? "";
      await uploadProposalFile(company, version, proposalType, file);
      await get().fetchProposal(company);
      return true;
    } catch (err) {
      set({ actionError: err instanceof Error ? err.message : "Onbekende fout" });
      return false;
    }
  },

  approveProposal: async (company, version, description) => {
    set({ actionError: null });
    try {
      const proposalType = get().proposal?.proposalType ?? "";
      await approveProposal(company, version, proposalType, description);
      set({
        proposal: null,
        approvalMessage: {
          type: "success",
          title: "Voorstel goedgekeurd.",
          message: `Voorstel voor ${company} (${version}) is succesvol goedgekeurd en omgezet.`,
        },
      });
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Onbekende fout";
      set({
        actionError: msg,
        approvalMessage: {
          type: "error",
          title: "Goedkeuren mislukt.",
          message: msg,
        },
      });
      return false;
    }
  },

  deleteProposal: async (company, version, deleteCheck) => {
    set({ actionError: null });
    try {
      const proposalType = get().proposal?.proposalType ?? "";
      await deleteProposal(company, version, proposalType, deleteCheck);
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
