export function deriveCycleSummary(days = []) {
  const bleeding = days.filter((row) => Number(row.flow) >= 2).map((row) => row.recorded_on).sort();
  const starts = bleeding.filter((day, index) => index === 0 || (Date.parse(`${day}T12:00:00Z`) - Date.parse(`${bleeding[index - 1]}T12:00:00Z`)) / 86400000 > 7);
  const lengths = starts.slice(1).map((day, index) => Math.round((Date.parse(`${day}T12:00:00Z`) - Date.parse(`${starts[index]}T12:00:00Z`)) / 86400000)).filter((length) => length >= 10 && length <= 200);
  const recent = lengths.slice(-4);
  return {
    bleedingDays: bleeding.length,
    starts,
    lengths,
    average: recent.length ? Math.round(recent.reduce((total, value) => total + value, 0) / recent.length) : null,
  };
}
