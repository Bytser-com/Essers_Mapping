import { expect, test } from '@playwright/test'

test.describe('End-to-End (E2E) - Essers Mapping Frontend & Nginx', () => {
  test('loads the root application, verifies title, and renders Home page', async ({ page }) => {
    const response = await page.goto('/')
    expect(response?.status()).toBe(200)

    await expect(page.getByRole('heading', { name: /essers mapping/i })).toBeVisible()
    await expect(page.getByTestId('home-page')).toBeVisible()
  })

  test('supports SPA deep-link fallback routing without 404 errors', async ({ page }) => {
    const response = await page.goto('/mappings/deep-link-e2e-check')
    expect(response?.status()).toBe(200)
    await expect(page.locator('#root')).toBeAttached()
  })
})
