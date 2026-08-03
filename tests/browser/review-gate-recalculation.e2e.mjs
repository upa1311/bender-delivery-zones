import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";

const reviewUrl = "review/";

async function waitUntilReady(page) {
  await page.goto(reviewUrl, { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-review-ready", "true", {
    timeout: 60_000,
  });
}

async function snapshot(page) {
  return page.evaluate(() => {
    const selected = document.querySelector("#selected-address");
    return {
      routeIndex: document.querySelector("#gate-slider")?.value,
      counts: document.querySelector("#catalog-recalc")?.textContent?.replace(/\s+/g, " ").trim(),
      zones: document.querySelector("#zone-legend")?.textContent?.replace(/\s+/g, " ").trim(),
      price: selected?.getAttribute("data-selected-price"),
      zone: selected?.getAttribute("data-selected-zone"),
      color: selected?.querySelector("[data-selected-color]")?.getAttribute("data-selected-color"),
      selected: selected?.textContent?.replace(/\s+/g, " ").trim(),
    };
  });
}

async function moveGate(page, routeIndex) {
  const before = await snapshot(page);
  await page.locator("#gate-slider").fill(String(routeIndex));
  await expect.poll(async () => {
    const current = await snapshot(page);
    return {
      routeIndex: current.routeIndex,
      countsChanged: current.counts !== before.counts,
      zonesChanged: current.zones !== before.zones,
      selectedChanged: current.selected !== before.selected,
      priceChanged: current.price !== before.price,
      zoneChanged: current.zone !== before.zone,
      colorChanged: current.color !== before.color,
    };
  }, {
    message: `full recalculation should settle at route index ${routeIndex}`,
    timeout: 60_000,
  }).toEqual({
    routeIndex: String(routeIndex), countsChanged: true, zonesChanged: true,
    selectedChanged: true, priceChanged: true, zoneChanged: true, colorChanged: true,
  });
  return snapshot(page);
}

test.beforeEach(async ({ page }) => {
  await waitUntilReady(page);
  await page.evaluate(() => localStorage.removeItem("bdz_tariff_gate_v2"));
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-review-ready", "true", {
    timeout: 60_000,
  });
});

test("gate move recalculates the full catalog and approval survives reload", async ({ page }) => {
  const initial = await snapshot(page);
  expect(initial.routeIndex).toBe("51");
  expect(initial.counts).toBe("Пересчитано 9 215 маршрутов · gate пересекают 3446 · не пересекают 5769");
  expect(initial.zones).toContain("Взвешенный Jenks по 9 215 маршрутам");
  expect(initial.zones).toContain("Границы ₽: 18.1, 24.9, 31.9, 43.8");
  for (const count of ["2992 адр.", "2597 адр.", "2271 адр.", "1355 адр."]) {
    expect(initial.zones).toContain(count);
  }
  expect(initial.price).toBe("25.63");
  expect(initial.zone).toBe("3");
  expect(initial.color).toBe("#f07f14");
  await expect(page.locator("#bcoords")).toContainText("PROVISIONAL");

  const moved = await moveGate(page, 83);
  expect(moved.counts).not.toBe(initial.counts);
  expect(moved.zones).not.toBe(initial.zones);
  expect(moved.selected).not.toBe(initial.selected);
  expect(moved.price).not.toBe(initial.price);
  expect(moved.zone).not.toBe(initial.zone);
  expect(moved.color).not.toBe(initial.color);

  await page.getByRole("button", { name: "Утвердить границу" }).click();
  await expect(page.locator("#bcoords")).toContainText("Утверждено:");
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-review-ready", "true", {
    timeout: 60_000,
  });
  await expect.poll(() => snapshot(page), { timeout: 60_000 }).toEqual(moved);
  await expect(page.locator("#bcoords")).toContainText("Утверждено:");

  await page.getByRole("button", { name: "Сбросить" }).click();
  await expect.poll(() => snapshot(page), { timeout: 60_000 }).toEqual(initial);
  await expect(page.locator("#bcoords")).toContainText("PROVISIONAL");
});

test("review panel, map and legend do not overlap", async ({ page }) => {
  const legend = page.locator("#zone-legend");
  await legend.scrollIntoViewIfNeeded();
  const layout = await page.evaluate(() => {
    const rectangle = (selector) => {
      const { left, top, right, bottom, width, height } = document.querySelector(selector).getBoundingClientRect();
      return { left, top, right, bottom, width, height };
    };
    return {
      panel: rectangle("#rpanel"),
      map: rectangle("#rmap"),
      legend: rectangle("#zone-legend"),
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      panelOverflowY: getComputedStyle(document.querySelector("#rpanel")).overflowY,
    };
  });
  const overlaps = (a, b) => a.left < b.right - 1 && a.right > b.left + 1
    && a.top < b.bottom - 1 && a.bottom > b.top + 1;
  const visibleLegend = {
    left: Math.max(layout.legend.left, layout.panel.left),
    top: Math.max(layout.legend.top, layout.panel.top),
    right: Math.min(layout.legend.right, layout.panel.right),
    bottom: Math.min(layout.legend.bottom, layout.panel.bottom),
  };

  expect(layout.horizontalOverflow).toBe(false);
  expect(["auto", "scroll"]).toContain(layout.panelOverflowY);
  expect(layout.panel.width).toBeGreaterThan(0);
  expect(layout.map.width).toBeGreaterThan(0);
  expect(overlaps(layout.panel, layout.map)).toBe(false);
  expect(visibleLegend.right - visibleLegend.left).toBeGreaterThan(0);
  expect(visibleLegend.bottom - visibleLegend.top).toBeGreaterThan(0);
  expect(overlaps(visibleLegend, layout.map)).toBe(false);
  expect(layout.legend.left).toBeGreaterThanOrEqual(layout.panel.left - 1);
  expect(layout.legend.right).toBeLessThanOrEqual(layout.panel.right + 1);
});

test("downloaded checkpoint uses the public lat/lon schema", async ({ page }) => {
  await moveGate(page, 83);
  await page.getByRole("button", { name: "Утвердить границу" }).click();
  await expect(page.locator("#bcoords")).toContainText("Утверждено:");

  const coordinates = await page.locator("#bcoords").evaluate((element) => ({
    lat: Number(element.getAttribute("data-lat")),
    lon: Number(element.getAttribute("data-lon")),
  }));
  expect(coordinates).toEqual({ lat: 46.82871, lon: 29.52008 });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать JSON" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("tariff-checkpoint.json");
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  const exported = JSON.parse(await readFile(downloadPath, "utf8"));

  expect(Object.keys(exported)).toEqual(["checkpoint"]);
  expect(Object.keys(exported.checkpoint).sort()).toEqual(["approved_at", "lat", "lon", "status"]);
  expect(exported.checkpoint.lat).toBe(coordinates.lat);
  expect(exported.checkpoint.lon).toBe(coordinates.lon);
  expect(exported.checkpoint.status).toBe("owner_approved");
  expect(new Date(exported.checkpoint.approved_at).toISOString()).toBe(exported.checkpoint.approved_at);
  for (const obsolete of ["status", "route_index", "center_lonlat", "geometry"]) {
    expect(exported).not.toHaveProperty(obsolete);
  }
});
