// Calls the upload and customer endpoints of the Mapping Proposal API.
// POST /upload saves the XML in the customer directory on SFTP (and data/source/).
// GET /customers returns the list of customer folders from the SFTP server.
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function uploadInterface(file: File, customerName: string): Promise<void> {
  const body = new FormData()
  body.append('file', file)
  body.append('customer_name', customerName)

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

export async function getCustomers(): Promise<string[]> {
  const res = await fetch(`${API_URL}/customers`).catch(() => {
    throw new Error('De server is niet bereikbaar.')
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.detail ?? `Ophalen van klanten mislukt (status ${res.status}).`)
  }
  const data = await res.json()
  return data.customers ?? []
}
