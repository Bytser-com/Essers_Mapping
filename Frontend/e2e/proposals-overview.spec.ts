// E2E tests for the proposals overview on Home, in a real browser.
// User story: "Als analist wil ik een overzicht van alle klanten en hun mapping packages,
// zodat ik snel naar het juiste package kan gaan." (TC-57-01 to TC-57-10)
//
// No backend is needed: page.route answers /api/proposal/* the way the Mapping_Proposal
// backend does. What only the backend decides (sorting, skipping broken data) is tested with
// pytest in Mapping_Proposal/tests/ (TC-57-03 and TC-57-01).
// Each test has the key of its Test issue in Jira (Xray), so the results can be imported.

import { expect, test, type Page } from '@playwright/test'

// Links a test to its Test issue in Xray
const xrayTest = (key: string) => ({ annotation: { type: 'test_key', description: key } })

// Dates are shown in the browser's timezone: use the one of the analisten.
test.use({ timezoneId: 'Europe/Brussels', locale: 'nl-BE' })

const PROPOSALS_API = '**/api/proposal/proposals'
const UPLOAD_API = '**/api/proposal/upload'

type Proposal = {
  id: string
  customer: string
  version: number
  uploaded_at: string
  status: string
  ai_status: string | null
  can_open: boolean
}

function proposal(customer: string, overrides: Partial<Proposal> = {}): Proposal {
  const folder = customer.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  const version = overrides.version ?? 1
  return {
    id: `${folder}/v${version}`,
    customer,
    version,
    uploaded_at: '2026-10-22T14:05:00+02:00',
    status: 'READY_FOR_REVIEW',
    ai_status: null,
    can_open: true,
    ...overrides,
  }
}

function list(...proposals: Proposal[]) {
  return { total: proposals.length, proposals }
}

// Answers the proposals API with the given responses, one per request; the last one keeps
// repeating. A number is answered as an HTTP error with that status.
async function mockProposals(page: Page, ...responses: Array<object | number>): Promise<() => number> {
  let calls = 0
  await page.route(PROPOSALS_API, (route) => {
    const response = responses[Math.min(calls, responses.length - 1)]
    calls += 1
    if (typeof response === 'number') {
      return route.fulfill({ status: response, json: { detail: 'Cannot connect to SFTP sftp-shared:22' } })
    }
    return route.fulfill({ json: response })
  })
  return () => calls
}

function proposalsSection(page: Page) {
  return page.getByTestId('proposal-overview')
}

function rowOf(page: Page, customer: string) {
  return page.getByRole('row').filter({ has: page.getByRole('cell', { name: customer, exact: true }) })
}

