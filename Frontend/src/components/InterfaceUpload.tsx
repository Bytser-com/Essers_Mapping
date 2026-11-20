import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { useHomeStore } from '../stores/homeStore'
import iconUpload from '../assets/home/icon-upload.svg'
import iconError from '../assets/home/icon-error.svg'
import iconSuccess from '../assets/home/icon-success.svg'

type UploadError = 'customer' | 'type' | 'noFile' | 'file' | 'server' | null

type MaxLengthHintProps = {
  id: string
  value: string
  max: number
}

// Shown under an input when the maximum number of characters is reached
function MaxLengthHint({ id, value, max }: Readonly<MaxLengthHintProps>) {
  if (value.length < max) return null
  return (
    <p id={id} aria-live="polite" className="text-[12px] text-red">
      Maximaal {max} tekens bereikt.
    </p>
  )
}

// Available proposal types for upload
const PROPOSAL_TYPE_OPTIONS = ['Inbound', 'Outbound'] as const

// Upload card on the Home page (user story 60)
function InterfaceUpload() {
  // Sends all chosen files of one customer to the backend in one request (see stores/homeStore.ts)
  const uploadInterface = useHomeStore((state) => state.uploadInterface)
  const serverMessage = useHomeStore((state) => state.uploadError)
  const fileInput = useRef<HTMLInputElement>(null)
  const [customerName, setCustomerName] = useState('')
  const [proposalType, setProposalType] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [uploadError, setUploadError] = useState<UploadError>(null)
  // Customer name shown in the success message after a successful upload
  const [uploadedFor, setUploadedFor] = useState<string | null>(null)

  // Longest customer name that can be entered (also checked by the backend)
  const MAX_CUSTOMER_LENGTH = 20

  // New files are added to the list, so files can also be chosen one by one
  function chooseFiles(chosen: FileList | null) {
    if (!chosen || chosen.length === 0) return
    const newFiles = Array.from(chosen)
    setFiles((current) => [...current, ...newFiles])
    setUploadError(null)
    setUploadedFor(null)
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    chooseFiles(event.target.files)
    // Clear the input so the same file can be chosen again after removing it
    event.target.value = ''
  }

  // Removes one chosen file before uploading
  function removeFile(index: number) {
    setFiles((current) => current.filter((_, i) => i !== index))
    setUploadedFor(null)
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    chooseFiles(event.dataTransfer.files)
  }

  async function handleUpload() {
    setUploadedFor(null)
    setUploadError(null)
    if (!customerName.trim()) {
      setUploadError('customer')
      return
    }

    if (!proposalType.trim()) {
      setUploadError('type')
      return
    }

    // A file must be chosen before uploading
    if (files.length === 0) {
      setUploadError('noFile')
      return
    }
    // Only XML files are allowed, nothing is sent if one of them is not XML
    if (files.some((file) => !file.name.toLowerCase().endsWith('.xml'))) {
      setUploadError('file')
      return
    }

    // Send all files together: the AI makes one proposal for this upload
    const succeeded = await uploadInterface(customerName.trim(), proposalType.trim(), files)
    if (succeeded) {
      setUploadedFor(customerName.trim())
      // The files are sent: empty the list, so the same files are not uploaded twice by accident
      setFiles([])
    } else {
      setUploadError('server')
    }
  }

  return (
    <>
      <section className="flex items-start gap-5 rounded-xl border border-[#e3e3e8] bg-white p-5">
        <div className="flex w-[300px] shrink-0 flex-col gap-2">
          <h2 className="font-['Montserrat',sans-serif] text-[16px] font-bold">Interface uploaden</h2>
          <label htmlFor="customer-name" className="text-[12px] font-medium text-[#6b6b73]">
            Klantnaam
          </label>
          <input
            id="customer-name"
            type="text"
            maxLength={MAX_CUSTOMER_LENGTH}
            aria-describedby="customer-name-max"
            value={customerName}
            onChange={(event) => {
              setCustomerName(event.target.value)
              setUploadError(null)
            }}
            className="w-full rounded-lg border border-[#e3e3e8] bg-white px-3 py-[10px] text-[13px]"
          />
          <MaxLengthHint id="customer-name-max" value={customerName} max={MAX_CUSTOMER_LENGTH} />
          <label htmlFor="proposal-type" className="text-[12px] font-medium text-[#6b6b73]">
            Type
          </label>
          <div className="relative">
            <select
              id="proposal-type"
              name="proposal-type"
              value={proposalType}
              onChange={(event) => {
                setProposalType(event.target.value)
                setUploadError(null)
              }}
              className="w-full cursor-pointer appearance-none rounded-lg border border-[#e3e3e8] bg-white px-3 py-[10px] pr-8 text-[13px] text-[#1c1c1f] focus:border-[#1c1c1f] focus:outline-none"
            >
              <option value="">Selecteer type</option>
              {PROPOSAL_TYPE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-[#6b6b73]">
              <svg className="h-4 w-4 fill-current" viewBox="0 0 20 20" aria-hidden="true">
                <path
                  fillRule="evenodd"
                  d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
          </div>
        </div>

        <div
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          className="flex flex-1 flex-col items-center gap-2 rounded-[10px] border border-dashed border-[#a1a1ab] bg-[#f4f4f6] px-5 py-[18px]"
        >
          <img src={iconUpload} alt="" width={26} height={26} />
          <p className="text-[13px] font-semibold">Sleep XML-bestanden hierheen</p>
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            className="cursor-pointer rounded-lg border border-[#e3e3e8] bg-white px-4 py-[10px] text-[14px] font-semibold transition-colors hover:bg-[#f4f4f6]"
          >
            Bestanden kiezen
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".xml"
            multiple
            onChange={handleFileChange}
            className="hidden"
            data-testid="file-input"
          />
          <p className="text-[12px] text-[#6b6b73]">Alleen XML-bestanden</p>
          {files.length > 0 && (
            <ul className="flex flex-wrap justify-center gap-2">
              {files.map((file, index) => (
                <li
                  key={`${file.name}-${index}`}
                  className="flex items-center gap-2 rounded-full border border-[#e3e3e8] bg-white py-1 pr-2 pl-3 text-[12px] font-semibold"
                >
                  {file.name}
                  <button
                    type="button"
                    onClick={() => removeFile(index)}
                    aria-label={`Verwijder ${file.name}`}
                    className="cursor-pointer rounded-full px-1 text-[14px] leading-none text-[#6b6b73] hover:bg-[#f4f4f6] hover:text-[#1c1c1f]"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex flex-col justify-end self-stretch">
          <button
            type="button"
            onClick={handleUpload}
            className="cursor-pointer rounded-lg bg-[#1c1c1f] px-4 py-[10px] text-[14px] font-semibold text-white transition-opacity hover:opacity-85"
          >
            Uploaden
          </button>
        </div>
      </section>

      {uploadError && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-[#1c1c1f] bg-white px-4 py-3">
          <img src={iconError} alt="" width={18} height={18} />
          <div className="flex flex-col gap-[2px]">
            {uploadError === 'customer' ? (
              <>
                <p className="text-[13px] font-semibold">Upload mislukt: Vul eerst een klant in.</p>
                <p className="text-[12px] text-[#6b6b73]">Vul de klantnaam in en probeer opnieuw.</p>
              </>
            ) : uploadError === 'type' ? (
              <>
                <p className="text-[13px] font-semibold">Upload mislukt: vul eerst een type in.</p>
                <p className="text-[12px] text-[#6b6b73]">Vul het type in en probeer opnieuw.</p>
              </>
            ) : uploadError === 'noFile' ? (
              <>
                <p className="text-[13px] font-semibold">Upload mislukt: kies eerst een XML-bestand.</p>
                <p className="text-[12px] text-[#6b6b73]">Kies een XML-bestand van de klant en probeer opnieuw.</p>
              </>
            ) : uploadError === 'server' ? (
              <p className="text-[13px] font-semibold">{serverMessage}</p>
            ) : (
              <>
                <p className="text-[13px] font-semibold">Upload mislukt: dit is geen XML-bestand.</p>
                <p className="text-[12px] text-[#6b6b73]">Kies een XML-bestand van de klant en probeer opnieuw.</p>
              </>
            )}
          </div>
        </div>
      )}

      {uploadedFor && (
        <div role="status" className="flex items-center gap-3 rounded-lg border border-[#1c1c1f] bg-white px-4 py-3">
          <img src={iconSuccess} alt="" width={18} height={18} />
          <div className="flex flex-col gap-[2px]">
            <p className="text-[13px] font-semibold">
              Upload gelukt. De AI is bezig met een mapping proposal voor {uploadedFor}.
            </p>
            <p className="text-[12px] text-[#6b6b73]">De status volg je hieronder bij Proposals.</p>
          </div>
        </div>
      )}
    </>
  )
}

export default InterfaceUpload