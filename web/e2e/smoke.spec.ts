import { expect, test, type Page } from '@playwright/test'

const PAGES = [
  { hash: '#/now', heading: /How clean is the grid/ },
  { hash: '#/plan', heading: /When should I run it/ },
  { hash: '#/trust', heading: /trust/i },
  { hash: '#/explore', heading: /Explore/ },
  { hash: '#/how', heading: /How it works/ },
]

/** Collect console errors and failed requests for the whole test. */
function watchErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console: ${m.text()}`)
  })
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('requestfailed', (r) => errors.push(`requestfailed: ${r.url()}`))
  page.on('response', (r) => {
    if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`)
  })
  return errors
}

for (const p of PAGES) {
  test(`${p.hash} loads without console errors`, async ({ page }) => {
    const errors = watchErrors(page)
    await page.goto(`./${p.hash}`)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(p.heading)
    await expect(page.getByText('Loading data…')).toHaveCount(0)
    await page.waitForLoadState('networkidle')
    expect(errors).toEqual([])
  })
}

test('Now page defaults to North West England and the map selects a region', async ({ page }) => {
  await page.goto('./#/now')
  await expect(page.getByLabel('Your region')).toHaveValue('3')
  await expect(page.getByRole('heading', { level: 2 }).first()).toContainText('North West England')
  await page.getByRole('button', { name: /^London:/ }).click()
  await expect(page.getByLabel('Your region')).toHaveValue('13')
  await expect(page.getByRole('heading', { level: 2 }).first()).toContainText('London')
  // The choice is remembered when moving to another page.
  await page.getByRole('link', { name: 'Plan' }).click()
  await expect(page.getByLabel('Your region')).toHaveValue('13')
})

test('Plan page shows a best window for each preset task', async ({ page }) => {
  await page.goto('./#/plan')
  for (const name of [/EV charge/, /Washing machine/, /Dishwasher/]) {
    await page.getByRole('button', { name }).click()
    await expect(page.locator('.result .when')).toBeVisible()
  }
  await page.getByRole('button', { name: 'Custom' }).click()
  await page.getByLabel('Duration (hours)').fill('1')
  await expect(page.locator('.result .when')).toBeVisible()
})

test('no horizontal scroll at the current viewport', async ({ page }) => {
  for (const p of PAGES) {
    await page.goto(`./${p.hash}`)
    await expect(page.getByText('Loading data…')).toHaveCount(0)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow, `${p.hash} overflows by ${overflow}px`).toBeLessThanOrEqual(0)
  }
})
