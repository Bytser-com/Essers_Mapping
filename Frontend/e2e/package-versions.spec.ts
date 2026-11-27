// E2E tests for the version history of a mapping package, in a real browser.
// User story 161: "Als analist wil ik alle versies van het mapping package van een klant zien,
// zodat ik weet wanneer er iets veranderd is en door wie."
//
// No backend is needed: page.route answers /api/version-control/packages/versions the way the
// Version_Control backend does. What only the backend decides (which versions exist, which one is
// active, the order) is tested with JUnit in Version_Control/src/test/.../SftpPackageStorageServiceTest.java.

import { expect, test, type Page } from '@playwright/test'

// Dates are shown in the browser's timezone: use the one of the analisten.
test.use({ timezoneId: 'Europe/Brussels', locale: 'nl-BE' })

const VERSIONS_API = '**/api/version-control/packages/versions*'
const PACKAGES_API = '**/api/version-control/packages*'
const VERSIONS_PAGE = '/package-versions/brevalis/inbound'

type PackageVersion = {
  version: string
  isActive: boolean
  createdAt: string | null
  createdBy: string | null
  description: string | null
}

function packageVersion(version: string, overrides: Partial<PackageVersion> = {}): PackageVersion {
  return {
    version,
    isActive: false,
    createdAt: '2026-10-22T14:05:00+02:00',
    createdBy: 'analist_a',
    description: null,
    ...overrides,
  }
}

// Answers the versions API with the given responses, one per request; the last one keeps
// repeating. A number is answered as an HTTP error with that status.
async function mockVersions(page: Page, ...responses: Array<PackageVersion[] | number>): Promise<() => number> {
  let calls = 0
  await page.route(VERSIONS_API, (route) => {
    const response = responses[Math.min(calls, responses.length - 1)]
    calls += 1
    if (typeof response === 'number') {
      return route.fulfill({
        status: response,
        json: { title: 'SFTP Storage Error', detail: 'Unable to read versions from SFTP storage' },
      })
    }
    return route.fulfill({ json: response })
  })
  return () => calls
}

function rowOf(page: Page, version: string) {
  return page.getByRole('row').filter({ has: page.getByText(version, { exact: true }) })
}

