import { STATUS, scoreStatus } from "@/lib/plan";
import { cn } from "@/lib/utils";
import type { StepStatus } from "@/types/api";

/** Estado con icono + texto + color (nunca solo color). */
export function StatusBadge({
  status,
  children,
}: {
  status: StepStatus;
  children?: React.ReactNode;
}) {
  const { label, icon: Icon, className } = STATUS[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium",
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {children ?? label}
    </span>
  );
}

export function ScoreBadge({ score }: { score: number | null }) {
  const status = scoreStatus(score);
  if (status == null || score == null) return null;
  return <StatusBadge status={status}>{Math.round(score)} %</StatusBadge>;
}
