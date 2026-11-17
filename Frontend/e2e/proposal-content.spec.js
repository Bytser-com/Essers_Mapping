import { expect, test } from '@playwright/test'

test.use({ timezoneId: 'Europe/Brussels', locale: 'nl-BE' })

const PROPOSAL_API = '**/proposals*'

// Links a test to its Test issue in Jira (Xray), so the results can be imported
const xrayTest = (key) => ({ annotation: { type: 'test_key', description: key } })

const MAPPING = { id: 'MP-001', bronveld: 'Klant/Nummer', doelveld: 'Klantnummer', zekerheid: 92, opmerking: '' }
const REVIEW_MAPPING = { id: 'MP-002', bronveld: null, doelveld: 'Leverdatum', zekerheid: null, opmerking: '' }

const PROPOSAL = {
  klant: 'brunos',
  versie: 1,
  status: 'Klaar om na te kijken',
  geupload: '2026-10-30T10:00:00',
  mappings: [MAPPING],
}

async function mockProposal(page, response) {
  await page.route(PROPOSAL_API, (route) => {
    if (route.request().resourceType() !== 'fetch') {
      return route.continue()
    }
    return route.fulfill(response)
  })
}

// Answers both calls of the proposals API: the overview on Home (no company) and the
// proposal page (?company=<folder>), with the proposals of the given customers.
async function mockHomeAndProposals(page, customers) {
  await page.route(PROPOSAL_API, (route) => {
    if (route.request().resourceType() !== 'fetch') {
      return route.continue()
    }
    const company = new URL(route.request().url()).searchParams.get('company')
    if (!company) {
      const overview = customers.map((c) => ({
        id: `${c.folder}/v${c.proposal.versie}`,
        customer: c.proposal.klant,
        version: c.proposal.versie,
        uploaded_at: '2026-10-30T10:00:00+01:00',
        status: 'READY_FOR_REVIEW',
        ai_status: null,
        can_open: true,
      }))
      return route.fulfill({ json: { total: overview.length, proposals: overview } })
    }
    const customer = customers.find((c) => c.folder === company)
    return customer ? route.fulfill({ json: customer.proposal }) : route.fulfill({ status: 404 })
  })
}

function rowOf(page, customer) {
  return page.getByRole('row').filter({ has: page.getByRole('cell', { name: customer, exact: true }) })
}

test.describe('End-to-End (E2E) - Proposal content', () => {
  test('shows the proposal of the company', async ({ page }) => {
    // Arrange
    await mockProposal(page, { json: PROPOSAL })

    // Act
    await page.goto('/proposals/brunos')

    // Assert
    await expect(page.getByText('brunos · v1')).toBeVisible()
    await expect(page.getByText('Geüpload op 30/10/2026 om 10:00')).toBeVisible()
    await expect(page.getByText('Klant/Nummer')).toBeVisible()
  })

  test('TC-89-01 "Openen" opens the proposal of the right customer', xrayTest('IT2627T06-123'), async ({ page }) => {
    // Arrange: two customers with their own mappings
    const customerA = { ...PROPOSAL, klant: 'Klant A', mappings: [{ ...MAPPING, bronveld: 'KlantA/Nummer' }] }
    const customerB = { ...PROPOSAL, klant: 'Klant B', mappings: [{ ...MAPPING, bronveld: 'KlantB/Nummer' }] }
    await mockHomeAndProposals(page, [
      { folder: 'klant-a', proposal: customerA },
      { folder: 'klant-b', proposal: customerB },
    ])

    // Act
    await page.goto('/')
    await rowOf(page, 'Klant A').getByRole('button', { name: 'Openen' }).click()

    // Assert
    await expect(page.getByRole('heading', { name: 'Klant A · v1' })).toBeVisible()
    await expect(page.getByText('KlantA/Nummer')).toBeVisible()

    // Act: back to Home, open the other customer
    await page.goBack()
    await rowOf(page, 'Klant B').getByRole('button', { name: 'Openen' }).click()

    // Assert
    await expect(page.getByRole('heading', { name: 'Klant B · v1' })).toBeVisible()
    await expect(page.getByText('KlantB/Nummer')).toBeVisible()
    await expect(page.getByText('KlantA/Nummer')).toHaveCount(0)
  })

  test('TC-89-02 the active version is shown with its status', xrayTest('IT2627T06-124'), async ({ page }) => {
    // Arrange: Klant A has v1 and v2. Version_Control only sends the active version (v2),
    // which is tested in SftpProposalStorageServiceTest.
    const activeVersion = {
      ...PROPOSAL,
      klant: 'Klant A',
      versie: 2,
      status: 'In review',
      mappings: [{ ...MAPPING, bronveld: 'Versie2/Nummer' }],
    }
    await mockHomeAndProposals(page, [{ folder: 'klant-a', proposal: activeVersion }])

    // Act
    await page.goto('/')
    await rowOf(page, 'Klant A').getByRole('button', { name: 'Openen' }).click()

    // Assert
    await expect(page.getByRole('heading', { name: 'Klant A · v2' })).toBeVisible()
    await expect(page.getByText('In review', { exact: true })).toBeVisible()
    await expect(page.getByText('Versie2/Nummer')).toBeVisible()
  })

  test('TC-89-03 approving is only possible without REVIEW_REQUIRED', xrayTest('IT2627T06-138'), async ({ page }) => {
    // Arrange: a proposal with a field that needs review
    await mockProposal(page, { json: { ...PROPOSAL, mappings:[REVIEW_MAPPING] } })

    // Act
    await page.goto('/proposals/brunos')

    // Assert
    await expect(page.getByText('REVIEW_REQUIRED', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Goedkeuren' })).toBeDisabled()

    // Arrange: the same proposal with all fields filled in
    await page.unroute(PROPOSAL_API)
    await mockProposal(page, { json: PROPOSAL })

    // Act
    await page.reload()

    // Assert
    await expect(page.getByText('Klant/Nummer')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Goedkeuren' })).toBeEnabled()
  })

  test('shows an error for an unknown company', async ({ page }) => {
    // Arrange
    await mockProposal(page, { status: 404 })

    // Act
    await page.goto('/proposals/brunos')

    // Assert
    await expect(page.getByText('geen mapping gevonden (status 404)')).toBeVisible()
  })
})