test.describe('E2E - Version history of a mapping package', () => {
  test('the page shows the breadcrumb, the company, the active version, the type and the columns', async ({ page }) => {
    await mockVersions(page, [
      packageVersion('v3'),
      packageVersion('v2', { isActive: true }),
      packageVersion('v1'),
    ])

    await page.goto(VERSIONS_PAGE)

    await expect(page.getByRole('main').getByRole('link', { name: 'Version Control' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'brevalis' })).toBeVisible()
    await expect(page.getByText('Actief: v2')).toBeVisible()
    await expect(page.getByText('Mapping package · inbound · 3 versies')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Versiegeschiedenis' })).toBeVisible()
    await expect(page.getByRole('columnheader')).toHaveText([
      'VERSIE',
      'OMSCHRIJVING',
      'GOEDGEKEURD OP',
      'DOOR',
      'ACTIE',
    ])
  })

  test('each row shows the version, date and time of approval and author', async ({ page }) => {
    await mockVersions(page, [
      packageVersion('v3', { createdAt: '2026-11-12T10:00:00+01:00', createdBy: 'analist_a' }),
      packageVersion('v2', { isActive: true, createdAt: '2026-10-25T09:00:00Z', createdBy: 'analist_b' }), // day of the change to winter time
      packageVersion('v1', { createdAt: '2026-01-05T08:07:00+01:00' }),
    ])

    await page.goto(VERSIONS_PAGE)

    const cells = rowOf(page, 'v3').getByRole('cell')
    await expect(cells.nth(0)).toHaveText('v3')
    await expect(cells.nth(2)).toHaveText('12/11/2026 10:00')
    await expect(cells.nth(3)).toHaveText('analist_a')
    await expect(cells.nth(4).getByRole('button', { name: 'Openen' })).toBeVisible()

    const v2 = rowOf(page, 'v2').getByRole('cell')
    await expect(v2.nth(2)).toHaveText('25/10/2026 10:00')
    await expect(v2.nth(3)).toHaveText('analist_b')

    await expect(rowOf(page, 'v1').getByRole('cell').nth(2)).toHaveText('05/01/2026 08:07')
  })

  test('the versions are shown in the order of the backend and only the active one has the "Actief" label', async ({ page }) => {
    await mockVersions(page, [
      packageVersion('v3'),
      packageVersion('v2', { isActive: true }),
      packageVersion('v1'),
    ])

    await page.goto(VERSIONS_PAGE)

    await expect(page.getByRole('row')).toHaveCount(4) // header + 3 versions
    await expect(page.getByRole('button', { name: 'Openen' })).toHaveCount(3)
    await expect(rowOf(page, 'v2').getByText('Actief', { exact: true })).toBeVisible()
    await expect(rowOf(page, 'v3').getByText('Actief', { exact: true })).toHaveCount(0)
    await expect(rowOf(page, 'v1').getByText('Actief', { exact: true })).toHaveCount(0)
  })

  test('without date or author "—" is shown', async ({ page }) => {
    await mockVersions(page, [packageVersion('v1', { createdAt: null, createdBy: null })])

    await page.goto(VERSIONS_PAGE)

    const cells = rowOf(page, 'v1').getByRole('cell')
    await expect(cells.nth(2)).toHaveText('—')
    await expect(cells.nth(3)).toHaveText('—')
  })

  test('"Bekijken" on the overview opens the version history of that package', async ({ page }) => {
    await mockVersions(page, [packageVersion('v1', { isActive: true })])
    await page.route(PACKAGES_API, (route) =>
      route.fulfill({
        json: [
          {
            company: 'brevalis',
            latestVersion: 'v1',
            createdAt: '2026-10-22T14:05:00+02:00',
            createdBy: 'analist_a',
            customerName: 'Brevalis',
            packageType: 'inbound',
          },
        ],
      }),
    )

    await page.goto('/version-control')
    const versionsRequest = page.waitForRequest(VERSIONS_API)
    await page.getByRole('button', { name: 'Bekijken' }).click()

    await expect(page).toHaveURL(/\/package-versions\/brevalis\/inbound$/)
    const params = new URL((await versionsRequest).url()).searchParams
    expect(params.get('company')).toBe('brevalis')
    expect(params.get('packageType')).toBe('inbound')
    await expect(rowOf(page, 'v1')).toBeVisible()
  })

  test('the Version Control link in the breadcrumb goes back to the overview without reloading the page', async ({ page }) => {
    await mockVersions(page, [packageVersion('v1')])
    await page.route(PACKAGES_API, (route) => route.fulfill({ json: [] }))
    let pageLoads = 0
    page.on('load', () => (pageLoads += 1))

    await page.goto(VERSIONS_PAGE)
    await page.getByRole('main').getByRole('link', { name: 'Version Control' }).click()

    await expect(page).toHaveURL(/\/version-control$/)
    await expect(page.getByRole('heading', { name: 'Version Control' })).toBeVisible()
    expect(pageLoads).toBe(1)
  })

  test('the versions are loaded once and the list does not keep refreshing', async ({ page }) => {
    const calls = await mockVersions(page, [packageVersion('v1')])

    await page.goto(VERSIONS_PAGE)
    await expect(rowOf(page, 'v1')).toBeVisible()

    await page.waitForTimeout(3_000)
    expect(calls()).toBe(1)
  })

  test('without versions the empty message is shown', async ({ page }) => {
    await mockVersions(page, [])

    await page.goto(VERSIONS_PAGE)

    await expect(page.getByText('Er zijn nog geen versies voor dit mapping package.')).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
  })

  test('loading message, error with "Opnieuw proberen" and retry', async ({ page }) => {
    // First answer is slow, so the loading message can be seen; then 502 (SFTP unreachable)
    let calls = 0
    let releaseFirst: () => void = () => {}
    const firstAnswered = new Promise<void>((resolve) => (releaseFirst = resolve))
    await page.route(VERSIONS_API, async (route) => {
      calls += 1
      if (calls === 1) {
        await firstAnswered
        return route.fulfill({ status: 502, json: { title: 'SFTP Storage Error' } })
      }
      return route.fulfill({ json: [packageVersion('v1')] })
    })

    await page.goto(VERSIONS_PAGE)
    await expect(page.getByText('Versies laden…')).toBeVisible()
    releaseFirst()

    const alert = page.getByRole('alert')
    await expect(alert).toContainText('De versies konden niet geladen worden.')
    await expect(page.getByRole('table')).toHaveCount(0)

    await alert.getByRole('button', { name: 'Opnieuw proberen' }).click()

    await expect(rowOf(page, 'v1')).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('the error stays visible when retrying fails again', async ({ page }) => {
    const calls = await mockVersions(page, 502)

    await page.goto(VERSIONS_PAGE)
    const alert = page.getByRole('alert')
    await expect(alert).toContainText('De versies konden niet geladen worden.')

    await alert.getByRole('button', { name: 'Opnieuw proberen' }).click()

    await expect.poll(calls).toBe(2)
    await expect(page.getByRole('alert')).toContainText('De versies konden niet geladen worden.')
  })
})