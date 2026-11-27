// E2E tests for story IT2627T06-187, in a real browser:
// "Als analist wil ik dat een voorstel na een geslaagde AI-controle automatisch een nieuwe
// versie van het mapping package wordt."
//
// The analyst approves a proposal, goes back to Home, sees the status change to "Goedgekeurd"
// with a message, and opens the new active version in Version Control.
//
// No backend is needed: page.route answers the Version_Control and Mapping_Converter APIs.
// The approve request moves the mocked proposal to "AI-controle bezig"; a few refreshes later
// the AI review "passes" and the proposal becomes APPROVED. What only the backend does (the
// AI review, storing MPackage.json with the description, active.json) is tested with pytest
// in Mapping_Converter/tests/ (test_finalization.py, test_approve.py).
// Each test has the key of its Test issue in Jira (Xray), so the results can be imported.

import { expect, test, type Page } from '@playwright/test'

// Links a test to its Test issue in Xray
const xrayTest = (key: string) => ({ annotation: { type: 'test_key', description: key } })

test.use({ timezoneId: 'Europe/Brussels', locale: 'nl-BE' })

const PROPOSALS_API = '**/proposals*'
const APPROVE_API = '**/api/converter/approve*'
const PACKAGES_API = '**/api/version-control/packages*'

const CUSTOMER = 'Klant B'
const FOLDER = 'klant-b'
const DESCRIPTION = 'Leverdatum mapt nu op DeliveryDate'

// Overview refreshes that still show "AI-controle bezig" before the AI review passes
const CHECKING_REFRESHES = 2
// Home refreshes every 2 seconds while the AI is busy
const STATUS_CHANGE_TIMEOUT = 15_000

type Stage = 'ready' | 'checking' | 'approved'

type Backend = {
  approveRequests: Array<{ url: URL; body: { description?: string } }>
}

const MAPPINGS = [
  { id: 'MP-001', bronveld: 'Order/Nummer', doelveld: 'Ordernummer', zekerheid: 95, opmerking: '' },
  { id: 'MP-002', bronveld: 'Order/Datum', doelveld: 'Leverdatum', zekerheid: 88, opmerking: '' },
]

const OVERVIEW_STATUS: Record<Stage, { status: string; ai_status: string | null }> = {
  ready: { status: 'READY_FOR_REVIEW', ai_status: null },
  checking: { status: 'AI_CHECKING_REVIEW', ai_status: 'RUNNING' },
  approved: { status: 'APPROVED', ai_status: null },
}

const PAGE_STATUS: Record<Stage, { status: string; statusCode: string }> = {
  ready: { status: 'Klaar om na te kijken', statusCode: 'READY_FOR_REVIEW' },
  checking: { status: 'AI-controle bezig', statusCode: 'AI_CHECKING_REVIEW' },
  approved: { status: 'Goedgekeurd', statusCode: 'APPROVED' },
}

// Plays the backend for one proposal of Klant B (v2, outbound) and its mapping package.
async function mockBackend(page: Page): Promise<Backend> {
  let stage: Stage = 'ready'
  let checkingRefreshes = 0
  const backend: Backend = { approveRequests: [] }

  await page.route(PROPOSALS_API, (route) => {
    if (route.request().resourceType() !== 'fetch') {
      return route.continue()
    }
    const company = new URL(route.request().url()).searchParams.get('company')

    if (company) {
      // Proposal page of the customer
      return route.fulfill({
        json: {
          klant: CUSTOMER,
          versie: 2,
          geupload: '2026-11-20T10:00:00',
          proposalType: 'outbound',
          mappings: MAPPINGS,
          ...PAGE_STATUS[stage],
        },
      })
    }

    // Overview on Home: after a few refreshes the AI review has passed
    if (stage === 'checking') {
      checkingRefreshes += 1
      if (checkingRefreshes > CHECKING_REFRESHES) stage = 'approved'
    }
    return route.fulfill({
      json: {
        total: 1,
        proposals: [
          {
            id: `${FOLDER}/v2`,
            customer: CUSTOMER,
            version: 2,
            proposal_type: 'outbound',
            uploaded_at: '2026-11-20T10:00:00+01:00',
            can_open: true,
            ...OVERVIEW_STATUS[stage],
          },
        ],
      },
    })
  })

  await page.route(APPROVE_API, (route) => {
    const request = route.request()
    backend.approveRequests.push({ url: new URL(request.url()), body: request.postDataJSON() ?? {} })
    stage = 'checking'
    checkingRefreshes = 0
    return route.fulfill({
      json: {
        company: FOLDER,
        version: 'v2',
        proposal_type: 'outbound',
        status: 'AI_CHECKING_REVIEW',
        approval_description: DESCRIPTION,
        approved_at: '2026-11-27T10:00:00+01:00',
      },
    })
  })

  // Version Control: the package that the AI review created, v2 is the active version
  await page.route(PACKAGES_API, (route) =>
    route.fulfill({
      json: [
        {
          company: FOLDER,
          latestVersion: 'v2',
          createdAt: '2026-11-27T10:00:30+01:00',
          createdBy: 'analist_a',
          customerName: CUSTOMER,
          packageType: 'outbound',
          activeVersion: 'v2',
          activeUpdatedAt: '2026-11-27T10:00:30+01:00',
          activeUpdatedBy: 'analist_a',
        },
      ],
    }),
  )

  return backend
}

