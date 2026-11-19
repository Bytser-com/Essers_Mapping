import { create } from "zustand";
import { fetchProposals as fetchProposalsRequest, type ProposalList } from "../services/proposals";
import { uploadInterface as uploadInterfaceRequest } from "../services/uploadService";

// How long the list keeps checking for the new row after an upload.
const WAIT_FOR_NEW_UPLOAD_MS = 30_000;

type HomeState = {
  proposalList: ProposalList | null;
  loading: boolean;
  error: string | null;
  uploadError: string | null;
  waitUntil: number;
  fetchProposals: (quiet?: boolean) => Promise<void>;
  uploadInterface: (customerName: string, proposalType: string, files: File[]) => Promise<boolean>;
};

export const useHomeStore = create<HomeState>()((set, get) => ({
  proposalList: null,
  loading: false,
  error: null,
  uploadError: null,
  waitUntil: 0,

  // quiet = refresh in the background: the table that is shown stays visible
  fetchProposals: async (quiet = false) => {
    if (!quiet) set({ loading: true, error: null });
    try {
      const proposalList = await fetchProposalsRequest();
      set({ proposalList: proposalList, loading: false, error: null });
    } catch (err) {
      // A failed background refresh keeps the table that is already shown.
      // (A new object, so polling keeps going and tries again later.)
      const current = get().proposalList;
      set({
        proposalList: current ? { ...current } : null,
        loading: false,
        error: current ? null : err instanceof Error ? err.message : "Onbekende fout",
      });
    }
  },

  uploadInterface: async (customerName, proposalType, files) => {
    set({ uploadError: null });
    try {
      await uploadInterfaceRequest(customerName, proposalType, files);
      set({ waitUntil: Date.now() + WAIT_FOR_NEW_UPLOAD_MS });
      await get().fetchProposals(true);
      return true;
    } catch (err) {
      set({ uploadError: err instanceof Error ? err.message : "Upload mislukt." });
      return false;
    }
  },
}));