import { expect, test } from '@playwright/test'

// E2E tests for the proposal page: scores, REVIEW_REQUIRED, the customer name and the Excel download.
// User stories 46 (score), 49 (REVIEW_REQUIRED), 85 (download) and 86 (customer name).
// The Version Control API is replaced by page.route, so no backend is needed.
// Each test has the key of its Test issue in Jira (Xray), so the results can be imported.

test.use({ timezoneId: 'Europe/Brussels', locale: 'nl-BE' })

const PROPOSAL_API = '**/proposals*'
const FILE_API = '**/proposals/file*'

// Links a test to its Test issue in Xray
const xrayTest = (key) => ({ annotation: { type: 'test_key', description: key } })

const MAPPINGS = [
  { id: 'MP-001', bronveld: 'Klant/Nummer', doelveld: 'Klantnummer', zekerheid: 92, opmerking: '' },
  { id: 'MP-002', bronveld: 'Klant/Naam', doelveld: 'Naam', zekerheid: 64, opmerking: '' },
  {
    id: 'MP-003',
    bronveld: null,
    doelveld: 'Leverdatum',
    zekerheid: null,
    opmerking: 'Geen bronveld gevonden in het bestand van de klant.',
  },
]

function proposal(customer) {
  return { klant: customer, versie: 1, status: 'Klaar om na te kijken', geupload: '2026-10-30T10:00:00', mappings: MAPPINGS }
}

// Answers the overview on Home (no company) and the proposal page (?company=<folder>).
async function mockProposals(page, customer, folder) {
  await page.route(PROPOSAL_API, (route) => {
    if (route.request().resourceType() !== 'fetch') {
      return route.continue()
    }
    const company = new URL(route.request().url()).searchParams.get('company')
    if (!company) {
      return route.fulfill({
        json: {
          total: 1,
          proposals: [
            {
              id: `${folder}/v1`,
              customer,
              version: 1,
              uploaded_at: '2026-10-30T10:00:00+01:00',
              status: 'READY_FOR_REVIEW',
              ai_status: null,
              can_open: true,
            },
          ],
        },
      })
    }
    return company === folder ? route.fulfill({ json: proposal(customer) }) : route.fulfill({ status: 404 })
  })
}

function mappingRow(page, targetField) {
  return page.getByRole('row').filter({ has: page.getByText(targetField, { exact: true }) })
}

test.describe('E2E - Proposal page', () => {
  test('TC-46-02 every score has a bar', xrayTest('IT2627T06-104'), async ({ page }) => {
    // Arrange
    await mockProposals(page, 'Klant A', 'klant-a')

    // Act
    await page.goto('/proposals/klant-a')

    // Assert: the table has a column Zekerheid
    await expect(page.getByRole('columnheader', { name: 'Zekerheid' })).toBeVisible()

    // Assert: every row with a score shows the score and a bar
    for (const [field, score] of [['Klantnummer', 92], ['Naam', 64]]) {
      const confidence = mappingRow(page, field).getByTitle(`Betrouwbaarheid: ${score}%`)
      await expect(confidence).toContainText(`${score}%`)
      await expect(confidence.locator('span.relative')).toHaveCount(1)
    }
  })

  test('TC-49-03 REVIEW_REQUIRED field has a label and a comment', xrayTest('IT2627T06-109'), async ({ page }) => {
    // Arrange
    await mockProposals(page, 'Klant A', 'klant-a')

    // Act
    await page.goto('/proposals/klant-a')

    // Assert
    const row = mappingRow(page, 'Leverdatum')
    await expect(row.getByText('REVIEW_REQUIRED', { exact: true })).toBeVisible()
    await expect(row.getByText('Geen bronveld gevonden in het bestand van de klant.')).toBeVisible()
  })

  test('TC-46-03 a REVIEW_REQUIRED field has no score', xrayTest('IT2627T06-105'), async ({ page }) => {
    // Arrange
    await mockProposals(page, 'Klant A', 'klant-a')

    // Act
    await page.goto('/proposals/klant-a')

    // Assert: the table has a column Zekerheid
    await expect(page.getByRole('columnheader', { name: 'Zekerheid' })).toBeVisible()

    // Assert: the REVIEW_REQUIRED row has no score and no bar
    const row = mappingRow(page, 'Leverdatum')
    await expect(row.getByText('REVIEW_REQUIRED', { exact: true })).toBeVisible()
    await expect(row.locator('[title^="Betrouwbaarheid"]')).toHaveCount(0)
  })

  test('TC-86-02 the customer name is shown on Home and in the page title', xrayTest('IT2627T06-114'), async ({ page }) => {
    // Arrange
    await mockProposals(page, 'Klant B', 'klant-b')

    // Act
    await page.goto('/')

    // Assert: column Klant on Home
    const row = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Klant B', exact: true }) })
    await expect(row).toBeVisible()

    // Act: open the proposal
    await row.getByRole('button', { name: 'Openen' }).click()

    // Assert: the page title contains the customer name
    await expect(page.getByRole('heading', { name: 'Klant B · v1' })).toBeVisible()
  })

  test('TC-85-01 Download Excel gives an .xlsx file', xrayTest('IT2627T06-101'), async ({ page }) => {
    // Arrange: a proposal "Klaar om na te kijken" and its Excel file
    await mockProposals(page, 'Klant B', 'klant-b')
    await page.route(FILE_API, (route) =>
      route.fulfill({
        json: {
          company: 'Klant B',
          version: 'v1',
          filename: 'MProposal-KlantB_V1.xlsx',
          fullPath: '/proposals/klant-b/v1/MProposal-KlantB_V1.xlsx',
          contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          sizeBytes: 4,
          createdDate: '2026-10-30T10:00:00Z',
          createdBy: 'Analist A',
          fileContentBase64: Buffer.from('test').toString('base64'),
        },
      }),
    )
    await page.goto('/proposals/klant-b')

    // Assert: the button is there
    const button = page.getByRole('button', { name: 'Download Excel' })
    await expect(button).toBeVisible()

    // Act
    const downloadPromise = page.waitForEvent('download')
    await button.click()
    const download = await downloadPromise

    // Assert
    expect(download.suggestedFilename()).toMatch(/\.xlsx$/)
  })
})
