import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deriveCycleSummary } from '../src/utils.js';

test('groups consecutive bleeding days into episodes and averages valid cycle gaps', () => {
  const rows = [
    { recorded_on: '2026-01-01', flow: 3 },
    { recorded_on: '2026-01-03', flow: 2 },
    { recorded_on: '2026-01-29', flow: 3 },
    { recorded_on: '2026-01-30', flow: 4 },
    { recorded_on: '2026-02-26', flow: 3 },
  ];
  assert.deepEqual(deriveCycleSummary(rows), {
    bleedingDays: 5,
    starts: ['2026-01-01', '2026-01-29', '2026-02-26'],
    lengths: [28, 28],
    average: 28,
  });
});

test('ignores spotting and intervals outside supported descriptive range', () => {
  const rows = [
    { recorded_on: '2026-01-01', flow: 1 },
    { recorded_on: '2026-01-02', flow: 3 },
    { recorded_on: '2026-01-07', flow: 3 },
    { recorded_on: '2026-09-01', flow: 3 },
  ];
  const summary = deriveCycleSummary(rows);
  assert.equal(summary.bleedingDays, 3);
  assert.deepEqual(summary.starts, ['2026-01-02', '2026-09-01']);
  assert.deepEqual(summary.lengths, []);
  assert.equal(summary.average, null);
});

test('handles empty or missing data', () => {
  assert.deepEqual(deriveCycleSummary(), { bleedingDays: 0, starts: [], lengths: [], average: null });
});
