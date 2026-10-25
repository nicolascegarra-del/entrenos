"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { TourOverlay } from "@/components/tour/tour-overlay";
import { useModules } from "@/hooks/use-api";
import { apiFetch } from "@/lib/api";
import {
  FIRST_ACTIVITY,
  markSeen,
  nextIndex,
  tourByKey,
  type Tour,
  type TourKey,
} from "@/lib/tours";
import type { ActivityPage } from "@/types/api";

const ACTIVE_KEY = "tour-activo";
const WAIT_MS = 2500;

interface TourContext {
  start: (key: TourKey) => void;
  stop: () => void;
  active: TourKey | null;
}

const Ctx = createContext<TourContext>({
  start: () => undefined,
  stop: () => undefined,
  active: null,
});

export const useTour = () => useContext(Ctx);

/** Primer elemento visible con ese `data-tour` (hay versiones de móvil y de escritorio). */
export function findTarget(name: string): HTMLElement | null {
  const nodes = document.querySelectorAll<HTMLElement>(
    `[data-tour~="${name}"]`,
  );
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (
      r.width > 0 &&
      r.height > 0 &&
      getComputedStyle(el).visibility !== "hidden"
    )
      return el;
  }
  return null;
}

/**
 * Lleva el elemento a la vista (centrado; si es muy alto, su principio bajo la cabecera para que el
 * bocadillo vaya debajo). Devuelve el scroll buscado para comprobar luego que se llegó.
 */
function reveal(el: HTMLElement, behavior: ScrollBehavior): number {
  const r = el.getBoundingClientRect();
  const vh = window.innerHeight;
  const wanted =
    r.height > vh * 0.6
      ? window.scrollY + r.top - 80
      : window.scrollY + r.top + r.height / 2 - vh / 2;
  const max = document.documentElement.scrollHeight - vh;
  const top = Math.max(0, Math.min(wanted, max));
  window.scrollTo({ top, behavior });
  return top;
}

/** Tour a medias guardado; solo se reanuda en la misma pantalla en la que se quedó (p. ej. al recargar). */
function readActive(): { key: TourKey; index: number } | null {
  try {
    const raw = JSON.parse(sessionStorage.getItem(ACTIVE_KEY) ?? "null");
    return raw && tourByKey(raw.key) && raw.path === window.location.pathname
      ? { key: raw.key, index: raw.index }
      : null;
  } catch {
    return null;
  }
}

function saveActive(
  value: { key: TourKey; index: number } | null,
  path: string,
) {
  try {
    if (value)
      sessionStorage.setItem(ACTIVE_KEY, JSON.stringify({ ...value, path }));
    else sessionStorage.removeItem(ACTIVE_KEY);
  } catch {
    // Sin almacenamiento: el tour sigue mientras no se recargue la página.
  }
}

/**
 * Tours guiados: estado del tour activo (sobrevive al cambiar de pantalla), navegación entre pantallas
 * y espera a que aparezca cada elemento antes de mostrar su bocadillo.
 */
export function TourProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<{ key: TourKey; index: number } | null>(
    null,
  );
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [ready, setReady] = useState(false);
  const { data: modules } = useModules();
  const tour: Tour | undefined = state
    ? tourByKey(state.key, modules)
    : undefined;
  const step = tour && state ? tour.steps[state.index] : undefined;

  useEffect(() => setState(readActive()), []);
  useEffect(() => saveActive(state, pathname), [state, pathname]);

  const stop = useCallback(() => {
    setState(null);
    setTarget(null);
    setReady(false);
  }, []);

  const start = useCallback((key: TourKey) => {
    setReady(false);
    setTarget(null);
    setState({ key, index: 0 });
  }, []);

  const move = useCallback(
    (dir: 1 | -1) => {
      if (!tour || !state) return;
      const i = nextIndex(tour.steps, state.index, dir, (t) => !!findTarget(t));
      if (i === null) {
        if (dir === 1) {
          try {
            markSeen(localStorage, tour.key);
          } catch {
            // ver markSeen
          }
          stop();
        }
        return;
      }
      setReady(false);
      setTarget(null);
      setState({ key: tour.key, index: i });
    },
    [tour, state, stop],
  );

  // Cada paso: ir a su pantalla si hace falta y esperar al elemento.
  useEffect(() => {
    if (!step || !tour || !state) return;
    let cancelled = false;
    const go = async () => {
      if (step.route) {
        let route = step.route;
        if (route === FIRST_ACTIVITY) {
          if (/^\/actividades\/\d+$/.test(pathname)) route = pathname;
          else {
            const page = await apiFetch<ActivityPage>(
              "/api/v1/activities?limit=1",
            ).catch(() => null);
            const first = page?.items[0];
            if (!first) {
              setTarget(null);
              setReady(true);
              return;
            }
            route = `/actividades/${first.id}`;
          }
        }
        if (route !== pathname) {
          router.push(route);
          return; // el efecto vuelve a correr con la ruta nueva
        }
      }
      if (!step.target) {
        setTarget(null);
        setReady(true);
        return;
      }
      const startAt = Date.now();
      while (!cancelled && Date.now() - startAt < WAIT_MS) {
        const el = findTarget(step.target);
        if (el) {
          const reduce = window.matchMedia(
            "(prefers-reduced-motion: reduce)",
          ).matches;
          const top = reveal(el, reduce ? "auto" : "smooth");
          await new Promise((r) => setTimeout(r, reduce ? 0 : 400));
          // A veces el navegador ignora o corta el desplazamiento suave: se termina de golpe.
          if (Math.abs(window.scrollY - top) > 4) reveal(el, "auto");
          if (!cancelled) {
            setTarget(el);
            setReady(true);
          }
          return;
        }
        await new Promise((r) => setTimeout(r, 120));
      }
      if (cancelled) return;
      if (step.optional) move(1);
      else {
        setTarget(null);
        setReady(true);
      }
    };
    void go();
    return () => {
      cancelled = true;
    };
  }, [step, tour, state, pathname, router, move]);

  const value = useMemo(
    () => ({ start, stop, active: state?.key ?? null }),
    [start, stop, state],
  );
  return (
    <Ctx.Provider value={value}>
      {children}
      {tour && step && state && ready && (
        <TourOverlay
          tour={tour}
          index={state.index}
          target={target}
          onNext={() => move(1)}
          onBack={() => move(-1)}
          onClose={stop}
        />
      )}
    </Ctx.Provider>
  );
}
