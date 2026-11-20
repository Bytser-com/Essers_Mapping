// E2E tests for the mapping packages overview on Version Control, in a real browser.
// User story 158: "Als analist wil ik een overzicht van alle klanten en hun mapping packages,
// zodat ik snel naar het juiste package kan gaan."
//
// No backend is needed: page.route answers /api/version-control/packages the way the
// Version_Control backend does. What only the backend decides (newest version per type,
// alphabetical order, skipping broken packages) is tested with JUnit in
// Version_Control/src/test/.../SftpPackageStorageServiceTest.java.
// Tests linked to a Test issue in Jira (Xray) have its key, so the results can be imported.

import { expect, test, type Page } from '@playwright/test'

// Links a test to its Test issue in Xray
const xrayTest = (key: string) => ({ annotation: { type: 'test_key', description: key } })

// Dates are shown in the browser's timezone: use the one of the analisten.
test.use({ timezoneId: 'Europe/Brussels', locale: 'nl-BE' })

const PACKAGES_API = '**/api/version-control/packages*'

type MappingPackage = {
  company: string
  latestVersion: string
  createdAt: string | null
  createdBy: string | null
  customerName: string | null
  packageType: string | null
}

function mappingPackage(customerName: string, overrides: Partial<MappingPackage> = {}): MappingPackage {
  return {
    company: customerName.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    latestVersion: 'v1',
    createdAt: '2026-10-22T14:05:00+02:00',
    createdBy: 'analist_a',
    customerName,
    packageType: 'inbound',
    ...overrides,
  }
}

// Answers the packages API with the given responses, one per request; the last one keeps
// repeating. A number is answered as an HTTP error with that status.
async function mockPackages(page: Page, ...responses: Array<MappingPackage[] | number>): Promise<() => number> {
  let calls = 0
  await page.route(PACKAGES_API, (route) => {
    const response = responses[Math.min(calls, responses.length - 1)]
    calls += 1
    if (typeof response === 'number') {
      return route.fulfill({
        status: response,
        json: { title: 'SFTP Storage Error', detail: 'Unable to read packages from SFTP storage' },
      })
    }
    return route.fulfill({ json: response })
  })
  return () => calls
}

function rowsOf(page: Page, customer: string) {
  return page.getByRole('row').filter({ has: page.getByRole('cell', { name: customer, exact: true }) })
}

