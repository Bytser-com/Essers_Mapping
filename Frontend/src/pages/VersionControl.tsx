import { useEffect, useMemo, useState } from 'react'
import iconSearch from '../assets/version-control/icon-search.svg'
import {
  type MappingPackageOverview,
} from '../services/mappingPackageOverviewService'
import { formatUploadedAt } from '../services/proposalOverviewService'
import { useMappingPackageStore } from '../stores/mappingPackageStore'
import { useNavigate } from 'react-router-dom'

// Column widths 280 / 150 / 150 / rest / 160 px with a 12 px gap; the row has 16 px side padding
// (Figma "Lijst – mapping packages"). Each cell's width includes its padding.
const CUSTOMER_CELL = 'w-[308px] pl-4 pr-3' // 16 + 280 + 12
const TYPE_CELL = 'w-[162px] pr-3' // 150 + 12, same as the TYPE column of the proposals table
const VERSION_CELL = 'w-[162px] pr-3' // 150 + 12
const CHANGE_CELL = 'pr-3' // rest of the width
const ACTION_CELL = 'w-[176px] pr-4 text-right' // 160 + 16

const HEADER_TEXT = 'py-2.5 text-left align-middle text-[11px] font-bold tracking-[0.66px] text-grey'
const BODY_CELL = 'py-[13px] align-middle'

