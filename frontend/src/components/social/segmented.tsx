"use client";

import { Button } from "@/components/ui/button";

/** Grupo de botones para elegir una opción (Semana/Mes, métrica, deporte…), con botones ≥ 44 px. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="flex gap-1 overflow-x-auto [scrollbar-width:none]"
    >
      {options.map((o) => (
        <Button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          size="sm"
          variant={value === o.value ? "default" : "outline"}
          className="min-h-11 shrink-0 md:min-h-8"
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </Button>
      ))}
    </div>
  );
}
