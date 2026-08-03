/* Browser contract. Run with a Playwright test runner against REVIEW_URL.
 * The same scenario is executed with the repository's interactive browser
 * during release verification, so this file is also the durable regression spec.
 */
import { expect, test } from "@playwright/test";

const url = process.env.REVIEW_URL || "http://127.0.0.1:8765/review/";

async function snapshot(page) {
  return page.evaluate(() => ({
    counts: document.querySelector("#catalog-recalc")?.textContent,
    zones: document.querySelector("#zone-legend")?.textContent,
    selected: document.querySelector("#selected-address")?.textContent,
    color: document.querySelector("#selected-address [data-selected-color]")
      ?.getAttribute("data-selected-color"),
    slider: document.querySelector("#gate-slider")?.value,
  }));
}

test("moving gate recalculates all routes and approve survives reload", async ({ page }) => {
  await page.goto(url);
  await page.locator('html[data-review-ready="true"]').waitFor();
  const initial = await snapshot(page);
  expect(initial.counts).toContain("9 215");

  await page.getByLabel("Положение gate по контрольному маршруту").fill("83");
  const moved = await snapshot(page);
  expect(moved.counts).not.toBe(initial.counts);
  expect(moved.zones).not.toBe(initial.zones);
  expect(moved.selected).not.toBe(initial.selected);
  expect(moved.color).not.toBe(initial.color);

  await page.getByRole("button", { name: "Утвердить границу" }).click();
  await page.reload();
  await page.locator('html[data-review-ready="true"]').waitFor();
  expect(await snapshot(page)).toEqual(moved);

  await page.getByRole("button", { name: "Сбросить" }).click();
  expect(await snapshot(page)).toEqual(initial);
});