test.describe('E2E - Proposals overview on Home', () => {
  test('TC-57-02 the overview shows one row per customer with its latest version', xrayTest('IT2627T06-128'), async ({ page }) => {
    // The backend sends only the latest version per customer
    await mockProposals(
      page,
      list(proposal('Klant A', { version: 2 }), proposal('Klant B'), proposal('Klant C', { version: 10 })),
    )

    await page.goto('/')

    const section = proposalsSection(page)
    await expect(section.getByRole('heading', { name: 'Proposals' })).toBeVisible()
    await expect(page.getByTestId('proposal-count')).toHaveText('3')
    await expect(section.getByRole('row')).toHaveCount(4) // header + 3 customers
    await expect(rowOf(page, 'Klant A').getByRole('cell').nth(1)).toHaveText('v2')
    await expect(rowOf(page, 'Klant B').getByRole('cell').nth(1)).toHaveText('v1')
    await expect(rowOf(page, 'Klant C').getByRole('cell').nth(1)).toHaveText('v10')
  })

  test('TC-57-04 each row shows customer, version, date and time of upload and status', xrayTest('IT2627T06-130'), async ({ page }) => {
    await mockProposals(
      page,
      list(
        proposal('Klant A', { uploaded_at: '2026-10-22T14:05:00+02:00' }),
        proposal('Klant B', { uploaded_at: '2026-01-05T08:07:00+01:00' }),
        proposal('Klant C', { uploaded_at: '2026-10-25T09:00:00Z' }), // day of the change to winter time
      ),
    )

    await page.goto('/')

    const headers = proposalsSection(page).getByRole('columnheader')
    await expect(headers).toHaveText(['KLANT', 'VERSIE', 'GEÜPLOAD OP', 'STATUS', 'AI-STATUS', 'ACTIE'])
    const cells = rowOf(page, 'Klant A').getByRole('cell')
    await expect(cells.nth(0)).toHaveText('Klant A')
    await expect(cells.nth(1)).toHaveText('v1')
    await expect(cells.nth(2)).toHaveText('22/10/2026 14:05')
    await expect(cells.nth(3)).toHaveText('Klaar om na te kijken')
    await expect(rowOf(page, 'Klant B').getByRole('cell').nth(2)).toHaveText('05/01/2026 08:07')
    await expect(rowOf(page, 'Klant C').getByRole('cell').nth(2)).toHaveText('25/10/2026 10:00')
  })

  test('TC-57-05 statuses and AI statuses are shown in Dutch', xrayTest('IT2627T06-131'), async ({ page }) => {
    await mockProposals(
      page,
      list(
        proposal('Klant A', { status: 'AI_GENERATING', ai_status: 'RUNNING', can_open: false }),
        proposal('Klant B', { status: 'READY_FOR_REVIEW' }),
        proposal('Klant C', { status: 'IN_REVIEW' }),
        proposal('Klant D', { status: 'AI_CHECKING_REVIEW', ai_status: 'RUNNING' }),
        proposal('Klant E', { status: 'RETURNED', ai_status: 'FAILED' }),
      ),
    )

    await page.goto('/')

    const expected: Array<[string, string, string]> = [
      ['Klant A', 'AI maakt voorstel', 'Bezig'],
      ['Klant B', 'Klaar om na te kijken', '—'],
      ['Klant C', 'In review', '—'],
      ['Klant D', 'AI controleert review van analist', 'Bezig'],
      ['Klant E', 'Teruggestuurd', 'Mislukt'],
    ]
    for (const [customer, status, aiStatus] of expected) {
      const cells = rowOf(page, customer).getByRole('cell')
      await expect(cells.nth(3)).toHaveText(status)
      await expect(cells.nth(4)).toHaveText(aiStatus)
    }
  })

  test('TC-57-06 "Openen" goes to the package of the customer and is disabled while the AI is busy', xrayTest('IT2627T06-132'), async ({ page }) => {
    await mockProposals(
      page,
      list(
        proposal('Klant A', { status: 'AI_GENERATING', ai_status: 'RUNNING', can_open: false }),
        proposal('Voorbeeldbedrijf B', { version: 2 }),
      ),
    )
    let pageLoads = 0
    page.on('load', () => (pageLoads += 1))

    await page.goto('/')

    await expect(rowOf(page, 'Klant A').getByRole('button', { name: 'Openen' })).toBeDisabled()
    await rowOf(page, 'Voorbeeldbedrijf B').getByRole('button', { name: 'Openen' }).click()

    // Only the address is checked: what that page shows belongs to another user story.
    await expect(page).toHaveURL(/\/proposals\/voorbeeldbedrijf-b$/)
    expect(pageLoads).toBe(1) // navigated inside the app, no page reload
  })

  test('TC-57-07 a status change is visible within 10 seconds without reloading the page', xrayTest('IT2627T06-133'), async ({ page }) => {
    const busy = proposal('Klant A', { status: 'AI_GENERATING', ai_status: 'RUNNING', can_open: false })
    const ready = proposal('Klant A')
    const calls = await mockProposals(page, list(busy), list(busy), list(ready))
    let pageLoads = 0
    page.on('load', () => (pageLoads += 1))

    await page.goto('/')
    const row = rowOf(page, 'Klant A')
    await expect(row.getByText('Bezig')).toBeVisible()

    await expect(row.getByText('Klaar om na te kijken')).toBeVisible({ timeout: 10_000 })
    await expect(row.getByRole('button', { name: 'Openen' })).toBeEnabled()
    expect(pageLoads).toBe(1)

    // When nothing is busy anymore, the list stops refreshing
    const callsWhenDone = calls()
    await page.waitForTimeout(5_000)
    expect(calls()).toBe(callsWhenDone)
  })

  test('TC-57-07 a failed AI run is shown as "Mislukt" within 10 seconds', xrayTest('IT2627T06-133'), async ({ page }) => {
    const busy = proposal('Klant A', { status: 'AI_GENERATING', ai_status: 'RUNNING', can_open: false })
    await mockProposals(page, list(busy), list({ ...busy, ai_status: 'FAILED' }))

    await page.goto('/')

    await expect(rowOf(page, 'Klant A').getByText('Mislukt')).toBeVisible({ timeout: 10_000 })
  })

  test('TC-57-08 after a successful upload the new proposal appears without reloading the page', xrayTest('IT2627T06-134'), async ({ page }) => {
    const klantB = proposal('Klant B')
    const klantA = proposal('Klant A', {
      uploaded_at: new Date().toISOString(),
      status: 'AI_GENERATING',
      ai_status: 'RUNNING',
      can_open: false,
    })
    let uploaded = false
    await page.route(PROPOSALS_API, (route) => route.fulfill({ json: uploaded ? list(klantA, klantB) : list(klantB) }))
    await page.route(UPLOAD_API, (route) => {
      uploaded = true
      return route.fulfill({ status: 201, json: { upload_id: 'test', customer: 'Klant A', files: ['order.xml'] } })
    })
    let pageLoads = 0
    page.on('load', () => (pageLoads += 1))

    await page.goto('/')
    await expect(rowOf(page, 'Klant B')).toBeVisible()

    await page.getByLabel('Klantnaam').fill('Klant A')
    await page.getByTestId('file-input').setInputFiles({ name: 'order.xml', mimeType: 'text/xml', buffer: Buffer.from('<root />') })
    await page.getByRole('button', { name: 'Uploaden' }).click()

    await expect(page.getByRole('status')).toContainText('Upload gelukt. De AI is bezig met een mapping proposal voor Klant A.')
    const row = rowOf(page, 'Klant A')
    await expect(row).toBeVisible({ timeout: 10_000 })
    await expect(row.getByRole('cell').nth(1)).toHaveText('v1')
    await expect(row.getByRole('cell').nth(3)).toHaveText('AI maakt voorstel')
    await expect(row.getByRole('cell').nth(4)).toHaveText('Bezig')
    await expect(row.getByRole('button', { name: 'Openen' })).toBeDisabled()
    await expect(page.getByTestId('proposal-count')).toHaveText('2')
    expect(pageLoads).toBe(1)
  })

  test('TC-57-09 without proposals the empty message and 0 are shown', xrayTest('IT2627T06-135'), async ({ page }) => {
    await mockProposals(page, list())

    await page.goto('/')

    await expect(proposalsSection(page).getByText('Er zijn nog geen proposals. Upload een interface om te beginnen.')).toBeVisible()
    await expect(page.getByTestId('proposal-count')).toHaveText('0')
    await expect(proposalsSection(page).getByRole('table')).toHaveCount(0)
  })

  test('TC-57-10 loading message, error with "Opnieuw proberen" and retry', xrayTest('IT2627T06-136'), async ({ page }) => {
    // First answer is slow, so the loading message can be seen; then 503 (SFTP unreachable)
    let calls = 0
    let releaseFirst: () => void = () => {}
    const firstAnswered = new Promise<void>((resolve) => (releaseFirst = resolve))
    await page.route(PROPOSALS_API, async (route) => {
      calls += 1
      if (calls === 1) {
        await firstAnswered
        return route.fulfill({ status: 503, json: { detail: 'Cannot connect to SFTP sftp-shared:22' } })
      }
      return route.fulfill({ json: list(proposal('Klant A')) })
    })

    await page.goto('/')
    await expect(proposalsSection(page).getByText('Proposals laden…')).toBeVisible()
    releaseFirst()

    const alert = proposalsSection(page).getByRole('alert')
    await expect(alert).toContainText('De proposals konden niet geladen worden.')

    await alert.getByRole('button', { name: 'Opnieuw proberen' }).click()

    await expect(rowOf(page, 'Klant A')).toBeVisible()
    await expect(proposalsSection(page).getByRole('alert')).toHaveCount(0)
  })
})
