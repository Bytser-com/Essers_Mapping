import { create } from "zustand";
import type { Proposal } from "../types/proposal";
import { getProposal } from "../services/proposalService";

type ProposalState = {
  proposal: Proposal | null;
  loading: boolean;
  error: string | null;
  fetchProposal: (company: string) => Promise<void>;
};

export const useProposalStore = create<ProposalState>()((set) => ({
  proposal: null,
  loading: false,
  error: null,

  fetchProposal: async (company) => {
    set({ loading: true, error: null });
    try {
      const proposal = await getProposal(company);
      set({ proposal: proposal, loading: false });
    } catch (err) {
      set({ error:  err instanceof Error ? err.message : "Onbekende fout" , loading: false });
    }
  },
}));