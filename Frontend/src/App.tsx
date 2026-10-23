import { useState } from 'react'
import heroImg from './assets/hero.png'
import reactLogo from './assets/react.svg'
import viteLogo from './assets/vite.svg'

function App() {
  const [count, setCount] = useState(0)

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col border-x border-zinc-200 bg-white text-center text-zinc-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-400">
      <section className="flex flex-col items-center px-6 py-16 sm:px-10 lg:py-24">
        <div className="relative mb-10 flex h-44 w-72 items-center justify-center">
          <img
            src={heroImg}
            className="absolute h-[179px] w-[170px] object-contain"
            width="170"
            height="179"
            alt=""
          />
          <img
            src={reactLogo}
            className="absolute left-4 top-0 h-20 w-20 -rotate-12 drop-shadow-lg"
            alt="React logo"
          />
          <img
            src={viteLogo}
            className="absolute bottom-0 right-4 h-20 w-20 rotate-12 drop-shadow-lg"
            alt="Vite logo"
          />
        </div>

        <div className="max-w-2xl">
          <h1 className="mb-5 text-4xl font-medium tracking-tight text-zinc-950 sm:text-6xl dark:text-zinc-50">
            Get started
          </h1>
          <p className="text-base leading-7 sm:text-lg">
            Edit <code className="rounded bg-stone-100 px-2 py-1 font-mono text-sm text-zinc-950 dark:bg-zinc-800 dark:text-zinc-100">src/App.tsx</code>{' '}
            and save to test <code className="rounded bg-stone-100 px-2 py-1 font-mono text-sm text-zinc-950 dark:bg-zinc-800 dark:text-zinc-100">HMR</code>
          </p>
        </div>
        <button
          type="button"
          className="mt-10 rounded-md bg-purple-600 px-5 py-3 font-mono text-sm font-medium text-white shadow-lg shadow-purple-600/20 transition hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-950"
          onClick={() => setCount((count) => count + 1)}
        >
          Count is {count}
        </button>
      </section>

      <section className="grid border-t border-zinc-200 text-left dark:border-zinc-700 md:grid-cols-2">
        <div className="p-8 sm:p-12">
          <svg className="mb-5 h-8 w-8 text-purple-600" role="presentation" aria-hidden="true">
            <use href="/icons.svg#documentation-icon"></use>
          </svg>
          <h2 className="mb-2 text-xl font-medium text-zinc-950 dark:text-zinc-50">Documentation</h2>
          <p className="mb-6">Your questions, answered</p>
          <ul className="space-y-3">
            <li>
              <a className="inline-flex items-center gap-3 rounded-md px-2 py-1 font-medium text-zinc-700 transition hover:bg-stone-100 hover:text-purple-600 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-purple-400" href="https://vite.dev/" target="_blank" rel="noreferrer">
                <img className="h-5 w-5" src={viteLogo} alt="" />
                Explore Vite
              </a>
            </li>
            <li>
              <a className="inline-flex items-center gap-3 rounded-md px-2 py-1 font-medium text-zinc-700 transition hover:bg-stone-100 hover:text-purple-600 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-purple-400" href="https://react.dev/" target="_blank" rel="noreferrer">
                <img className="h-5 w-5" src={reactLogo} alt="" />
                Learn more
              </a>
            </li>
          </ul>
        </div>
        <div className="border-t border-zinc-200 bg-stone-50 p-8 sm:p-12 md:border-l md:border-t-0 dark:border-zinc-700 dark:bg-zinc-900/50">
          <svg className="mb-5 h-8 w-8 text-purple-600" role="presentation" aria-hidden="true">
            <use href="/icons.svg#social-icon"></use>
          </svg>
          <h2 className="mb-2 text-xl font-medium text-zinc-950 dark:text-zinc-50">Connect with us</h2>
          <p className="mb-6">Join the Vite community</p>
          <ul className="space-y-3">
            <li>
              <a className="inline-flex items-center gap-3 rounded-md px-2 py-1 font-medium text-zinc-700 transition hover:bg-white hover:text-purple-600 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-purple-400" href="https://github.com/vitejs/vite" target="_blank" rel="noreferrer">
                <svg
                  className="h-5 w-5"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#github-icon"></use>
                </svg>
                GitHub
              </a>
            </li>
            <li>
              <a className="inline-flex items-center gap-3 rounded-md px-2 py-1 font-medium text-zinc-700 transition hover:bg-white hover:text-purple-600 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-purple-400" href="https://chat.vite.dev/" target="_blank" rel="noreferrer">
                <svg
                  className="h-5 w-5"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#discord-icon"></use>
                </svg>
                Discord
              </a>
            </li>
            <li>
              <a className="inline-flex items-center gap-3 rounded-md px-2 py-1 font-medium text-zinc-700 transition hover:bg-white hover:text-purple-600 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-purple-400" href="https://x.com/vite_js" target="_blank" rel="noreferrer">
                <svg
                  className="h-5 w-5"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#x-icon"></use>
                </svg>
                X.com
              </a>
            </li>
            <li>
              <a className="inline-flex items-center gap-3 rounded-md px-2 py-1 font-medium text-zinc-700 transition hover:bg-white hover:text-purple-600 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-purple-400" href="https://bsky.app/profile/vite.dev" target="_blank" rel="noreferrer">
                <svg
                  className="h-5 w-5"
                  role="presentation"
                  aria-hidden="true"
                >
                  <use href="/icons.svg#bluesky-icon"></use>
                </svg>
                Bluesky
              </a>
            </li>
          </ul>
        </div>
      </section>
    </main>
  )
}

export default App
