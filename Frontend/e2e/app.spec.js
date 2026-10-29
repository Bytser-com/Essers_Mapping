import { expect, test } from '@playwright/test'

test.describe('End-to-End (E2E) - Essers Mapping Frontend & Nginx', () => {
  test('loads the root application, verifies title, and executes counter workflow', async ({ page }) => {
    const response = await page.goto('/')
    expect(response?.status()).toBe(200)

    await expect(page.getByRole('heading', { name: /get started/i })).toBeVisible()

    const counterButton = page.getByRole('button', { name: /count is 0/i })
    await expect(counterButton).toBeVisible()
    await counterButton.click()
    await expect(page.getByRole('button', { name: /count is 1/i })).toBeVisible()
  })

  test('supports SPA deep-link fallback routing without 404 errors', async ({ page }) => {
    const response = await page.goto('/mappings/deep-link-e2e-check')
    expect(response?.status()).toBe(200)
    await expect(page.locator('#root')).toBeAttached()
  })
})
