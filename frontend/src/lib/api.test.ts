import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, login } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("apiFetch", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    useAuthStore.setState({ accessToken: null });
  });
  afterEach(() => {
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("cuando login correcto entonces guarda el token solo en memoria", async () => {
    fetchMock.mockResolvedValueOnce(
      json(200, { access_token: "tok", expires_in: 900 }),
    );
    await login("a@b.com", "x");
    expect(useAuthStore.getState().accessToken).toBe("tok");
  });

  it("cuando hay token entonces envía cabecera Bearer y cookies", async () => {
    useAuthStore.setState({ accessToken: "tok" });
    fetchMock.mockResolvedValueOnce(json(200, { id: 1 }));
    await apiFetch("/api/v1/auth/me");
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok");
    expect(init.credentials).toBe("include");
  });

  it("cuando access caduca entonces renueva una vez y reintenta", async () => {
    useAuthStore.setState({ accessToken: "viejo" });
    fetchMock
      .mockResolvedValueOnce(
        json(401, { error: { code: "UNAUTHORIZED", message: "x" } }),
      )
      .mockResolvedValueOnce(
        json(200, { access_token: "nuevo", expires_in: 900 }),
      )
      .mockResolvedValueOnce(json(200, { id: 1 }));
    await expect(apiFetch("/api/v1/auth/me")).resolves.toEqual({ id: 1 });
    expect(useAuthStore.getState().accessToken).toBe("nuevo");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("cuando refresh falla entonces lanza ApiError con el formato Klyp", async () => {
    fetchMock
      .mockResolvedValueOnce(
        json(401, {
          error: { code: "UNAUTHORIZED", message: "No autenticado." },
        }),
      )
      .mockResolvedValueOnce(
        json(401, {
          error: { code: "UNAUTHORIZED", message: "Sesión caducada." },
        }),
      );
    const err = (await apiFetch("/api/v1/auth/me").catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("UNAUTHORIZED");
    expect(err.message).toBe("No autenticado.");
  });
});
