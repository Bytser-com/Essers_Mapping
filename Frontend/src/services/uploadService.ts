// Calls the upload endpoint of the Mapping Proposal API (POST /upload).
// The endpoint lives in Mapping_Proposal/routers/upload.py. All files of one upload are
// sent together with the customer name, so the AI makes one proposal for them: the backend
// stores them in one folder in Mapping_Proposal/data/source/ and the AI starts automatically.
//
// Like services/proposals.ts the request goes through /api/proposal: in Kubernetes the
// frontend proxies it to the backend, locally vite.config.js does the same.
// Override with VITE_API_URL (then also set CORS_ORIGINS in the backend .env).
const API_URL: string = import.meta.env.VITE_API_URL ?? '/api/proposal'

export async function uploadInterface(customerName: string, files: File[]): Promise<void> {
  const body = new FormData()
  body.append('customer_name', customerName)
  for (const file of files) {
    body.append('files', file)
  }

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
