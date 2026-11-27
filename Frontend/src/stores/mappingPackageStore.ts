import { create } from "zustand";
import {
  fetchPackages as fetchPackagesRequest,
  setActivePackage as setActivePackageRequest,
  type MappingPackageOverview,
} from "../services/mappingPackageOverviewService";

type MappingPackageState = {
  packages: MappingPackageOverview[] | null;
  loading: boolean;
  error: string | null;
  fetchPackages: (company?: string) => Promise<void>;
  setActivePackage: (
    company: string,
    packageType: string,
    version: string,
    updatedBy?: string
  ) => Promise<void>;
};

export const useMappingPackageStore = create<MappingPackageState>()((set, get) => ({
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

  // Updates active package on backend and updates the in-memory packages list
  setActivePackage: async (company, packageType, version, updatedBy) => {
    const updated = await setActivePackageRequest(company, packageType, version, updatedBy);
    const current = get().packages;
    if (current) {
      const updatedList = current.map((pkg) => {
        if (
          pkg.company.toLowerCase() === company.toLowerCase() &&
          (pkg.packageType || '').toLowerCase() === packageType.toLowerCase()
        ) {
          return updated;
        }
        return pkg;
      });
      set({ packages: updatedList });
    }
  },
}));
