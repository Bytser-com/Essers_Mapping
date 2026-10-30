import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import iconUpload from '../assets/home/icon-upload.svg'
import iconError from '../assets/home/icon-error.svg'
import iconSuccess from '../assets/home/icon-success.svg'

type InterfaceUploadProps = {
  // Sends one file to the backend, called once per chosen file (see services/uploadService.ts)
  onUpload?: (file: File) => void | Promise<void>
}

type UploadError = 'customer' | 'noFile' | 'file' | 'server' | null

// Upload card on the Home page (user story 60)
function InterfaceUpload({ onUpload }: InterfaceUploadProps) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [customerName, setCustomerName] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [uploadError, setUploadError] = useState<UploadError>(null)
  const [serverMessage, setServerMessage] = useState('')
  // Customer name shown in the success message after a successful upload
  const [uploadedFor, setUploadedFor] = useState<string | null>(null)

  // More than one file can be chosen at the same time
  function chooseFiles(chosen: FileList | null) {
    if (!chosen || chosen.length === 0) return
    setFiles(Array.from(chosen))
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

    // Send the files to the backend one by one and show the result
    try {
      for (const file of files) {
        await onUpload?.(file)
      }
      setUploadedFor(customerName.trim())
    } catch (error) {
      setServerMessage(error instanceof Error ? error.message : 'Upload mislukt.')
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
            value={customerName}
            onChange={(event) => {
              setCustomerName(event.target.value)
              setUploadError(null)
            }}
            className="w-full rounded-lg border border-[#e3e3e8] bg-white px-3 py-[10px] text-[13px]"
          />
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
          <p className="text-[13px] font-semibold">
            Upload gelukt. Er is een nieuwe proposal aangemaakt voor {uploadedFor}.
          </p>
        </div>
      )}
    </>
  )
}

export default InterfaceUpload
