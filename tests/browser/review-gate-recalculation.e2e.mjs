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
  await page.evaluate(() => {
    localStorage.removeItem("bdz_tariff_gate_v2");
    localStorage.removeItem("bdz_tariff_gate_v3");
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-review-ready", "true", {
    timeout: 60_000,
  });
});

test("gate move recalculates the full catalog and approval survives reload", async ({ page }) => {
  const initial = await snapshot(page);
  expect(initial.routeIndex).toBe("33");
  expect(initial.counts).toBe("Пересчитано 9 215 маршрутов · gate пересекают 4315 · не пересекают 4900");
  expect(initial.zones).toContain("Взвешенный Jenks по 9 215 маршрутам");
  expect(initial.zones).toContain("Границы ₽: 18.3, 25.7, 33, 52.9");
  for (const count of ["2729 адр.", "2557 адр.", "2588 адр.", "1341 адр."]) {
    expect(initial.zones).toContain(count);
  }
  expect(initial.price).toBe("26.75");
  expect(initial.zone).toBe("3");
  expect(initial.color).toBe("#f07f14");
  await expect(page.locator("#bcoords")).toContainText("owner_approved");
  await expect(page.locator("#bcoords")).toContainText("46.829970, 29.487740");
  await expect(page.locator("#bcoords")).toContainText("route index 33");

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
  await expect(page.locator("#bcoords")).toContainText("owner_approved");
  await expect(page.locator("#bcoords")).toContainText("route index 33");
});

test("legacy and mismatched saved gates cannot override the canonical checkpoint", async ({ page }) => {
  await page.evaluate(() => {
    localStorage.setItem("bdz_tariff_gate_v2", JSON.stringify({
      status: "owner_approved", route_index: 83, approved_at: "2026-01-01T00:00:00.000Z",
    }));
    localStorage.setItem("bdz_tariff_gate_v3", JSON.stringify({
      status: "owner_approved", route_index: 83, approved_at: "2026-01-01T00:00:00.000Z",
      checkpoint_model_id: "obsolete-model",
    }));
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-review-ready", "true", {
    timeout: 60_000,
  });
  await expect.poll(async () => (await snapshot(page)).routeIndex, { timeout: 60_000 }).toBe("33");
  await expect(page.locator("#bcoords")).toContainText("owner_approved");
  expect(await page.evaluate(() => localStorage.getItem("bdz_tariff_gate_v2"))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem("bdz_tariff_gate_v3"))).toBeNull();
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
  await page.getByRole("button", { name: "Утвердить границу" }).click();
  await expect(page.locator("#bcoords")).toContainText("Утверждено:");

  const coordinates = await page.locator("#bcoords").evaluate((element) => ({
    lat: Number(element.getAttribute("data-lat")),
    lon: Number(element.getAttribute("data-lon")),
  }));
  expect(coordinates).toEqual({ lat: 46.82997, lon: 29.48774 });
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
  expect(exported.checkpoint.approved_at).toBe("2026-08-03T22:31:23.434Z");
  for (const obsolete of ["status", "route_index", "center_lonlat", "geometry"]) {
    expect(exported).not.toHaveProperty(obsolete);
  }
});
