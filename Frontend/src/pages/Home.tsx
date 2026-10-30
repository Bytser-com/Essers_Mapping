import ProposalOverview from '../components/ProposalOverview'

function Home() {
  return (
    <main data-testid="home-page" className="p-8">
      <h1 className="text-3xl font-bold">Essers Mapping</h1>
      <p className="mt-2 text-zinc-600 dark:text-zinc-400">Welcome to Essers Mapping platform.</p>
      <div className="mt-8">
        <ProposalOverview />
      </div>
    </main>
  )
}

export default Home
