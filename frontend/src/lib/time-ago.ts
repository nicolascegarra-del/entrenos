/** «ahora», «hace 12 min», «hace 3 h», «hace 2 días» (para el estado de la sincronización). */
export function timeAgo(
  iso: string | null | undefined,
  now: Date = new Date(),
): string {
  if (!iso) return "nunca";
  const diff = Math.max(0, now.getTime() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "ahora";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  const days = Math.floor(diff / 86400);
  return `hace ${days} ${days === 1 ? "día" : "días"}`;
}
