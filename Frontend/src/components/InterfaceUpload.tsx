import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import iconUpload from '../assets/home/icon-upload.svg'
import iconError from '../assets/home/icon-error.svg'

type InterfaceUploadProps = {
  onUpload?: (file: File) => void
}

// Upload card on the Home page (user story 60)
function InterfaceUpload({ onUpload }: InterfaceUploadProps) {
  const fileInput = useRef<HTMLInputElement>(null)
  // Customer name is only kept in the field for now, saving it is another user story
  const [customerName, setCustomerName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [showError, setShowError] = useState(false)

  function chooseFile(chosen: File | undefined) {
    if (!chosen) return
    setFile(chosen)
    setShowError(false)
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.target.files?.[0])
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    chooseFile(event.dataTransfer.files[0])
  }

  function handleUpload() {
    if (!file) return
    // Only XML files are allowed
    if (!file.name.toLowerCase().endsWith('.xml')) {
      setShowError(true)
      return
    }
    // TODO: send the file to the backend when the upload endpoint is ready
    onUpload?.(file)
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
            onChange={(event) => setCustomerName(event.target.value)}
            className="w-full rounded-lg border border-[#e3e3e8] bg-white px-3 py-[10px] text-[13px]"
          />
        </div>

        <div
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          className="flex flex-1 flex-col items-center gap-2 rounded-[10px] border border-dashed border-[#a1a1ab] bg-[#f4f4f6] px-5 py-[18px]"
        >
          <img src={iconUpload} alt="" width={26} height={26} />
          <p className="text-[13px] font-semibold">Sleep een XML-bestand hierheen</p>
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
            onChange={handleFileChange}
            className="hidden"
            data-testid="file-input"
          />
          <p className="text-[12px] text-[#6b6b73]">Alleen XML-bestanden</p>
          {file && <p className="text-[13px] font-semibold">Gekozen: {file.name}</p>}
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

      {showError && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-[#1c1c1f] bg-white px-4 py-3">
          <img src={iconError} alt="" width={18} height={18} />
          <div className="flex flex-col gap-[2px]">
            <p className="text-[13px] font-semibold">Upload mislukt: dit is geen XML-bestand.</p>
            <p className="text-[12px] text-[#6b6b73]">Kies een XML-bestand van de klant en probeer opnieuw.</p>
          </div>
        </div>
      )}
    </>
  )
}

export default InterfaceUpload
