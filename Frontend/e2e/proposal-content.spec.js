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