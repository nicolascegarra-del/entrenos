/** Lunes (00:00 local) de la semana de una fecha. */
export function weekStart(date: Date): Date {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d;
}

/**
 * Agrupa elementos con fecha por semana (lunes a domingo), conservando el orden de entrada.
 * @returns Grupos con la clave AAAA-MM-DD del lunes y sus elementos.
 */
export function groupByWeek<T>(
  items: T[],
  dateOf: (item: T) => string,
): { week: string; items: T[] }[] {
  const groups: { week: string; items: T[] }[] = [];
  for (const item of items) {
    const w = weekStart(new Date(dateOf(item)));
    const key = `${w.getFullYear()}-${String(w.getMonth() + 1).padStart(2, "0")}-${String(w.getDate()).padStart(2, "0")}`;
    const last = groups[groups.length - 1];
    if (last?.week === key) last.items.push(item);
    else groups.push({ week: key, items: [item] });
  }
  return groups;
}

/** «Esta semana», «Semana pasada» o «Semana del 6 oct». */
export function weekLabel(week: string, today: Date = new Date()): string {
  const current = weekStart(today).getTime();
  const start = new Date(`${week}T00:00:00`).getTime();
  const diff = Math.round((current - start) / (7 * 86400000));
  if (diff === 0) return "Esta semana";
  if (diff === 1) return "Semana pasada";
  return `Semana del ${new Date(`${week}T12:00:00`).toLocaleDateString("es-ES", { day: "numeric", month: "short" })}`;
}
