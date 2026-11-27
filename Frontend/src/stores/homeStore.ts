import { create } from "zustand";
import {
  fetchProposals as fetchProposalsRequest,
  type Proposal,
  type ProposalList,
} from "../services/proposalOverviewService";
import { uploadInterface as uploadInterfaceRequest } from "../services/uploadService";

// How long the list keeps checking for the new row after an upload.
const WAIT_FOR_NEW_UPLOAD_MS = 30_000;

// A proposal that just passed the AI review and became a mapping package (story IT2627T06-187).
export type ApprovedNotice = {
  id: string;
  customer: string;
};

// Proposals that became APPROVED since the previous load. The first load shows nothing,
// so reopening Home does not repeat old news.
function findNewlyApproved(previous: ProposalList | null, next: ProposalList): ApprovedNotice[] {
  if (!previous) return [];
  const before = new Map<string, Proposal["status"]>(previous.proposals.map((p) => [p.id, p.status]));
  return next.proposals
    .filter((p) => p.status === "APPROVED" && before.has(p.id) && before.get(p.id) !== "APPROVED")
    .map((p) => ({ id: p.id, customer: p.customer }));
}

type HomeState = {
  proposalList: ProposalList | null;
  loading: boolean;
  error: string | null;
  uploadError: string | null;
  waitUntil: number;
  approvedNotices: ApprovedNotice[];
  fetchProposals: (quiet?: boolean) => Promise<void>;
  dismissApprovedNotice: (id: string) => void;
  uploadInterface: (customerName: string, proposalType: string, files: File[]) => Promise<boolean>;
};

export const useHomeStore = create<HomeState>()((set, get) => ({
  proposalList: null,
  loading: false,
  error: null,
  uploadError: null,
  waitUntil: 0,
  approvedNotices: [],

  // quiet = refresh in the background: the table that is shown stays visible
  fetchProposals: async (quiet = false) => {
    if (!quiet) set({ loading: true, error: null });
    try {
      const proposalList = await fetchProposalsRequest();
      const newlyApproved = findNewlyApproved(get().proposalList, proposalList);
      const notices = get().approvedNotices.filter((n) => !newlyApproved.some((a) => a.id === n.id));
      set({
        proposalList: proposalList,
        loading: false,
        error: null,
        approvedNotices: [...notices, ...newlyApproved],
      });
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

  dismissApprovedNotice: (id) => {
    set({ approvedNotices: get().approvedNotices.filter((notice) => notice.id !== id) });
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