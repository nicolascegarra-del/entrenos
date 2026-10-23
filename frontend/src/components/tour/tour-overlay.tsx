"use client";

import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { Tour } from "@/lib/tours";

const PAD = 6;
const GAP = 12;
const BUBBLE_W = 340;
const MOBILE = 768;

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

function rectOf(el: HTMLElement | null): Box | null {
  if (!el || !el.isConnected) return null;
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return null;
  return {
    top: r.top - PAD,
    left: r.left - PAD,
    width: r.width + PAD * 2,
    height: r.height + PAD * 2,
  };
}

/**
 * Posición del bocadillo. En el móvil, una tarjeta a lo ancho en el lado contrario al elemento;
 * en el PC, junto al elemento (debajo, encima o al lado, lo que quepa) sin salirse de la pantalla.
 */
function placeBubble(
  hole: Box | null,
  bubble: { width: number; height: number },
) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (vw < MOBILE) {
    if (!hole) return { mode: "center" as const };
    // Elementos muy altos: se ve su principio y la tarjeta va abajo.
    const below = hole.height > vh * 0.6 || hole.top + hole.height / 2 < vh / 2;
    return { mode: below ? ("bottom" as const) : ("top" as const) };
  }
  if (!hole) return { mode: "center" as const };
  const w = Math.min(BUBBLE_W, vw - 24);
  const clampX = (x: number) => Math.max(12, Math.min(x, vw - w - 12));
  const clampY = (y: number) =>
    Math.max(12, Math.min(y, vh - bubble.height - 12));
  const cx = clampX(hole.left + hole.width / 2 - w / 2);
  if (hole.top + hole.height + GAP + bubble.height <= vh - 12)
    return {
      mode: "abs" as const,
      top: hole.top + hole.height + GAP,
      left: cx,
      width: w,
    };
  if (hole.top - GAP - bubble.height >= 12)
    return {
      mode: "abs" as const,
      top: hole.top - GAP - bubble.height,
      left: cx,
      width: w,
    };
  const cy = clampY(hole.top + hole.height / 2 - bubble.height / 2);
  if (hole.left + hole.width + GAP + w <= vw - 12)
    return {
      mode: "abs" as const,
      top: cy,
      left: hole.left + hole.width + GAP,
      width: w,
    };
  if (hole.left - GAP - w >= 12)
    return {
      mode: "abs" as const,
      top: cy,
      left: hole.left - GAP - w,
      width: w,
    };
  return {
    mode: "abs" as const,
    top: clampY(vh - bubble.height - 12),
    left: cx,
    width: w,
  };
}

export function TourOverlay({
  tour,
  index,
  target,
  onNext,
  onBack,
  onClose,
}: {
  tour: Tour;
  index: number;
  target: HTMLElement | null;
  onNext: () => void;
  onBack: () => void;
  onClose: () => void;
}) {
  const step = tour.steps[index];
  const last = index === tour.steps.length - 1;
  const bubbleRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const [hole, setHole] = useState<Box | null>(() => rectOf(target));
  const [size, setSize] = useState({ width: BUBBLE_W, height: 180 });

  // Sigue al elemento si la página se mueve o cambia de tamaño.
  useEffect(() => {
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setHole(rectOf(target)));
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [target]);

  // Tamaño real del bocadillo (cambia con cada texto) para colocarlo sin que se salga.
  useEffect(() => {
    const el = bubbleRef.current;
    if (!el) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      setSize((s) =>
        Math.abs(r.height - s.height) > 1 || Math.abs(r.width - s.width) > 1
          ? { width: r.width, height: r.height }
          : s,
      );
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    nextRef.current?.focus({ preventScroll: true });
  }, [index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") onNext();
      else if (e.key === "ArrowLeft" && index > 0) onBack();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onNext, onBack, index]);

  const place = placeBubble(hole, size);
  const style: React.CSSProperties =
    place.mode === "abs"
      ? { top: place.top, left: place.left, width: place.width }
      : place.mode === "top"
        ? { top: "calc(env(safe-area-inset-top) + 12px)", left: 12, right: 12 }
        : place.mode === "bottom"
          ? {
              bottom: "calc(env(safe-area-inset-bottom) + 12px)",
              left: 12,
              right: 12,
            }
          : {
              top: "50%",
              left: "50%",
              width: `min(${BUBBLE_W}px, calc(100vw - 24px))`,
              transform: "translate(-50%, -50%)",
            };

  return (
    <div className="fixed inset-0 z-[100]" data-tour-overlay>
      {/* Bloquea los toques en la página; tocar fuera no cierra para no salir sin querer. */}
      <div className="absolute inset-0" aria-hidden />
      {hole ? (
        <div
          aria-hidden
          className="pointer-events-none absolute rounded-lg outline-2 outline-klyp-accent outline-solid transition-all duration-300 motion-reduce:transition-none"
          style={{ ...hole, boxShadow: "0 0 0 9999px rgb(0 0 0 / 0.6)" }}
        />
      ) : (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-black/60"
        />
      )}
      <div
        ref={bubbleRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        className="absolute rounded-lg border bg-popover p-4 text-popover-foreground shadow-md"
        style={style}
      >
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1" aria-live="polite">
            <p className="text-xs text-muted-foreground">
              {tour.title} · {index + 1} de {tour.steps.length}
            </p>
            <h2
              id="tour-title"
              className="mt-0.5 font-heading text-base font-semibold"
            >
              {step.title}
            </h2>
            <p id="tour-body" className="mt-1 text-sm text-muted-foreground">
              {step.body}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="-mr-2 -mt-2 size-11 shrink-0 md:size-8"
            aria-label="Salir del tour"
            onClick={onClose}
          >
            <X aria-hidden />
          </Button>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button
            variant="ghost"
            className="min-h-11 md:min-h-9"
            onClick={onClose}
          >
            Salir
          </Button>
          <span className="flex-1" />
          {index > 0 && (
            <Button
              variant="outline"
              className="min-h-11 md:min-h-9"
              onClick={onBack}
            >
              <ChevronLeft aria-hidden /> Atrás
            </Button>
          )}
          <Button
            ref={nextRef}
            className="min-h-11 md:min-h-9"
            onClick={onNext}
          >
            {last ? "Terminar" : "Siguiente"}
            {!last && <ChevronRight aria-hidden />}
          </Button>
        </div>
      </div>
    </div>
  );
}
