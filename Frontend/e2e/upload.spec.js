import { expect, test } from '@playwright/test'

// E2E tests for the upload card on the Home page.
// User story 48: fill in the customer before uploading (TC-48-01 to TC-48-03)
// User story 60: upload an XML file via the dashboard (TC-60-01 and TC-60-03)
// The upload API (POST /upload) is replaced by a fake response with page.route,
// so these tests run without the Mapping Proposal API.

const xmlFile = {
  name: 'ostavel_levering_001.xml',
  mimeType: 'text/xml',
  buffer: Buffer.from('<root />'),
}

const pdfFile = {
  name: 'ostavel_levering_001.pdf',
  mimeType: 'application/pdf',
  buffer: Buffer.from('%PDF'),
}

test.describe('E2E - Upload card on the Home page', () => {
  // Counts the requests the page sends to the upload API
  let uploadRequests

  test.beforeEach(async ({ page }) => {
    uploadRequests = 0
    await page.route('**/upload', (route) => {
      uploadRequests++
      return route.fulfill({
        status: 201,
        headers: { 'Access-Control-Allow-Origin': '*' },
        json: { file_name: xmlFile.name },
      })
    })
    await page.goto('/')
  })

  test('TC-48-01 upload is not possible with an empty customer name', async ({ page }) => {
    await page.getByTestId('file-input').setInputFiles(xmlFile)
    await page.getByRole('button', { name: 'Uploaden' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
    expect(uploadRequests).toBe(0)
  })

  test('TC-48-02 the missing customer name is shown', async ({ page }) => {
    await page.getByTestId('file-input').setInputFiles(xmlFile)
    await page.getByRole('button', { name: 'Uploaden' }).click()

    await expect(page.getByRole('alert')).toContainText('Vul eerst een klant in.')
  })

  test('TC-48-03 upload works with a customer name and an XML file', async ({ page }) => {
    await page.getByLabel('Klantnaam').fill('Ostavel')
    await page.getByTestId('file-input').setInputFiles(xmlFile)
    await page.getByRole('button', { name: 'Uploaden' }).click()

    await expect(page.getByRole('status')).toBeVisible()
    expect(uploadRequests).toBe(1)
  })

  test('TC-48-04 upload request includes the filled customer name', async ({ page }) => {
    let capturedBody = ''
    await page.route('**/upload', async (route) => {
      capturedBody = route.request().postData() || ''
      return route.fulfill({
        status: 201,
        headers: { 'Access-Control-Allow-Origin': '*' },
        json: { file_name: xmlFile.name, customer_name: 'Ostavel' },
      })
    })

    await page.getByLabel('Klantnaam').fill('Ostavel')
    await page.getByTestId('file-input').setInputFiles(xmlFile)
    await page.getByRole('button', { name: 'Uploaden' }).click()

    await expect(page.getByRole('status')).toBeVisible()
    expect(capturedBody).toContain('name="customer_name"')
    expect(capturedBody).toContain('Ostavel')
  })

  test('TC-60-01 a message is shown after a successful XML upload', async ({ page }) => {
    await page.getByLabel('Klantnaam').fill('Ostavel')
    await page.getByTestId('file-input').setInputFiles(xmlFile)
    await page.getByRole('button', { name: 'Uploaden' }).click()

    await expect(page.getByRole('status')).toHaveText(
      'Upload gelukt. Er is een nieuwe proposal aangemaakt voor Ostavel.',
    )
  })

  test('TC-60-03 a file that is not XML is rejected', async ({ page }) => {
    await page.getByLabel('Klantnaam').fill('Ostavel')

    // No file chosen yet
    await page.getByRole('button', { name: 'Uploaden' }).click()
    await expect(page.getByRole('alert')).toContainText('Upload mislukt: kies eerst een XML-bestand.')

    // A PDF file instead of an XML file
    await page.getByTestId('file-input').setInputFiles(pdfFile)
    await page.getByRole('button', { name: 'Uploaden' }).click()

    await expect(page.getByRole('alert')).toContainText('Upload mislukt: dit is geen XML-bestand.')
    expect(uploadRequests).toBe(0)
  })
})
