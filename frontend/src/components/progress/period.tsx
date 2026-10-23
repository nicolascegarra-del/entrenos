"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { PERIODS } from "@/components/progress/sections";

const KEY = "progreso.periodo";
const PeriodContext = createContext<{
  days: number;
  setDays: (d: number) => void;
}>({
  days: 180,
  setDays: () => undefined,
});

/** Periodo elegido (3 meses, 6 meses…), común a Forma, Rendimiento y Salud y recordado en este navegador. */
export function PeriodProvider({ children }: { children: React.ReactNode }) {
  const [days, setDaysState] = useState(180);
  useEffect(() => {
    try {
      const saved = Number(window.localStorage.getItem(KEY));
      if (PERIODS.some((p) => p.days === saved)) setDaysState(saved);
    } catch {
      // Sin almacenamiento (modo privado): se queda el de por defecto.
    }
  }, []);
  const setDays = (d: number) => {
    setDaysState(d);
    try {
      window.localStorage.setItem(KEY, String(d));
    } catch {
      // Ignorado: es solo una comodidad.
    }
  };
  return (
    <PeriodContext.Provider value={{ days, setDays }}>
      {children}
    </PeriodContext.Provider>
  );
}

export const usePeriod = () => useContext(PeriodContext);

export function PeriodPicker() {
  const { days, setDays } = usePeriod();
  return (
    <div
      className="flex gap-1 overflow-x-auto"
      role="group"
      aria-label="Periodo"
    >
      {PERIODS.map((p) => (
        <Button
          key={p.days}
          size="sm"
          variant={days === p.days ? "default" : "outline"}
          aria-pressed={days === p.days}
          className="min-h-11 shrink-0 md:min-h-8"
          onClick={() => setDays(p.days)}
        >
          {p.label}
        </Button>
      ))}
    </div>
  );
}
