/* Shared route-geometry tariff functions for /review/ and /admin/. */
(function installTariffModel(root) {
  "use strict";

  const basePrice = (km) => (km <= 3 ? 14 : 14 + (km - 3) * 4);
  const externalSurcharge = (km) => (km <= 0 ? 0 : Math.max(5, km * 2));

  function haversineKm(a, b) {
    const rad = Math.PI / 180;
    const radius = 6371.0088;
    const dLat = (b[1] - a[1]) * rad;
    const dLon = (b[0] - a[0]) * rad;
    const value = Math.sin(dLat / 2) ** 2
      + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * radius * Math.asin(Math.sqrt(value));
  }

  function cross(a, b) { return a[0] * b[1] - a[1] * b[0]; }

  function segmentIntersectionFraction(routeA, routeB, gateA, gateB) {
    const route = [routeB[0] - routeA[0], routeB[1] - routeA[1]];
    const gate = [gateB[0] - gateA[0], gateB[1] - gateA[1]];
    const offset = [gateA[0] - routeA[0], gateA[1] - routeA[1]];
    const denominator = cross(route, gate);
    const epsilon = 1e-12;
    if (Math.abs(denominator) <= epsilon) return null;
    const routeFraction = cross(offset, gate) / denominator;
    const gateFraction = cross(offset, route) / denominator;
    if (routeFraction < -epsilon || routeFraction > 1 + epsilon
      || gateFraction < -epsilon || gateFraction > 1 + epsilon) return null;
    return Math.max(0, Math.min(1, routeFraction));
  }

  function routeGeometry(points, routeKm, gate) {
    const lengths = [];
    let geometryKm = 0;
    for (let index = 0; index < points.length - 1; index += 1) {
      const length = haversineKm(points[index], points[index + 1]);
      lengths.push(length);
      geometryKm += length;
    }
    if (!Number.isFinite(routeKm) || routeKm < 0 || geometryKm <= 0) {
      return { intersections: [], geometryKm, lengths };
    }
    const intersections = [];
    let traversed = 0;
    for (let index = 0; index < points.length - 1; index += 1) {
      const fraction = segmentIntersectionFraction(
        points[index], points[index + 1], gate[0], gate[1],
      );
      if (fraction != null) {
        const chainage = Math.max(
          0,
          Math.min(routeKm, (traversed + lengths[index] * fraction) * routeKm / geometryKm),
        );
        if (!intersections.length
          || Math.abs(chainage - intersections[intersections.length - 1]) > 1e-7) {
          intersections.push(chainage);
        }
      }
      traversed += lengths[index];
    }
    return { intersections, geometryKm, lengths };
  }

  function routeGateMetrics(points, routeKm, gate) {
    const { intersections } = routeGeometry(points, routeKm, gate);
    if (!intersections.length) return { crosses: false, chainage: null, externalKm: 0 };
    const chainage = intersections[0];
    return { crosses: true, chainage, externalKm: Math.max(0, routeKm - chainage) };
  }

  function pointSide(point, gate) {
    return Math.sign(cross(
      [gate[1][0] - gate[0][0], gate[1][1] - gate[0][1]],
      [point[0] - gate[0][0], point[1] - gate[0][1]],
    ));
  }

  function symmetricRouteGateMetrics(points, routeKm, gate, internalReference) {
    const { intersections } = routeGeometry(points, routeKm, gate);
    if (!intersections.length) {
      return { crosses: false, chainage: null, externalKm: 0, intersections: [] };
    }
    const internalSide = pointSide(internalReference, gate);
    if (!internalSide) throw new Error("internal reference cannot lie on the gate");
    const startSide = points.map((point) => pointSide(point, gate)).find(Boolean) || internalSide;
    let outside = startSide !== internalSide;
    let externalKm = 0;
    let previous = 0;
    for (const intersection of intersections) {
      if (outside) externalKm += intersection - previous;
      outside = !outside;
      previous = intersection;
    }
    if (outside) externalKm += routeKm - previous;
    return {
      crosses: true,
      chainage: intersections[0],
      externalKm: Math.max(0, Math.min(routeKm, externalKm)),
      intersections,
    };
  }

  function gateAt(route, index, halfLengthM = 90) {
    const center = route[index];
    const before = route[Math.max(0, index - 1)];
    const after = route[Math.min(route.length - 1, index + 1)];
    const latitude = center[1] * Math.PI / 180;
    const dx = (after[0] - before[0]) * 111320 * Math.cos(latitude);
    const dy = (after[1] - before[1]) * 110540;
    const length = Math.hypot(dx, dy) || 1;
    const perpendicularX = -dy / length;
    const perpendicularY = dx / length;
    return [-1, 1].map((side) => [
      center[0] + side * halfLengthM * perpendicularX / (111320 * Math.cos(latitude)),
      center[1] + side * halfLengthM * perpendicularY / 110540,
    ]);
  }

  function weightedJenks(values, classCount) {
    const frequency = new Map();
    values.forEach((value) => frequency.set(value, (frequency.get(value) || 0) + 1));
    const levels = [...frequency.entries()].sort((a, b) => a[0] - b[0]);
    const n = levels.length;
    const counts = [0];
    const sums = [0];
    const squares = [0];
    levels.forEach(([value, count]) => {
      counts.push(counts.at(-1) + count);
      sums.push(sums.at(-1) + value * count);
      squares.push(squares.at(-1) + value * value * count);
    });
    const variance = (first, last) => {
      const weight = counts[last] - counts[first - 1];
      const total = sums[last] - sums[first - 1];
      return squares[last] - squares[first - 1] - total * total / weight;
    };
    const scores = Array.from(
      { length: classCount + 1 }, () => Array(n + 1).fill(Infinity),
    );
    const starts = Array.from({ length: classCount + 1 }, () => Array(n + 1).fill(0));
    scores[0][0] = 0;
    for (let group = 1; group <= classCount; group += 1) {
      for (let last = group; last <= n; last += 1) {
        for (let first = group; first <= last; first += 1) {
          const score = scores[group - 1][first - 1] + variance(first, last);
          if (score < scores[group][last] - 1e-12) {
            scores[group][last] = score;
            starts[group][last] = first;
          }
        }
      }
    }
    const breaks = [];
    let last = n;
    for (let group = classCount; group >= 1; group -= 1) {
      const first = starts[group][last];
      breaks.push(levels[last - 1][0]);
      last = first - 1;
    }
    return breaks.reverse();
  }

  function zoneOf(price, breaks) {
    let zone = 0;
    while (zone < breaks.length - 1 && price > breaks[zone]) zone += 1;
    return zone + 1;
  }

  root.BenderTariffModel = Object.freeze({
    basePrice,
    externalSurcharge,
    gateAt,
    haversineKm,
    routeGateMetrics,
    segmentIntersectionFraction,
    symmetricRouteGateMetrics,
    weightedJenks,
    zoneOf,
  });
}(globalThis));
