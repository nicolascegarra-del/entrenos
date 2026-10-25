import { cn } from "@/lib/utils";

/** Monograma de KTrain: «K» blanca sobre accent, con un trazo de pulso que sale de la pata inferior. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden
      className={cn("size-7 shrink-0", className)}
    >
      <rect width="32" height="32" rx="8" fill="#2E6DB4" />
      <path
        d="M10 7v18M10 17l9-10M13.5 13.5 20 21h3l2-4 2 6"
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Logo con el nombre: KTrain. */
export function Logo({
  className,
  markClassName,
  onDark = false,
}: {
  className?: string;
  markClassName?: string;
  /** Sobre fondo navy, «Train» en azul claro para que se lea. */
  onDark?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 font-heading font-semibold tracking-tight",
        className,
      )}
    >
      <LogoMark className={markClassName} />
      <span>
        K
        <span className={onDark ? "text-[#7FB2EE]" : "text-klyp-accent"}>
          Train
        </span>
      </span>
    </span>
  );
}
