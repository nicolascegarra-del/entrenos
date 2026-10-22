/** Utilidades de Web Push en el navegador (suscripción del dispositivo y compatibilidad). */

export type PushSupport =
  | "ok"
  /** iPhone/iPad: solo funciona con la app añadida a la pantalla de inicio (iOS 16.4+). */
  | "ios-install"
  | "unsupported"
  /** Necesita HTTPS (o localhost). */
  | "insecure";

/** Convierte la clave VAPID pública (base64url) al formato que pide PushManager.subscribe. */
export function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

/** Qué puede hacer este navegador con las notificaciones push. */
export function pushSupport(env: {
  userAgent: string;
  secure: boolean;
  standalone: boolean;
  hasPush: boolean;
}): PushSupport {
  if (!env.secure) return "insecure";
  const ios = /iPhone|iPad|iPod/.test(env.userAgent);
  if (ios && !env.standalone) return "ios-install";
  return env.hasPush ? "ok" : "unsupported";
}

/** Entorno real del navegador para `pushSupport`. */
export function browserPushSupport(): PushSupport {
  if (typeof window === "undefined") return "unsupported";
  return pushSupport({
    userAgent: navigator.userAgent,
    secure: window.isSecureContext,
    standalone:
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true,
    hasPush:
      "serviceWorker" in navigator &&
      "PushManager" in window &&
      "Notification" in window,
  });
}

/** Nombre corto del dispositivo a partir del user agent (para la lista de dispositivos). */
export function deviceLabel(userAgent: string): string {
  const os = /Android/.test(userAgent)
    ? "Android"
    : /iPhone|iPad/.test(userAgent)
      ? "iPhone/iPad"
      : /Windows/.test(userAgent)
        ? "Windows"
        : /Mac OS/.test(userAgent)
          ? "Mac"
          : /Linux/.test(userAgent)
            ? "Linux"
            : "Dispositivo";
  const browser = /Edg\//.test(userAgent)
    ? "Edge"
    : /Firefox\//.test(userAgent)
      ? "Firefox"
      : /Chrome\//.test(userAgent)
        ? "Chrome"
        : /Safari\//.test(userAgent)
          ? "Safari"
          : "";
  return browser ? `${browser} · ${os}` : os;
}

export async function registerServiceWorker() {
  return navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

/** Suscripción push actual de este navegador (o null). */
export async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  return reg ? reg.pushManager.getSubscription() : null;
}
