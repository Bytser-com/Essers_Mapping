// Mapping packages overview: data retrieved from Version_Control backend (GET /api/version-control/packages).

import { VERSION_CONTROL_API } from './proposalOverviewService'

// One package in the overview, same fields as MappingPackageOverviewDto in the backend.
export type MappingPackageOverview = {
  company: string // customer folder on SFTP, used in links
  latestVersion: string // version folder, e.g. "v2"
  createdAt: string | null // ISO 8601 (meta.date_created of the package)
  createdBy: string | null // meta.user_created
  customerName: string | null // meta.client_name, shown in the list
  packageType: string | null // meta.package_type (or the type folder) in lowercase, e.g. "inbound"
}

// Loads the latest package(s) of every customer, or only of one customer when `company` is given.
export async function fetchPackages(
  company?: string,
  signal?: AbortSignal,
): Promise<MappingPackageOverview[]> {
  const query = company ? `?${new URLSearchParams({ company }).toString()}` : ''
  const response = await fetch(`${VERSION_CONTROL_API}/packages${query}`, { signal: signal ?? null })
  if (!response.ok) {
    throw new Error(`Loading mapping packages failed (HTTP ${response.status})`)
  }
  const data = await response.json()
  return Array.isArray(data) ? (data as MappingPackageOverview[]) : []
}
