"use client";

import {
  Activity,
  ArrowLeft,
  ArrowRight,
  CircleCheck,
  CircleDashed,
  Loader2,
  Sparkles,
  UserRound,
  Watch,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";

import { AiProvidersCard } from "@/components/settings/ai-providers-card";
import { ProfileCard } from "@/components/settings/profile-card";
import { WatchConnections } from "@/components/settings/watch-connections";
import { Button } from "@/components/ui/button";
import {
  useAiProviders,
  useFinishOnboarding,
  useGarminStatus,
  useModuleOn,
  useProfile,
  useSources,
} from "@/hooks/use-api";
import { ONBOARDING_STEPS, stepIndex } from "@/lib/onboarding";
import { cn } from "@/lib/utils";
import { otherWatch } from "@/lib/watch-brands";

/** Barra de progreso con el nombre de cada paso. */
function Progress({ current }: { current: number }) {
  return (
    <nav aria-label="Pasos de la configuración" className="space-y-2">
      <p className="text-sm text-muted-foreground">
        Paso {current + 1} de {ONBOARDING_STEPS.length}:{" "}
        <span className="font-medium text-foreground">
          {ONBOARDING_STEPS[current].label}
        </span>
      </p>
      <ol className="flex gap-1.5">
        {ONBOARDING_STEPS.map((s, i) => (
          <li
            key={s.key}
            aria-current={i === current ? "step" : undefined}
            className={cn(
              "h-1.5 flex-1 rounded-full",
              i <= current ? "bg-klyp-accent" : "bg-muted",
            )}
          >
            <span className="sr-only">
              {s.label}
              {i < current ? " (hecho)" : ""}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function Intro({ text }: { text: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground md:text-base">{text}</p>;
}

/** Fila del resumen final: hecho / pendiente y enlace para volver al paso. */
function CheckRow({
  done,
  label,
  pending,
  step,
  optional,
}: {
  done: boolean | undefined;
  label: string;
  pending: string;
  step: string;
  optional?: boolean;
}) {
  return (
    <li className="flex items-start gap-3 rounded-lg border p-3">
      {done ? (
        <CircleCheck
          className="mt-0.5 size-5 shrink-0 text-emerald-600"
          aria-label="Hecho"
        />
      ) : (
        <CircleDashed
          className="mt-0.5 size-5 shrink-0 text-muted-foreground"
          aria-label="Pendiente"
        />
      )}
      <span className="min-w-0 flex-1">
        <span className="block font-medium">{label}</span>
        {!done && (
          <span className="block text-sm text-muted-foreground">
            {pending}
            {optional && " (opcional)"}
          </span>
        )}
      </span>
      {!done && (
        <Link
          href={`/bienvenida?paso=${step}`}
          className="shrink-0 text-sm font-medium text-klyp-accent hover:underline"
        >
          Configurar
        </Link>
      )}
    </li>
  );
}

function Summary() {
  const garmin = useGarminStatus();
  const sources = useSources();
  const profile = useProfile();
  const watch = garmin.data?.connected ? "Garmin" : otherWatch(sources.data);
  const ai = useAiProviders();
  const iaOn = useModuleOn("ia");
  const profileDone =
    !!profile.data?.birth_date &&
    !!profile.data?.sex &&
    !!profile.data?.weight_kg;
  return (
    <div className="space-y-3">
      <Intro text="Así queda tu cuenta. Lo que falte lo puedes completar cuando quieras desde Ajustes." />
      <ul className="space-y-2">
        <CheckRow
          done={!!watch}
          label={watch ? `${watch} conectado` : "Reloj conectado"}
          pending="Sin reloj no hay entrenos que analizar."
          step="reloj"
        />
        <CheckRow
          done={profileDone}
          label="Perfil completo"
          pending="Fecha de nacimiento, sexo y peso afinan zonas, percentiles y previsiones."
          step="perfil"
        />
        {iaOn && (
          <CheckRow
            done={ai.data?.providers.some((p) => p.configured && p.enabled)}
            label="Asistente IA"
            pending="Para preguntar sobre tus entrenamientos."
            step="ia"
            optional
          />
        )}
      </ul>
      {watch && (
        <p className="text-sm text-muted-foreground">
          La primera sincronización puede tardar unos minutos; tus entrenos irán
          apareciendo en Entrenos y en Hoy.
        </p>
      )}
    </div>
  );
}

function Wizard() {
  const router = useRouter();
  const params = useSearchParams();
  const current = stepIndex(params.get("paso"));
  const step = ONBOARDING_STEPS[current].key;
  const finish = useFinishOnboarding();
  const iaOn = useModuleOn("ia");
  const last = current === ONBOARDING_STEPS.length - 1;

  const go = (i: number) =>
    router.push(`/bienvenida?paso=${ONBOARDING_STEPS[i].key}`, {
      scroll: true,
    });

  const done = () =>
    finish.mutate(undefined, {
      onSuccess: () => router.replace("/"),
      onError: () => toast.error("No se pudo guardar. Inténtalo de nuevo."),
    });

  return (
    <div className="mx-auto w-full max-w-2xl space-y-5">
      <Progress current={current} />

      {step === "bienvenida" && (
        <section className="space-y-4">
          <h1 className="font-heading text-2xl font-bold md:text-3xl">
            Te damos la bienvenida a KTrain
          </h1>
          <Intro text="En tres pasos dejamos tu cuenta lista. Cualquier paso se puede saltar y completar más tarde en Ajustes." />
          <ul className="space-y-2">
            {[
              {
                icon: Watch,
                title: "Conectar tu reloj",
                text: "Garmin, Apple Watch, COROS, Samsung, Xiaomi, Huawei, Suunto, Polar…: tus entrenos y métricas diarias.",
              },
              {
                icon: UserRound,
                title: "Tu perfil",
                text: "Edad, sexo, peso y altura afinan zonas, percentiles y previsiones.",
              },
              {
                icon: Sparkles,
                title: "Asistente IA (opcional)",
                text: "Tu cuenta de ChatGPT, Gemini o Claude para preguntar sobre tus entrenamientos.",
              },
            ].map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3 rounded-lg border p-3">
                <Icon
                  className="mt-0.5 size-5 shrink-0 text-klyp-accent"
                  aria-hidden
                />
                <span>
                  <span className="block font-medium">{title}</span>
                  <span className="block text-sm text-muted-foreground">
                    {text}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {step === "reloj" && (
        <section className="space-y-3">
          <h1 className="font-heading text-2xl font-bold">Conecta tu reloj</h1>
          <Intro text="Elige la marca de tu reloj (y tu anillo Oura, si lo tienes) y te decimos cómo traer tus datos. Nunca guardamos tus contraseñas." />
          <WatchConnections />
        </section>
      )}

      {step === "perfil" && (
        <section className="space-y-3">
          <h1 className="font-heading text-2xl font-bold">Tu perfil</h1>
          <Intro text="Revisa o completa tus datos. Con la fecha de nacimiento se estima tu FC máxima y se comparan tus marcas y tu VO2max con gente de tu edad." />
          <ProfileCard />
        </section>
      )}

      {step === "ia" && (
        <section className="space-y-3">
          <h1 className="font-heading text-2xl font-bold">
            Asistente IA{" "}
            <span className="text-base font-normal text-muted-foreground">
              (opcional)
            </span>
          </h1>
          {iaOn ? (
            <>
              <Intro text="Si quieres preguntar sobre tus entrenamientos, conecta tu cuenta de ChatGPT, Gemini o Claude con una clave de API. Si no, salta este paso." />
              <AiProvidersCard />
            </>
          ) : (
            <Intro text="El administrador ha desactivado el entrenador IA en esta app. Salta este paso." />
          )}
        </section>
      )}

      {step === "listo" && (
        <section className="space-y-3">
          <h1 className="flex items-center gap-2 font-heading text-2xl font-bold">
            <Activity className="size-6 text-klyp-accent" aria-hidden />
            Todo listo
          </h1>
          <Summary />
        </section>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t pt-4">
        {current > 0 && (
          <Button
            variant="ghost"
            className="min-h-11 md:min-h-9"
            onClick={() => go(current - 1)}
          >
            <ArrowLeft aria-hidden /> Atrás
          </Button>
        )}
        {!last && (
          <button
            type="button"
            className="min-h-11 text-sm text-muted-foreground underline-offset-4 hover:underline md:min-h-9"
            onClick={done}
            disabled={finish.isPending}
          >
            {current === 0 ? "Ahora no, ir a la app" : "Terminar más tarde"}
          </button>
        )}
        <Button
          className="ml-auto min-h-11 md:min-h-9"
          onClick={() => (last ? done() : go(current + 1))}
          disabled={finish.isPending}
        >
          {finish.isPending && <Loader2 className="animate-spin" />}
          {last
            ? "Ir a mi Resumen"
            : current === 0
              ? "Empezar"
              : step === "ia"
                ? "Siguiente (o saltar)"
                : "Siguiente"}
          {!last && <ArrowRight aria-hidden />}
        </Button>
      </div>
    </div>
  );
}

/**
 * Configuración guiada para la primera vez que alguien entra: reloj, perfil y
 * asistente IA, reutilizando las mismas tarjetas de Ajustes. Se puede saltar
 * cualquier paso y repetir desde Ajustes → Cuenta.
 */
export default function BienvenidaPage() {
  return (
    <Suspense>
      <Wizard />
    </Suspense>
  );
}