test.describe('E2E - Mapping packages overview on Version Control', () => {
  test('the overview shows the title, the search field and the columns', async ({ page }) => {
    await mockPackages(page, [mappingPackage('Klant A')])

    await page.goto('/version-control')

    await expect(page.getByRole('heading', { name: 'Version Control' })).toBeVisible()
    await expect(page.getByText('Alle klanten en hun mapping packages.')).toBeVisible()
    await expect(page.getByRole('searchbox', { name: 'Zoek een klant op naam' })).toBeVisible()
    await expect(page.getByRole('columnheader')).toHaveText([
      'KLANT',
      'TYPE',
      'ACTIEVE VERSIE',
      'LAATSTE WIJZIGING',
      'ACTIE',
    ])
  })

  test('each row shows customer, type, active version, date and time of the change and author', async ({ page }) => {
    await mockPackages(page, [
      mappingPackage('Klant A', { packageType: 'inbound', latestVersion: 'v2', createdAt: '2026-10-22T14:05:00+02:00', createdBy: 'analist_a' }),
      mappingPackage('Klant B', { packageType: 'outbound', createdAt: '2026-01-05T08:07:00+01:00', createdBy: 'analist_b' }),
      mappingPackage('Klant C', { latestVersion: 'v10', createdAt: '2026-10-25T09:00:00Z' }), // day of the change to winter time
    ])

    await page.goto('/version-control')

    const cells = rowsOf(page, 'Klant A').getByRole('cell')
    await expect(cells.nth(0)).toHaveText('Klant A')
    await expect(cells.nth(1)).toHaveText('inbound')
    await expect(cells.nth(2)).toHaveText('v2')
    await expect(cells.nth(3)).toContainText('22/10/2026 14:05')
    await expect(cells.nth(3)).toContainText('door analist_a')
    await expect(cells.nth(4).getByRole('button', { name: 'Bekijken' })).toBeVisible()

    const klantB = rowsOf(page, 'Klant B').getByRole('cell')
    await expect(klantB.nth(1)).toHaveText('outbound')
    await expect(klantB.nth(3)).toContainText('05/01/2026 08:07')
    await expect(klantB.nth(3)).toContainText('door analist_b')

    const klantC = rowsOf(page, 'Klant C').getByRole('cell')
    await expect(klantC.nth(2)).toHaveText('v10')
    await expect(klantC.nth(3)).toContainText('25/10/2026 10:00')
  })

  test('TC-158-01 a customer with several package types is shown once per type with the latest version of that type', xrayTest('IT2627T06-201'), async ({ page }) => {
    // The backend sends the newest version per type, sorted on customer and then type
    await mockPackages(page, [
      mappingPackage('Brevalis', { packageType: 'outbound', latestVersion: 'v4' }),
      mappingPackage('Nouryon', { packageType: 'inbound', latestVersion: 'v2' }),
      mappingPackage('Nouryon', { packageType: 'outbound', latestVersion: 'v1' }),
    ])

    await page.goto('/version-control')

    await expect(page.getByRole('row')).toHaveCount(4) // header + 3 packages
    const nouryon = rowsOf(page, 'Nouryon')
    await expect(nouryon).toHaveCount(2)
    await expect(nouryon.nth(0).getByRole('cell').nth(1)).toHaveText('inbound')
    await expect(nouryon.nth(0).getByRole('cell').nth(2)).toHaveText('v2')
    await expect(nouryon.nth(1).getByRole('cell').nth(1)).toHaveText('outbound')
    await expect(nouryon.nth(1).getByRole('cell').nth(2)).toHaveText('v1')
  })

  test('TC-158-01 the active packages are shown alphabetically per customer', xrayTest('IT2627T06-201'), async ({ page }) => {
    await mockPackages(page, [
      mappingPackage('Brevalis', { packageType: 'outbound' }),
      mappingPackage('Nouryon', { packageType: 'inbound' }),
      mappingPackage('Nouryon', { packageType: 'outbound' }),
      mappingPackage('Zentrova', { packageType: 'inbound' }),
    ])

    await page.goto('/version-control')

    const firstCells = page.getByRole('row').locator('td:first-child')
    await expect(firstCells).toHaveText(['Brevalis', 'Nouryon', 'Nouryon', 'Zentrova'])
  })

  test('without customer name, type or date the company folder and "—" are shown', async ({ page }) => {
    await mockPackages(page, [
      mappingPackage('Quorvia', { company: 'quorvia', customerName: null, packageType: null, createdAt: null, createdBy: null }),
    ])

    await page.goto('/version-control')

    const cells = rowsOf(page, 'quorvia').getByRole('cell')
    await expect(cells.nth(1)).toHaveText('—')
    await expect(cells.nth(3)).toHaveText('—')
  })

  test('the Version Control link in the sidebar opens the overview without reloading the page', async ({ page }) => {
    await mockPackages(page, [mappingPackage('Klant A')])
    // Home loads the proposals: an empty list keeps that page quiet
    await page.route('**/api/version-control/proposals*', (route) => route.fulfill({ json: [] }))
    let pageLoads = 0
    page.on('load', () => (pageLoads += 1))

    await page.goto('/')
    await page.getByRole('navigation').getByRole('link', { name: 'Version Control' }).click()

    await expect(page).toHaveURL(/\/version-control$/)
    await expect(rowsOf(page, 'Klant A')).toBeVisible()
    expect(pageLoads).toBe(1)
  })

  test('the packages are loaded once and the list does not keep refreshing', async ({ page }) => {
    const calls = await mockPackages(page, [mappingPackage('Klant A')])

    await page.goto('/version-control')
    await expect(rowsOf(page, 'Klant A')).toBeVisible()

    await page.waitForTimeout(3_000)
    expect(calls()).toBe(1)
  })

  test('without mapping packages the empty message is shown', async ({ page }) => {
    await mockPackages(page, [])

    await page.goto('/version-control')

    await expect(page.getByText('Er zijn nog geen mapping packages.')).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
  })

  test('loading message, error with "Opnieuw proberen" and retry', async ({ page }) => {
    // First answer is slow, so the loading message can be seen; then 502 (SFTP unreachable)
    let calls = 0
    let releaseFirst: () => void = () => {}
    const firstAnswered = new Promise<void>((resolve) => (releaseFirst = resolve))
    await page.route(PACKAGES_API, async (route) => {
      calls += 1
      if (calls === 1) {
        await firstAnswered
        return route.fulfill({ status: 502, json: { title: 'SFTP Storage Error' } })
      }
      return route.fulfill({ json: [mappingPackage('Klant A')] })
    })

    await page.goto('/version-control')
    await expect(page.getByText('Mapping packages laden…')).toBeVisible()
    releaseFirst()

    const alert = page.getByRole('alert')
    await expect(alert).toContainText('De mapping packages konden niet geladen worden.')
    await expect(page.getByRole('table')).toHaveCount(0)

    await alert.getByRole('button', { name: 'Opnieuw proberen' }).click()

    await expect(rowsOf(page, 'Klant A')).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('the error stays visible when retrying fails again', async ({ page }) => {
    const calls = await mockPackages(page, 502)

    await page.goto('/version-control')
    const alert = page.getByRole('alert')
    await expect(alert).toContainText('De mapping packages konden niet geladen worden.')

    await alert.getByRole('button', { name: 'Opnieuw proberen' }).click()

    await expect.poll(calls).toBe(2)
    await expect(page.getByRole('alert')).toContainText('De mapping packages konden niet geladen worden.')
  })
})
