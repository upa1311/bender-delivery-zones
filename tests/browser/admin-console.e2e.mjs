import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";

const adminUrl = "admin/";

async function mockOSRM(page, failure = false) {
  await page.route("https://router.project-osrm.org/route/v1/driving/**", async (route) => {
    if (failure) {
      await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
      return;
    }
    const match = route.request().url().match(/driving\/([^?]+)/);
    const [start, end] = decodeURIComponent(match[1]).split(";").map(
      (coordinate) => coordinate.split(",").map(Number),
    );
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: "Ok",
        routes: [{
          distance: 6000,
          duration: 720,
          geometry: {
            type: "LineString",
            coordinates: [
              start,
              [29.487726, 46.829816],
              [29.487794, 46.830313],
              end,
            ],
          },
        }],
      }),
    });
  });
}

async function waitUntilReady(page) {
  await page.goto(adminUrl, { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-admin-ready", "true", {
    timeout: 60_000,
  });
}

async function selectAddress(page, target, values, address, uid) {
  await page.locator(`#target-${target}`).check();
  await page.locator("#street-filter").fill(values.street);
  await page.locator("#house-filter").fill(values.house);
  await page.locator("#district-filter").selectOption({ label: values.district });
  await page.locator("#zone-filter").selectOption(values.zone);
  const result = page.locator(`.address-result[data-uid="${uid}"]`);
  await expect(result).toHaveCount(1, { timeout: 30_000 });
  await expect(result).toContainText(address);
  await result.click();
}

async function chooseRouteEndpoints(page) {
  await selectAddress(page, "a", {
    street: "улица Ленина", house: "40", district: "Бендеры", zone: "1",
  }, "Бендеры, улица Ленина, 40", "n6539017900");
  await selectAddress(page, "b", {
    street: "улица Горького", house: "1", district: "Парканы", zone: "3",
  }, "Парканы, улица Горького, 1", "n2323152058");
}

test("registry filters, exact A/B route, symmetric swap and CSV work", async ({ page }) => {
  await mockOSRM(page);
  await waitUntilReady(page);
  await chooseRouteEndpoints(page);
  await expect(page.locator("#selected-a")).toContainText("Бендеры, улица Ленина, 40");
  await expect(page.locator("#selected-b")).toContainText("Парканы, улица Горького, 1");

  await page.getByRole("button", { name: "Построить A → B" }).click();
  await expect(page.locator("#calculation")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#route-km")).toHaveText("6.000 км");
  await expect(page.locator("#route-minutes")).toHaveText("12.0 мин");
  await expect(page.locator("#route-zones")).toHaveText("1 / 3");
  await expect(page.locator("#route-crosses")).toHaveText("пересекает");
  await expect(page.locator("#route-external")).not.toHaveText("0.000 км");
  const totalBefore = await page.locator("#calculation").getAttribute("data-total");
  expect(Number(totalBefore)).toBeGreaterThan(26);

  await page.getByRole("button", { name: "Поменять A ↔ B" }).click();
  await expect(page.locator("#selected-a")).toContainText("Парканы, улица Горького, 1");
  await expect(page.locator("#selected-b")).toContainText("Бендеры, улица Ленина, 40");
  await expect(page.locator("#route-zones")).toHaveText("3 / 1");
  expect(await page.locator("#calculation").getAttribute("data-total")).toBe(totalBefore);

  const downloadPromise = page.waitForEvent("download");
  await page.locator("#download-csv").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("reference-tariff-v3.csv");
  const path = await download.path();
  expect(path).not.toBeNull();
  expect((await readFile(path, "utf8")).split("\n")[0]).toContain("crosses_checkpoint");
});

test("OSRM failure is honest and never produces a fabricated calculation", async ({ page }) => {
  await mockOSRM(page, true);
  await waitUntilReady(page);
  await chooseRouteEndpoints(page);
  await page.getByRole("button", { name: "Построить A → B" }).click();
  await expect(page.locator("#route-error")).toContainText("OSRM недоступен: HTTP 503");
  await expect(page.locator("#route-error")).toContainText("Расчёт не выполнен");
  await expect(page.locator("#calculation")).toBeHidden();
});

test("canonical model, 9,216 registry rows and responsive layout are visible", async ({ page }) => {
  await waitUntilReady(page);
  await expect(page.locator("#model-status")).toContainText("9 216 записей");
  await expect(page.locator("#model-status")).toContainText("owner_approved");
  await expect(page.locator("#model-status")).toContainText("46.829970, 29.487740");
  await expect(page.locator("#model-status")).toContainText("route index 33");
  await expect(page.locator("#model-status")).toContainText("18.3 / 25.7 / 33 / 52.9");
  await expect(page.locator("#model-status")).toContainText("gate 4315 / 4900");
  expect(await page.evaluate(() => window.__adminTest.snapshot().catalogCount)).toBe(9216);

  await page.locator("#street-filter").fill("Горького");
  await page.locator("#district-filter").selectOption({ label: "Парканы" });
  await page.locator("#zone-filter").selectOption("3");
  await expect.poll(async () => page.locator(".address-result").count(), { timeout: 30_000 })
    .toBeGreaterThan(0);

  const layout = await page.evaluate(() => {
    const rectangle = (selector) => {
      const { left, top, right, bottom, width, height } = document.querySelector(selector)
        .getBoundingClientRect();
      return { left, top, right, bottom, width, height };
    };
    return {
      panel: rectangle("#admin-panel"), map: rectangle("#admin-map"),
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
  const overlaps = layout.panel.left < layout.map.right - 1
    && layout.panel.right > layout.map.left + 1
    && layout.panel.top < layout.map.bottom - 1
    && layout.panel.bottom > layout.map.top + 1;
  expect(layout.overflow).toBe(false);
  expect(layout.panel.width).toBeGreaterThan(0);
  expect(layout.map.width).toBeGreaterThan(0);
  expect(layout.map.height).toBeGreaterThan(300);
  expect(overlaps).toBe(false);
});
