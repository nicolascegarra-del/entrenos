import { useAuthStore } from "@/stores/auth";

// Vacío = mismo origen (proxy de next.config.ts). Solo se define para apuntar a otra API.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

/** Error de la API con el formato estándar Klyp. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public field?: string,
  ) {
    super(message);
  }
}

interface TokenResponse {
  access_token: string;
  expires_in: number;
}

export async function parseError(res: Response): Promise<ApiError> {
  try {
    const { error } = await res.json();
    return new ApiError(res.status, error.code, error.message, error.field);
  } catch {
    return new ApiError(
      res.status,
      "ERROR",
      "No se pudo conectar con el servidor.",
    );
  }
}

let refreshing: Promise<boolean> | null = null;

/**
 * Pide un access token nuevo usando la cookie HttpOnly de refresh.
 * Las llamadas concurrentes comparten la misma petición.
 * @returns true si se obtuvo un token nuevo.
 */
export function refreshAccessToken(): Promise<boolean> {
  refreshing ??= fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
  })
    .then(async (res) => {
      if (!res.ok) return false;
      const data: TokenResponse = await res.json();
      useAuthStore.getState().setAccessToken(data.access_token);
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

/**
 * Petición autenticada: añade el access token y, si ha caducado, lo renueva una vez
 * y reintenta. Devuelve la respuesta tal cual (sirve también para streaming).
 * @param path - Ruta relativa, ej. "/api/v1/auth/me".
 */
export async function authFetch(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<Response> {
  const token = useAuthStore.getState().accessToken;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (res.status === 401 && retry && (await refreshAccessToken())) {
    return authFetch(path, init, false);
  }
  return res;
}

/** Llama a la API (JSON) y lanza `ApiError` con el formato Klyp si falla. */
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const res = await authFetch(path, init, retry);
  if (!res.ok) throw await parseError(res);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export async function login(email: string, password: string): Promise<void> {
  const data = await apiFetch<TokenResponse>(
    "/api/v1/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) },
    false,
  );
  useAuthStore.getState().setAccessToken(data.access_token);
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/api/v1/auth/logout", { method: "POST" }, false).catch(
    () => undefined,
  );
  useAuthStore.getState().setAccessToken(null);
}

/** Crea el usuario con una invitación y deja la sesión iniciada. */
export async function registerWithInvitation(
  token: string,
  password: string,
): Promise<void> {
  const data = await apiFetch<TokenResponse>(
    "/api/v1/auth/register",
    { method: "POST", body: JSON.stringify({ token, password }) },
    false,
  );
  useAuthStore.getState().setAccessToken(data.access_token);
}

/**
 * Crea una cuenta sin invitación. La cuenta queda sin confirmar hasta abrir el enlace del email.
 * @returns El mensaje para mostrar («te hemos enviado un email…»).
 */
export async function signup(
  email: string,
  password: string,
  captchaToken: string | null,
): Promise<string> {
  const data = await apiFetch<{ status: "unverified"; message: string }>(
    "/api/v1/auth/signup",
    {
      method: "POST",
      body: JSON.stringify({ email, password, captcha_token: captchaToken }),
    },
    false,
  );
  return data.message;
}

/**
 * Confirma el email con el token del enlace.
 * @returns "active" (ya hay sesión iniciada) o "pending" (espera aprobación de un administrador).
 */
export async function verifyEmail(
  token: string,
): Promise<"active" | "pending"> {
  const data = await apiFetch<{
    status: "active" | "pending";
    access_token: string | null;
  }>(
    "/api/v1/auth/verify",
    { method: "POST", body: JSON.stringify({ token }) },
    false,
  );
  if (data.access_token)
    useAuthStore.getState().setAccessToken(data.access_token);
  return data.status;
}

/** Reenvía el email de confirmación (respuesta genérica, no revela si existe la cuenta). */
export async function resendVerification(email: string): Promise<string> {
  const data = await apiFetch<{ message: string }>(
    "/api/v1/auth/verify/resend",
    { method: "POST", body: JSON.stringify({ email }) },
    false,
  );
  return data.message;
}

/** Cambia la contraseña; la API cierra las demás sesiones y devuelve tokens nuevos. */
export async function changePassword(
  current_password: string,
  new_password: string,
): Promise<void> {
  const data = await apiFetch<TokenResponse>("/api/v1/auth/password", {
    method: "POST",
    body: JSON.stringify({ current_password, new_password }),
  });
  useAuthStore.getState().setAccessToken(data.access_token);
}
