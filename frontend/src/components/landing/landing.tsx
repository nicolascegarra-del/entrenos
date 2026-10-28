"use client";

import {
  BarChart3,
  Brain,
  CalendarCheck,
  Check,
  HeartPulse,
  MapPinned,
  Sparkles,
  Watch,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

import { LoginForm } from "@/components/auth/login-form";
import { Logo } from "@/components/brand/logo";
import { InstallGuide } from "@/components/landing/install-guide";
import { Button } from "@/components/ui/button";
import { useAuthOptions } from "@/hooks/use-api";

interface Feature {
  icon: LucideIcon;
  title: string;
  text: string;
}

const FEATURES: Feature[] = [
  {
    icon: CalendarCheck,
    title: "Crea entrenos y mándalos al reloj",
    text: "Sesiones por bloques con ritmo, pulso o potencia, y un plan automático hacia tu carrera que se ajusta cada semana. Se envían solas a Garmin y COROS; para el resto, en FIT o GPX.",
  },
  {
    icon: BarChart3,
    title: "Métricas de rendimiento de verdad",
    text: "Forma y frescura, tiempo en cada zona, VO2max y tu percentil, deriva cardiaca, parciales con FC y cadencia, previsión de tus marcas y tests de umbral y lactato.",
  },
  {
    icon: Watch,
    title: "Todos tus relojes, en un sitio",
    text: `Garmin, COROS, Apple Watch y, vía Health Connect, Samsung, Xiaomi, Amazfit, Huawei o Wear OS. También el anillo Oura, con tu sueño, recuperación y actividad. Y ficheros FIT, GPX y TCX de Suunto, Polar, Wahoo… sin duplicados.`,
  },
  {
    icon: MapPinned,
    title: "Rutas con su desnivel",
    text: "Dibuja tu ruta por asfalto o por senderos y mira los kilómetros, el desnivel y el perfil antes de salir. Luego llévala a tu reloj.",
  },
  {
    icon: HeartPulse,
    title: "Salud y progreso",
    text: "FC en reposo, variabilidad, fases del sueño, recuperación y temperatura (con Oura), logros y rachas, y avisos cuando subes la carga demasiado rápido para que no te lesiones.",
  },
];

const WHY = [
  "Todos tus relojes y apps en una sola cuenta, aunque cambies de marca.",
  "Un entrenador con IA sin pagar otra suscripción: usas tu propia cuenta.",
  "El plan se adapta cada semana a lo que haces y a cómo llegas.",
  "Te explica cada dato en lenguaje llano y en español.",
  "Sin anuncios. Tus datos son tuyos: los exportas o los borras cuando quieras.",
];

const STEPS = [
  {
    title: "Crea tu cuenta",
    text: "Solo tu email. Gratis.",
  },
  {
    title: "Conecta tu reloj",
    text: "Garmin, COROS, Apple Watch, Android… y se traen tus entrenos.",
  },
  {
    title: "Conoce a tu entrenador",
    text: "Una entrevista de 5 minutos y empieza a entrenarte como lo haría un entrenador personal.",
  },
];

/** Landing pública de KTrain con el inicio de sesión integrado. */
export function Landing() {
  const { data: options } = useAuthOptions();
  const signup = options?.signup_available;
  const signupLabel =
    options?.registration === "approval"
      ? "Solicitar cuenta"
      : "Crear cuenta gratis";

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-white/10 bg-klyp-navy/95 pt-[env(safe-area-inset-top)] text-white backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-2 px-4">
          <Logo className="text-xl" onDark />
          <nav className="flex items-center gap-1" aria-label="Acceso">
            <Button
              asChild
              variant="ghost"
              className="min-h-11 text-white hover:bg-white/10 hover:text-white"
            >
              <a href="#entrar">Entrar</a>
            </Button>
            {signup && (
              <Button
                asChild
                className="min-h-11 bg-klyp-accent text-white hover:bg-klyp-accent/90"
              >
                <Link href="/registro">
                  {options?.registration === "approval"
                    ? "Solicitar"
                    : "Crear cuenta"}
                </Link>
              </Button>
            )}
          </nav>
        </div>
      </header>

      <main>
        {/* Hero: qué es y el inicio de sesión a mano. */}
        <section className="bg-klyp-navy text-white">
          <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 md:py-16 lg:grid-cols-[1fr_24rem] lg:items-center lg:gap-12">
            <div className="space-y-5">
              <p className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-sm">
                <Sparkles className="size-4 text-klyp-accent" aria-hidden />
                Entrenador personal con IA
              </p>
              <h1 className="font-heading text-4xl leading-tight font-bold md:text-5xl">
                Entrena con un plan que te conoce,{" "}
                <span className="text-[#7FB2EE]">sea cual sea tu reloj</span>
              </h1>
              <p className="max-w-xl text-lg text-white/80">
                KTrain junta tus entrenos de Garmin, COROS, Apple Watch o
                Android, te los explica con métricas avanzadas y pone a tu lado
                un entrenador con IA que planifica contigo y manda las sesiones
                a tu reloj.
              </p>
              <div className="flex flex-wrap gap-3">
                {signup ? (
                  <Button
                    asChild
                    size="lg"
                    className="h-12 px-6 text-base bg-klyp-accent text-white hover:bg-klyp-accent/90"
                  >
                    <Link href="/registro">{signupLabel}</Link>
                  </Button>
                ) : null}
                <Button
                  asChild
                  size="lg"
                  variant="outline"
                  className="h-12 border-white/30 bg-transparent px-6 text-base text-white hover:bg-white/10 hover:text-white"
                >
                  <a href="#instalar">Instálala en tu móvil</a>
                </Button>
              </div>
            </div>
            <div
              id="entrar"
              className="scroll-mt-20 rounded-lg bg-card p-5 text-card-foreground shadow-md md:p-6"
            >
              <h2 className="font-heading text-xl font-semibold">
                Entra en KTrain
              </h2>
              <p className="mb-4 text-sm text-muted-foreground">
                Tus entrenos, tu plan y tu entrenador.
              </p>
              <LoginForm options={options} />
            </div>
          </div>
        </section>

        {/* El entrenador IA, lo más diferencial. */}
        <section className="mx-auto max-w-6xl px-4 py-12 md:py-16">
          <div className="grid gap-6 rounded-lg border border-klyp-accent/40 bg-klyp-accent/5 p-5 md:grid-cols-[auto_1fr] md:p-8">
            <span className="flex size-14 items-center justify-center rounded-lg bg-klyp-accent text-white">
              <Brain className="size-7" aria-hidden />
            </span>
            <div className="space-y-3">
              <h2 className="font-heading text-2xl font-bold md:text-3xl">
                Tu entrenador virtual, con tu propia cuenta de IA
              </h2>
              <p className="text-muted-foreground">
                Conecta tu cuenta de ChatGPT, Gemini o Claude y tendrás un
                entrenador que mira todos tus datos: analiza cada entreno al
                sincronizar, recuerda tu historial, lesiones y disponibilidad,
                te hace una revisión cada domingo y te propone cambios en el
                plan que tú aceptas o rechazas.
              </p>
              <ul className="grid gap-2 sm:grid-cols-2">
                {[
                  "Pregúntale lo que quieras: te dice en qué datos se basa",
                  "Empieza con una entrevista y completa tu ficha",
                  "Ajusta tu plan según cómo llegas cada semana",
                  "Pagas solo lo que usas en tu propia cuenta",
                ].map((t) => (
                  <li key={t} className="flex gap-2 text-sm">
                    <Check
                      className="mt-0.5 size-4 shrink-0 text-klyp-accent"
                      aria-hidden
                    />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* El resto de lo que ofrece. */}
        <section aria-labelledby="ofrece" className="bg-muted/40">
          <div className="mx-auto max-w-6xl px-4 py-12 md:py-16">
            <h2
              id="ofrece"
              className="text-center font-heading text-2xl font-bold md:text-3xl"
            >
              Todo lo que necesitas para entrenar mejor
            </h2>
            <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <li
                  key={title}
                  className="rounded-lg border bg-card p-5 shadow-sm"
                >
                  <Icon className="size-6 text-klyp-accent" aria-hidden />
                  <h3 className="mt-3 font-heading text-lg font-semibold">
                    {title}
                  </h3>
                  <p className="mt-1 text-sm text-muted-foreground">{text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Por qué es diferente. */}
        <section className="mx-auto max-w-3xl px-4 py-12 md:py-16">
          <h2 className="text-center font-heading text-2xl font-bold md:text-3xl">
            ¿Qué tiene que no tengan las demás?
          </h2>
          <ul className="mt-6 space-y-3">
            {WHY.map((t) => (
              <li key={t} className="flex gap-3 rounded-lg border bg-card p-4">
                <Check
                  className="mt-0.5 size-5 shrink-0 text-klyp-accent"
                  aria-hidden
                />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* Cómo empezar. */}
        <section className="bg-klyp-navy text-white">
          <div className="mx-auto max-w-6xl px-4 py-12 md:py-16">
            <h2 className="text-center font-heading text-2xl font-bold md:text-3xl">
              Empieza en 3 pasos
            </h2>
            <ol className="mt-8 grid gap-4 md:grid-cols-3">
              {STEPS.map((s, i) => (
                <li key={s.title} className="rounded-lg bg-white/5 p-5">
                  <span className="flex size-9 items-center justify-center rounded-full bg-klyp-accent font-semibold">
                    {i + 1}
                  </span>
                  <h3 className="mt-3 font-heading text-lg font-semibold">
                    {s.title}
                  </h3>
                  <p className="mt-1 text-sm text-white/75">{s.text}</p>
                </li>
              ))}
            </ol>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              {signup && (
                <Button
                  asChild
                  size="lg"
                  className="h-12 px-6 text-base bg-klyp-accent text-white hover:bg-klyp-accent/90"
                >
                  <Link href="/registro">{signupLabel}</Link>
                </Button>
              )}
              <Button
                asChild
                size="lg"
                variant="outline"
                className="h-12 border-white/30 bg-transparent px-6 text-base text-white hover:bg-white/10 hover:text-white"
              >
                <a href="#entrar">Ya tengo cuenta</a>
              </Button>
            </div>
          </div>
        </section>

        <InstallGuide />
      </main>

      <footer className="border-t pb-[env(safe-area-inset-bottom)]">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <Logo className="text-base text-foreground" markClassName="size-5" />
          <p>
            Las respuestas de la IA son orientaciones de entrenamiento, no
            consejo médico.
          </p>
        </div>
      </footer>
    </div>
  );
}
