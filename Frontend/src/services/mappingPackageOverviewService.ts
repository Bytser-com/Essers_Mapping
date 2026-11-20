// Mapping packages overview: data retrieved from Version_Control backend (GET /api/version-control/packages).

import { VERSION_CONTROL_API } from './proposalOverviewService'

// One package in the overview, same fields as MappingPackageOverviewDto in the backend.
export type MappingPackageOverview = {
  company: string // customer folder on SFTP, used in links
  latestVersion: string // newest version folder found, e.g. "v2"
  createdAt: string | null // ISO 8601 (meta.date_created of the package)
  createdBy: string | null // meta.user_created
  customerName: string | null // meta.client_name, shown in the list
  packageType: string | null // meta.package_type (or the type folder) in lowercase, e.g. "inbound"
  activeVersion?: string | null // explicitly active version from active.json, e.g. "v1"
  activeUpdatedAt?: string | null // ISO 8601 timestamp when active version was set
  activeUpdatedBy?: string | null // user who set the active version
}

export type PackageVersion = {
  version: string
  isActive: boolean
  createdAt: string | null
  createdBy: string | null
  description: string | null
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

// Loads all versions for a customer and package type.
export async function fetchPackageVersions(
  company: string,
  packageType: string,
  signal?: AbortSignal,
): Promise<PackageVersion[]> {
  const query = new URLSearchParams({ company, packageType }).toString()
  const response = await fetch(`${VERSION_CONTROL_API}/packages/versions?${query}`, { signal: signal ?? null })
  if (!response.ok) {
    throw new Error(`Loading package versions failed (HTTP ${response.status})`)
  }
  const data = await response.json()
  return Array.isArray(data) ? (data as PackageVersion[]) : []
}

// Sets the active version for a customer and package type.
export async function setActivePackage(
  company: string,
  packageType: string,
  version: string,
  updatedBy?: string,
  signal?: AbortSignal,
): Promise<MappingPackageOverview> {
  const response = await fetch(`${VERSION_CONTROL_API}/packages/active`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      company,
      packageType,
      version,
      updatedBy: updatedBy || 'analist',
    }),
    signal: signal ?? null,
  })
  if (!response.ok) {
    throw new Error(`Setting active package failed (HTTP ${response.status})`)
  }
  return (await response.json()) as MappingPackageOverview
}
