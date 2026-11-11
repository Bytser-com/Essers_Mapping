import { expect, test } from '@playwright/test'

// E2E tests for the sidebar.
// User story 59: a sidebar with all pages (TC-59-01 to TC-59-03)
// Each test has the key of its Test issue in Jira (Xray), so the results can be imported.

// Links a test to its Test issue in Xray
const xrayTest = (key) => ({ annotation: { type: 'test_key', description: key } })

test.describe('E2E - Sidebar', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('TC-59-01 all pages are shown in the sidebar', xrayTest('IT2627T06-120'), async ({ page }) => {
    const sidebar = page.getByRole('navigation')

    await expect(sidebar.getByRole('link', { name: 'Home' })).toBeVisible()
    await expect(sidebar.getByRole('link', { name: 'Version Control' })).toBeVisible()
  })

  test('TC-59-02 the links in the sidebar open the right page', xrayTest('IT2627T06-121'), async ({ page }) => {
    const sidebar = page.getByRole('navigation')

    await sidebar.getByRole('link', { name: 'Version Control' }).click()
    await expect(page).toHaveURL(/\/version-control$/)
    await expect(page.getByTestId('home-page')).toHaveCount(0)

    await sidebar.getByRole('link', { name: 'Home' }).click()
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByTestId('home-page')).toBeVisible()
  })

  test('TC-59-03 the active page is marked in the sidebar', xrayTest('IT2627T06-122'), async ({ page }) => {
    const sidebar = page.getByRole('navigation')
    const home = sidebar.getByRole('link', { name: 'Home' })
    const versionControl = sidebar.getByRole('link', { name: 'Version Control' })

    // NavLink sets aria-current="page" on the link of the active page
    await expect(home).toHaveAttribute('aria-current', 'page')
    await expect(versionControl).not.toHaveAttribute('aria-current', 'page')

    await versionControl.click()
    await expect(versionControl).toHaveAttribute('aria-current', 'page')
    await expect(home).not.toHaveAttribute('aria-current', 'page')
  })
})