function overviewRow(page: Page) {
  return page
    .getByTestId('proposal-overview')
    .getByRole('row')
    .filter({ has: page.getByRole('cell', { name: CUSTOMER, exact: true }) })
}

// Home -> open the proposal -> approve with a description -> back to Home via the breadcrumb.
// In-app navigation (no page.goto) keeps the list that Home loaded before, like the analyst.
async function approveAndReturnHome(page: Page) {
  await page.goto('/')
  await expect(overviewRow(page)).toContainText('Klaar om na te kijken')

  await overviewRow(page).getByRole('button', { name: 'Openen' }).click()
  // exact: while sending, the dialog button is called "Goedkeuren…"
  const approveButton = page.getByRole('button', { name: 'Goedkeuren', exact: true })
  await approveButton.click()
  await page.locator('#approve-description-input').fill(DESCRIPTION)
  await page.getByRole('button', { name: 'Bevestigen' }).click()
  await expect(page.locator('#approve-description-input')).toHaveCount(0) // dialog closed
  await expect(approveButton).toBeDisabled()

  await page.getByRole('navigation', { name: 'Kruimelpad' }).getByRole('link', { name: 'Home' }).click()
}

test.describe('E2E - Approved proposal becomes a mapping package (story 187)', () => {
  test(
    "TC-187-02 Home shows the status 'Goedgekeurd' and a message after a passed AI review",
    xrayTest('IT2627T06-198'),
    async ({ page }) => {
      const backend = await mockBackend(page)

      await approveAndReturnHome(page)

      // The approval was sent for the right proposal, with the description
      expect(backend.approveRequests).toHaveLength(1)
      const [approveRequest] = backend.approveRequests
      expect(Object.fromEntries(approveRequest?.url.searchParams ?? [])).toEqual({
        company: FOLDER,
        version: 'v2',
        proposalType: 'outbound',
      })
      expect(approveRequest?.body.description).toBe(DESCRIPTION)

      // While the AI is busy, Home refreshes by itself
      await expect(overviewRow(page)).toContainText('AI-controle bezig')
      await expect(overviewRow(page)).toContainText('Goedgekeurd', { timeout: STATUS_CHANGE_TIMEOUT })

      const notice = page.getByTestId('approved-notice')
      await expect(notice).toBeVisible()
      await expect(notice).toContainText('De AI-controle is geslaagd.')
      await expect(notice).toContainText(
        `${CUSTOMER} is goedgekeurd en omgezet naar een mapping package. Je vindt het in Version Control.`,
      )
      await expect(notice.getByRole('button', { name: 'Naar Version Control' })).toBeVisible()
    },
  )

  test(
    'TC-187-01 the new version is the active mapping package in Version Control',
    xrayTest('IT2627T06-197'),
    async ({ page }) => {
      await mockBackend(page)
      await approveAndReturnHome(page)
      const notice = page.getByTestId('approved-notice')
      await expect(notice).toBeVisible({ timeout: STATUS_CHANGE_TIMEOUT })

      await notice.getByRole('button', { name: 'Naar Version Control' }).click()

      await expect(page).toHaveURL(/\/version-control$/)
      await expect(page.getByRole('heading', { name: 'Version Control' })).toBeVisible()
      const packageRow = page.getByRole('row').filter({ has: page.getByRole('cell', { name: CUSTOMER, exact: true }) })
      await expect(packageRow).toHaveCount(1)
      await expect(packageRow).toContainText('outbound')
      await expect(packageRow).toContainText('v2')
    },
  )

  test('the message can be closed and does not come back after reloading Home', async ({ page }) => {
    await mockBackend(page)
    await approveAndReturnHome(page)
    const notice = page.getByTestId('approved-notice')
    await expect(notice).toBeVisible({ timeout: STATUS_CHANGE_TIMEOUT })

    await notice.getByRole('button', { name: 'Melding sluiten' }).click()
    await expect(notice).toHaveCount(0)

    await page.reload()
    await expect(overviewRow(page)).toContainText('Goedgekeurd')
    await expect(page.getByTestId('approved-notice')).toHaveCount(0)
  })
})
