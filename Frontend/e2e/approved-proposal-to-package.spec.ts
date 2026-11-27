// E2E tests for story IT2627T06-187, in a real browser:
// "Als analist wil ik dat een voorstel na een geslaagde AI-controle automatisch een nieuwe
// versie van het mapping package wordt."
//
// The analyst approves a proposal, gets redirected to Home with a confirmation banner,
// and opens the new active version in Version Control.
//
// No backend is needed: page.route answers the Version_Control and Mapping_Converter APIs.
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

type Backend = {
  approveRequests: Array<{ url: URL; body: { description?: string } }>
}

const MAPPINGS = [
  { id: 'MP-001', bronveld: 'Order/Nummer', doelveld: 'Ordernummer', zekerheid: 95, opmerking: '' },
  { id: 'MP-002', bronveld: 'Order/Datum', doelveld: 'Leverdatum', zekerheid: 88, opmerking: '' },
]

// Plays the backend for one proposal of Klant B (v2, outbound) and its mapping package.
async function mockBackend(page: Page): Promise<Backend> {
  let isApproved = false
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
          status: 'In review',
          statusCode: 'IN_REVIEW',
          mappings: MAPPINGS,
        },
      })
    }

    // Overview on Home: once approved and converted, the proposal is removed from the active proposals list
    return route.fulfill({
      json: {
        total: isApproved ? 0 : 1,
        proposals: isApproved
          ? []
          : [
              {
                id: `${FOLDER}/v2`,
                customer: CUSTOMER,
                version: 2,
                proposal_type: 'outbound',
                uploaded_at: '2026-11-20T10:00:00+01:00',
                can_open: true,
                status: 'IN_REVIEW',
                ai_status: null,
              },
            ],
      },
    })
  })

  await page.route(APPROVE_API, (route) => {
    const request = route.request()
    backend.approveRequests.push({ url: new URL(request.url()), body: request.postDataJSON() ?? {} })
    isApproved = true
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

// Home -> open the proposal -> approve with a description -> automatically redirected to Home with success banner
async function approveProposal(page: Page) {
  await page.goto('/')
  await expect(overviewRow(page)).toBeVisible()

  await overviewRow(page).getByRole('button', { name: 'Openen' }).click()
  const approveButton = page.getByRole('button', { name: 'Goedkeuren', exact: true })
  await approveButton.click()
  await page.locator('#approve-description-input').fill(DESCRIPTION)
  await page.getByRole('button', { name: 'Bevestigen' }).click()

  // Approving navigates automatically to Home with approvalMessage
  await expect(page).toHaveURL('/')
}

test.describe('E2E - Approved proposal becomes a mapping package (story 187)', () => {
  test(
    "TC-187-02 Home shows a message after a passed AI review",
    xrayTest('IT2627T06-198'),
    async ({ page }) => {
      const backend = await mockBackend(page)

      await approveProposal(page)

      // The approval was sent for the right proposal, with the description
      expect(backend.approveRequests).toHaveLength(1)
      const [approveRequest] = backend.approveRequests
      expect(Object.fromEntries(approveRequest?.url.searchParams ?? [])).toEqual({
        company: FOLDER,
        version: 'v2',
        proposalType: 'outbound',
      })
      expect(approveRequest?.body.description).toBe(DESCRIPTION)

      // Home shows the approval success banner
      const banner = page.getByTestId('approval-success-banner')
      await expect(banner).toBeVisible()
      await expect(banner).toContainText('Voorstel goedgekeurd.')
      await expect(banner).toContainText(
        'Het voorstel is goedgekeurd en geconverteerd naar een Mapping Package.',
      )
    },
  )

  test(
    'TC-187-01 the new version is the active mapping package in Version Control',
    xrayTest('IT2627T06-197'),
    async ({ page }) => {
      await mockBackend(page)
      await approveProposal(page)

      // Verify approval banner on Home
      const banner = page.getByTestId('approval-success-banner')
      await expect(banner).toBeVisible()

      // Navigate to Version Control
      await page.goto('/version-control')
      const packageRow = page.getByRole('row').filter({ has: page.getByRole('cell', { name: CUSTOMER, exact: true }) })
      await expect(packageRow).toHaveCount(1)
      await expect(packageRow).toContainText('outbound')
      await expect(packageRow).toContainText('v2')
    },
  )

  test('the message can be closed and does not come back after reloading Home', async ({ page }) => {
    await mockBackend(page)
    await approveProposal(page)
    const banner = page.getByTestId('approval-success-banner')
    await expect(banner).toBeVisible()

    await banner.getByRole('button', { name: 'Melding sluiten' }).click()
    await expect(banner).toHaveCount(0)

    await page.reload()
    await expect(page.getByTestId('approval-success-banner')).toHaveCount(0)
  })
})
