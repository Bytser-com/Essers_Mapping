import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMappingPackageStore } from '../stores/mappingPackageStore'
import { formatUploadedAt } from '../services/proposalOverviewService'

// Column widths 150 / rest / 200 / 160 / 140 px with a 12 px gap; the row has 16 px side padding
// (Figma "08 · Versiegeschiedenis" → "Lijst – versies"). Each cell's width includes its padding.
const VERSION_CELL = 'w-[178px] pl-4 pr-3' // 16 + 150 + 12
const DESCRIPTION_CELL = 'pr-3' // rest of the width
const DATE_CELL = 'w-[212px] pr-3' // 200 + 12
const BY_CELL = 'w-[172px] pr-3' // 160 + 12
const ACTION_CELL = 'w-[156px] pr-4 text-right' // 140 + 16

const HEADER_TEXT = 'py-2.5 text-left align-middle text-[11px] font-bold tracking-[0.66px] text-grey'
const BODY_CELL = 'py-[13px] align-middle'

// Version history of one mapping package (Figma "08 · Versiegeschiedenis")
export default function PackageVersions() {
  const { company, packageType } = useParams()
  const versions = useMappingPackageStore((state) => state.versions)
  const loading = useMappingPackageStore((state) => state.versionsLoading)
  const error = useMappingPackageStore((state) => state.versionsError)
  const fetchVersions = useMappingPackageStore((state) => state.fetchVersions)

  useEffect(() => {
    if (company && packageType) {
      void fetchVersions(company, packageType)
    }
  }, [company, packageType, fetchVersions])

  const activeVersion = versions?.find((version) => version.isActive)

  return (
    <main className="flex flex-col gap-4 px-8 py-7">
      <header className="flex flex-col gap-1.5">
        <nav className="flex gap-2 text-xs text-grey">
          <Link to="/version-control" className="hover:underline">
            Version Control
          </Link>
          <span>/</span>
          <span>{company}</span>
        </nav>

        <div className="flex items-center gap-3">
          <h1 className="m-0 font-title text-2xl font-bold">{company}</h1>
          {activeVersion && <span className="status status--ready">Actief: {activeVersion.version}</span>}
        </div>

        <p className="m-0 text-[13px] text-grey">
          Mapping package · {packageType}
          {versions && ` · ${versions.length} versies`}
        </p>
      </header>

      <h2 className="m-0 font-title text-base font-bold">Versiegeschiedenis</h2>

      {loading && (
        <div className="rounded-medium border border-line-grey bg-white px-4 py-6 text-[13px] text-grey">
          Versies laden…
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-center justify-between gap-4 rounded-medium border border-anthracite bg-white px-4 py-[13px] text-[13px]"
        >
          <span>De versies konden niet geladen worden.</span>
          <button
            type="button"
            className="btn"
            onClick={() => company && packageType && void fetchVersions(company, packageType)}
          >
            Opnieuw proberen
          </button>
        </div>
      )}

      {!loading && !error && versions?.length === 0 && (
        <div className="rounded-medium border border-line-grey bg-white px-4 py-6 text-[13px] text-grey">
          Er zijn nog geen versies voor dit mapping package.
        </div>
      )}

      {!loading && versions && versions.length > 0 && (
        <div className="overflow-hidden rounded-medium border border-line-grey bg-white">
          <table className="w-full table-fixed border-collapse text-[13px] text-anthracite">
            <thead className="border-b border-line-grey bg-background">
              <tr>
                <th className={`${VERSION_CELL} ${HEADER_TEXT}`}>VERSIE</th>
                <th className={`${DESCRIPTION_CELL} ${HEADER_TEXT}`}>OMSCHRIJVING</th>
                <th className={`${DATE_CELL} ${HEADER_TEXT}`}>GOEDGEKEURD OP</th>
                <th className={`${BY_CELL} ${HEADER_TEXT}`}>DOOR</th>
                <th className={`${ACTION_CELL} ${HEADER_TEXT} text-right`}>ACTIE</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((version) => (
                <tr key={version.version} className="border-b border-line-grey last:border-b-0">
                  <td className={`${VERSION_CELL} ${BODY_CELL}`}>
                    {version.isActive ? (
                      <div className="flex items-center gap-2">
                        <span className="status status--ready">{version.version}</span>
                        <span className="status status--success">Actief</span>
                      </div>
                    ) : (
                      <span className="font-semibold">{version.version}</span>
                    )}
                  </td>
                  <td className={`${DESCRIPTION_CELL} ${BODY_CELL} whitespace-normal break-words`}>
                    {version.description || '—'}
                  </td>
                  <td className={`${DATE_CELL} ${BODY_CELL}`}>
                    {version.createdAt ? formatUploadedAt(version.createdAt) : '—'}
                  </td>
                  <td className={`${BY_CELL} ${BODY_CELL}`}>{version.createdBy || '—'}</td>
                  <td className={`${ACTION_CELL} ${BODY_CELL}`}>
                    {/* Opens this version: user story 62 (Figma "09 · Versie bekijken") */}
                    <button type="button" className="btn">
                      Openen
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}