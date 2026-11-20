import { useEffect, useState } from 'react'
import {
  fetchPackageVersions,
  type PackageVersion,
} from '../services/mappingPackageOverviewService'
import { formatUploadedAt } from '../services/proposalOverviewService'

type SelectActivePackageDialogProps = {
  company: string
  customerName: string | null
  packageType: string | null
  onClose: () => void
  onSetActive: (version: string) => Promise<void>
}

export default function SelectActivePackageDialog({
  company,
  customerName,
  packageType,
  onClose,
  onSetActive,
}: Readonly<SelectActivePackageDialogProps>) {
  const [versions, setVersions] = useState<PackageVersion[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activatingVersion, setActivatingVersion] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const abort = new AbortController()

    async function load() {
      if (!packageType) return
      setLoading(true)
      setError(null)
      try {
        const data = await fetchPackageVersions(company, packageType, abort.signal)
        if (active) {
          setVersions(data)
          setLoading(false)
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Kon versies niet ophalen')
          setLoading(false)
        }
      }
    }

    void load()

    return () => {
      active = false
      abort.abort()
    }
  }, [company, packageType])

  const handleActivate = async (version: string) => {
    setActivatingVersion(version)
    try {
      await onSetActive(version)
      // Update local versions state to reflect new active version
      setVersions((prev) =>
        prev
          ? prev.map((v) => ({
              ...v,
              isActive: v.version.toLowerCase() === version.toLowerCase(),
            }))
          : null
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activeren mislukt')
    } finally {
      setActivatingVersion(null)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-anthracite/45"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <dialog
        open
        aria-labelledby="active-package-dialog-title"
        className="static flex flex-col gap-4 w-160 max-w-[calc(100vw-32px)] m-0 p-6 rounded-large bg-white text-anthracite shadow-xl"
      >
        <div className="flex items-start justify-between border-b border-line-grey pb-3">
          <div>
            <h2 id="active-package-dialog-title" className="m-0 font-title text-xl font-bold">
              Versiebeheer mapping package
            </h2>
            <p className="m-0 text-sm text-grey">
              Klant: <span className="font-semibold text-anthracite">{customerName || company}</span> | Type:{' '}
              <span className="font-semibold text-anthracite">{packageType || '—'}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Sluiten"
            className="text-grey hover:text-anthracite text-lg font-bold px-2 py-0.5"
          >
            ✕
          </button>
        </div>

        {loading && (
          <div className="py-6 text-center text-sm text-grey">
            Versies laden…
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="flex items-center justify-between rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700"
          >
            <span>{error}</span>
          </div>
        )}

        {!loading && versions && versions.length === 0 && (
          <div className="py-6 text-center text-sm text-grey">
            Geen versies gevonden voor dit package.
          </div>
        )}

        {!loading && versions && versions.length > 0 && (
          <div className="max-h-80 overflow-y-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-line-grey text-xs font-semibold text-grey">
                  <th className="py-2 pr-3">VERSIE</th>
                  <th className="py-2 pr-3">AANGEMAAKT</th>
                  <th className="py-2 pr-3">OMSCHRIJVING</th>
                  <th className="py-2 text-right">STATUS / ACTIE</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((ver) => (
                  <tr
                    key={ver.version}
                    className={`border-b border-line-grey last:border-b-0 ${
                      ver.isActive ? 'bg-[#F4FAF5]' : ''
                    }`}
                  >
                    <td className="py-2.5 pr-3 font-semibold">
                      {ver.version}
                    </td>
                    <td className="py-2.5 pr-3 text-xs">
                      <div>{ver.createdAt ? formatUploadedAt(ver.createdAt) : '—'}</div>
                      {ver.createdBy && <div className="text-grey">door {ver.createdBy}</div>}
                    </td>
                    <td className="py-2.5 pr-3 text-xs text-grey max-w-[200px] truncate" title={ver.description ?? undefined}>
                      {ver.description || '—'}
                    </td>
                    <td className="py-2.5 text-right">
                      {ver.isActive ? (
                        <span className="inline-flex items-center gap-1 rounded bg-[#EAF5EC] px-2.5 py-1 text-xs font-semibold text-[#1E7E34]">
                          Actief
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="btn text-xs py-1 px-3"
                          disabled={activatingVersion !== null}
                          onClick={() => void handleActivate(ver.version)}
                        >
                          {activatingVersion === ver.version ? 'Activeren…' : 'Actief maken'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex justify-end pt-2 border-t border-line-grey">
          <button type="button" className="btn" onClick={onClose}>
            Sluiten
          </button>
        </div>
      </dialog>
    </div>
  )
}