function matchToken(text: string, token: string): boolean {
  if (!text) return false
  if (token.length === 1) {
    const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`)
    return new RegExp(String.raw`(?:^|\s|[^a-zA-Z0-9])${escaped}`, 'i').test(text)
  }
  return text.toLowerCase().includes(token)
}

function matchField(pkg: MappingPackageOverview, token: string): boolean {
  const company = pkg.company || ''
  const customerName = pkg.customerName || ''
  const type = pkg.packageType || ''
  const version = pkg.activeVersion || pkg.latestVersion || ''
  const user = pkg.createdBy || ''
  const activeUser = pkg.activeUpdatedBy || ''
  const rawDate = pkg.createdAt || ''
  const formattedDate = pkg.createdAt ? formatUploadedAt(pkg.createdAt) : ''
  const rawActiveDate = pkg.activeUpdatedAt || ''
  const formattedActiveDate = pkg.activeUpdatedAt ? formatUploadedAt(pkg.activeUpdatedAt) : ''

  return (
    matchToken(company, token) ||
    matchToken(customerName, token) ||
    matchToken(type, token) ||
    matchToken(version, token) ||
    matchToken(user, token) ||
    matchToken(activeUser, token) ||
    matchToken(rawDate, token) ||
    matchToken(formattedDate, token) ||
    matchToken(rawActiveDate, token) ||
    matchToken(formattedActiveDate, token)
  )
}

// Version Control overview (Figma "07 · Version Control"): all customers and their mapping packages
export default function VersionControl() {
  const navigate = useNavigate()
  const [searchTerm, setSearchTerm] = useState('')
  const fetchPackages = useMappingPackageStore((state) => state.fetchPackages)

  useEffect(() => {
    void fetchPackages()
  }, [fetchPackages])

  const packages = useMappingPackageStore((state) => state.packages)
  const loading = useMappingPackageStore((state) => state.loading)
  const error = useMappingPackageStore((state) => state.error)

  const filteredPackages = useMemo(() => {
    if (!packages) return []
    const q = searchTerm.trim().toLowerCase()
    if (!q) return packages

    // Check if the entire query matches directly as a phrase in any field
    const phraseMatches = packages.filter((pkg) => {
      const company = (pkg.company || '').toLowerCase()
      const customerName = (pkg.customerName || '').toLowerCase()
      const type = (pkg.packageType || '').toLowerCase()
      const version = (pkg.activeVersion || pkg.latestVersion || '').toLowerCase()
      const user = (pkg.createdBy || '').toLowerCase()
      const activeUser = (pkg.activeUpdatedBy || '').toLowerCase()
      const rawDate = (pkg.createdAt || '').toLowerCase()
      const formattedDate = pkg.createdAt ? formatUploadedAt(pkg.createdAt).toLowerCase() : ''
      const rawActiveDate = (pkg.activeUpdatedAt || '').toLowerCase()
      const formattedActiveDate = pkg.activeUpdatedAt ? formatUploadedAt(pkg.activeUpdatedAt).toLowerCase() : ''

      return (
        company.includes(q) ||
        customerName.includes(q) ||
        type.includes(q) ||
        version.includes(q) ||
        user.includes(q) ||
        activeUser.includes(q) ||
        rawDate.includes(q) ||
        formattedDate.includes(q) ||
        rawActiveDate.includes(q) ||
        formattedActiveDate.includes(q)
      )
    })

    if (phraseMatches.length > 0) {
      return phraseMatches
    }

    // Otherwise, multi-token AND matching across fields
    const tokens = q.split(/\s+/).filter(Boolean)
    return packages.filter((pkg) => tokens.every((token) => matchField(pkg, token)))
  }, [packages, searchTerm])

  return (
    <main className="flex flex-col gap-4 px-8 py-7">
      <header className="flex flex-col gap-1.5">
        <h1 className="m-0 font-title text-2xl font-bold">Version Control</h1>
        <p className="m-0 text-[13px] text-grey">Alle klanten en hun mapping packages.</p>
      </header>

      {/* Search on customer name: implemented in user story 159 */}
      <label className="flex w-120 items-center gap-2.5 rounded-small border border-line-grey bg-white px-3.5 py-[11px]">
        <img src={iconSearch} alt="" width={18} height={18} />
        <input
          type="search"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Zoek een klant op naam…"
          aria-label="Zoek een klant op naam"
          className="flex-1 bg-transparent text-[13px] text-anthracite placeholder:text-grey focus:outline-none"
        />
      </label>

      {loading && (
        <div className="rounded-medium border border-line-grey bg-white px-4 py-6 text-[13px] text-grey">
          Mapping packages laden…
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-center justify-between gap-4 rounded-medium border border-anthracite bg-white px-4 py-[13px] text-[13px]"
        >
          <span>De mapping packages konden niet geladen worden.</span>
          <button type="button" className="btn" onClick={() => void fetchPackages()}>
            Opnieuw proberen
          </button>
        </div>
      )}

      {!loading && !error && packages?.length === 0 && (
        <div className="rounded-medium border border-line-grey bg-white px-4 py-6 text-[13px] text-grey">
          Er zijn nog geen mapping packages.
        </div>
      )}

      {!loading && packages && packages.length > 0 && (
        <div className="overflow-hidden rounded-medium border border-line-grey bg-white">
          <table className="w-full table-fixed border-collapse text-[13px] text-anthracite">
            <thead className="border-b border-line-grey bg-background">
              <tr>
                <th className={`${CUSTOMER_CELL} ${HEADER_TEXT}`}>KLANT</th>
                <th className={`${TYPE_CELL} ${HEADER_TEXT}`}>TYPE</th>
                <th className={`${VERSION_CELL} ${HEADER_TEXT}`}>ACTIEVE VERSIE</th>
                <th className={`${CHANGE_CELL} ${HEADER_TEXT}`}>LAATSTE WIJZIGING</th>
                <th className={`${ACTION_CELL} ${HEADER_TEXT} text-right`}>ACTIE</th>
              </tr>
            </thead>
            <tbody>
              {filteredPackages.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-[13px] text-grey">
                    Geen mapping packages gevonden die voldoen aan de zoekcriteria.
                  </td>
                </tr>
              ) : (
                filteredPackages.map((mappingPackage) => {
                  const displayVersion = mappingPackage.activeVersion || mappingPackage.latestVersion
                  const changeDate = mappingPackage.activeUpdatedAt || mappingPackage.createdAt
                  const changeUser = mappingPackage.activeUpdatedBy || mappingPackage.createdBy

                  return (
                    // A company can be listed once per package type (e.g. nouryon inbound + nouryon outbound)
                    <tr
                      key={`${mappingPackage.company}/${mappingPackage.packageType ?? ''}`}
                      className="border-b border-line-grey last:border-b-0"
                    >
                      <td className={`${CUSTOMER_CELL} ${BODY_CELL} truncate font-semibold`}>
                        {mappingPackage.customerName || mappingPackage.company}
                      </td>
                      <td className={`${TYPE_CELL} ${BODY_CELL} truncate`} title={mappingPackage.packageType ?? undefined}>
                        {mappingPackage.packageType || '—'}
                      </td>
                      <td className={`${VERSION_CELL} ${BODY_CELL} font-semibold`}>
                        {displayVersion}
                      </td>
                      <td className={`${CHANGE_CELL} ${BODY_CELL}`}>
                        <div className="flex flex-col gap-0.5">
                          <span>{changeDate ? formatUploadedAt(changeDate) : '—'}</span>
                          {changeUser && (
                            <span className="text-xs text-grey">door {changeUser}</span>
                          )}
                        </div>
                      </td>
                      <td className={`${ACTION_CELL} ${BODY_CELL}`}>
                        {/* Opens the versions of this customer: user story 161 */}
                        <button
                          type="button"
                          className="btn"
                          onClick={() => navigate(`/package-versions/${mappingPackage.company}/${mappingPackage.packageType}`)}
                        >
                          Bekijken
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      )
      }
    </main >
  )
}