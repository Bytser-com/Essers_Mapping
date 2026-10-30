// Calls the upload endpoint of the Mapping Proposal API (POST /upload).
// The endpoint lives in Mapping_Proposal/routers/upload.py and saves the XML
// in Mapping_Proposal/data/source/, where the AI pipeline reads it.
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function uploadInterface(file: File): Promise<void> {
  const body = new FormData()
  body.append('file', file)

  // fetch only fails here when the API cannot be reached (not started, wrong URL)
  const res = await fetch(`${API_URL}/upload`, { method: 'POST', body }).catch(() => {
    throw new Error('Upload mislukt: de server is niet bereikbaar.')
  })
  if (!res.ok) {
    // The API sends the reason in "detail", e.g. "Upload mislukt: dit is geen XML-bestand."
    const data = await res.json().catch(() => null)
    throw new Error(data?.detail ?? `Upload mislukt (status ${res.status}).`)
  }
}
