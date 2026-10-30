import InterfaceUpload from '../components/InterfaceUpload'

function Home() {
  return (
    <div data-testid="home-page" className="flex flex-col gap-4 px-8 py-7">
      <div className="flex flex-col gap-[6px]">
        <h1 className="font-['Montserrat',sans-serif] text-[24px] font-bold">Home</h1>
        <p className="text-[13px] text-[#6b6b73]">
          Upload een interface van een klant. De AI maakt er een mapping proposal van.
        </p>
      </div>
      <InterfaceUpload />
    </div>
  )
}

export default Home
