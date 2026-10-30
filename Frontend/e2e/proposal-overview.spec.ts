// Fit criteria: the AI makes a mapping proposal for an uploaded XML – the part the analist
// sees in the list on Home, tested end-to-end in a real browser. The backend part (proposal
// per upload, Excel on SFTP, status when the AI is done) is tested in
// Mapping_Proposal/tests/integration/test_proposal.py.
//
//   FC3  Zodra de AI klaar is, krijgt de proposal in de lijst op Home de status "Klaar om na te kijken".
//   TC   Na een geslaagde upload staat er een nieuwe rij in de lijst op Home met de klantnaam,
//        de versie, de datum en tijd van upload en de status "AI maakt voorstel".
//        Techniek: equivalence partitioning (geldig bestand). Voorwaarde: TC-60-01 net uitgevoerd.
//        Testdata: order_ostavel.xml, klantnaam Ostavel.
//
// No backend is needed: page.route answers GET /api/proposal/proposals the way the
// Mapping_Proposal backend does.
import { expect, test, type Page } from '@playwright/test'

// Dates are shown in the browser's timezone: use the one of the analisten.
test.use({ timezoneId: 'Europe/Brussels', locale: 'nl-BE' })

const PROPOSALS_API = '**/api/proposal/proposals'

// The row the backend returns right after Ostavel uploaded order_ostavel.xml.
const ostavelBusy = {
  id: 'ostavel/v1',
  customer: 'Ostavel',
  version: 1,
  uploaded_at: '2026-10-30T13:30:00+01:00',
  status: 'AI_GENERATING',
  ai_status: 'RUNNING',
  can_open: false,
}
const ostavelReady = { ...ostavelBusy, status: 'READY_FOR_REVIEW', ai_status: null, can_open: true }

function list(...proposals: object[]) {
  return { total: proposals.length, proposals }
}

// Answers the proposals API with the given lists, one per request; the last one keeps repeating.
async function mockProposals(page: Page, ...responses: object[]): Promise<() => number> {
  let calls = 0
  await page.route(PROPOSALS_API, (route) => {
    const body = responses[Math.min(calls, responses.length - 1)]
    calls += 1
    return route.fulfill({ json: body })
  })
  return () => calls
}

test.describe('Fit criteria – AI mapping proposal, list on Home', () => {
  test('TC: after a successful upload a new row shows Ostavel, v1, date/time of upload and "AI maakt voorstel"', async ({ page }) => {
    await mockProposals(page, list(ostavelBusy))

    await page.goto('/')

    const row = page.getByRole('row', { name: /Ostavel/ })
    await expect(row).toBeVisible()
    await expect(row.getByRole('cell').nth(0)).toHaveText('Ostavel')
    await expect(row.getByRole('cell').nth(1)).toHaveText('v1')
    await expect(row.getByRole('cell').nth(2)).toHaveText('30/10/2026 13:30')
    await expect(row.getByRole('cell').nth(3)).toHaveText('AI maakt voorstel')
    await expect(row.getByRole('cell').nth(4)).toHaveText('Bezig')
    await expect(row.getByRole('button', { name: 'Openen' })).toBeDisabled()
  })

  test('FC3: as soon as the AI is done, the row shows "Klaar om na te kijken" (without reloading the page)', async ({ page }) => {
    const calls = await mockProposals(page, list(ostavelBusy), list(ostavelReady))
    let pageLoads = 0
    page.on('load', () => (pageLoads += 1))

    await page.goto('/')
    const row = page.getByRole('row', { name: /Ostavel/ })
    await expect(row.getByText('AI maakt voorstel')).toBeVisible()

    // The list refreshes by itself while the AI is busy; the new status must appear within 10 seconds.
    await expect(row.getByText('Klaar om na te kijken')).toBeVisible({ timeout: 10_000 })
    await expect(row.getByText('AI maakt voorstel')).toHaveCount(0)
    await expect(row.getByRole('button', { name: 'Openen' })).toBeEnabled()
    expect(calls()).toBeGreaterThanOrEqual(2) // asked the backend again ...
    expect(pageLoads).toBe(1) // ... without reloading the page
  })

  test('"Openen" goes to the page of that customer: /proposals/<customer>', async ({ page }) => {
    await mockProposals(page, list(ostavelReady))
    let pageLoads = 0
    page.on('load', () => (pageLoads += 1))

    await page.goto('/')
    await page.getByRole('row', { name: /Ostavel/ }).getByRole('button', { name: 'Openen' }).click()

    // Only the address is checked: what that page shows belongs to another user story.
    await expect(page).toHaveURL(/\/proposals\/ostavel$/)
    expect(pageLoads).toBe(1) // navigated inside the app, no page reload
  })
})
