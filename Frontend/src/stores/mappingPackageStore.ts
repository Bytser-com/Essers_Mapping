import { create } from "zustand";
import {
  fetchPackages as fetchPackagesRequest,
  type MappingPackageOverview,
} from "../services/mappingPackageOverviewService";

type MappingPackageState = {
  packages: MappingPackageOverview[] | null;
  loading: boolean;
  error: string | null;
  fetchPackages: (company?: string) => Promise<void>;
};

export const useMappingPackageStore = create<MappingPackageState>()((set) => ({
  packages: null,
  loading: false,
  error: null,

  // Loads the latest package(s) of every customer, or of one customer when `company` is given
  fetchPackages: async (company) => {
    set({ loading: true, error: null });
    try {
      const packages = await fetchPackagesRequest(company);
      set({ packages, loading: false, error: null });
    } catch (err) {
      set({
        packages: null,
        loading: false,
        error: err instanceof Error ? err.message : "Onbekende fout",
      });
    }
  },
}));
