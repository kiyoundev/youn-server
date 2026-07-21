export function formatStorage(tb: number | undefined): string {
  const value = Number(tb ?? 0);
  if (value < 1) return `${Math.round(value * 1000)}GB`;
  return `${value.toFixed(1)}TB`;
}
