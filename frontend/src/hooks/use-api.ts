import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  AdminSettings,
  AdminSettingsInput,
  EmailSettings,
  EmailSettingsInput,
  AuditRow,
  AuthOptions,
  InvitationCreated,
  SystemStatus,
  UsersPage,
  AiProviderId,
  AiProviderInput,
  AiProviders,
  ConnectState,
  Conversation,
  ConversationBrief,
  InvitationRow,
  Me,
  Profile,
  ProfileInput,
  ActivityDetail,
  ActivityFeedback,
  ActivityPage,
  ActivitySummary,
  DeviceSpan,
  EfficiencyPoint,
  FitnessResponse,
  GarminStatus,
  GoalReport,
  InsightsResponse,
  PaceCurve,
  ZonesReport,
  MetricDefinition,
  PlannedSession,
  PlannedSessionDetail,
  PlannedSessionInput,
  RaceGoal,
  RaceGoalInput,
  RecordRead,
  SeriesPoint,
  Streams,
  Summary,
  SyncMode,
  SyncSettings,
  TrainingPaces,
  WeekPoint,
} from "@/types/api";

export function useActivities(sport: string | null) {
  return useInfiniteQuery({
    queryKey: ["activities", sport],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: "20" });
      if (sport) params.set("sport", sport);
      if (pageParam) params.set("cursor", pageParam);
      return apiFetch<ActivityPage>(`/api/v1/activities?${params}`);
    },
    getNextPageParam: (last) => last.next_cursor,
  });
}

export function useSports() {
  return useQuery({
    queryKey: ["sports"],
    queryFn: () => apiFetch<string[]>("/api/v1/activities/sports"),
  });
}

export function useActivity(id: number) {
  return useQuery({
    queryKey: ["activity", id],
    queryFn: () => apiFetch<ActivityDetail>(`/api/v1/activities/${id}`),
  });
}

export function useStreams(id: number, channels: string[], enabled: boolean) {
  return useQuery({
    queryKey: ["streams", id, channels],
    enabled,
    staleTime: Infinity, // las series de una actividad no cambian
    queryFn: () =>
      apiFetch<Streams>(
        `/api/v1/activities/${id}/streams?channels=${channels.join(",")}&max_points=800`,
      ),
  });
}

export function useCatalog() {
  return useQuery({
    queryKey: ["catalog"],
    staleTime: Infinity,
    queryFn: () => apiFetch<MetricDefinition[]>("/api/v1/metrics/catalog"),
  });
}

export function useGarminStatus() {
  return useQuery({
    queryKey: ["garmin-status"],
    queryFn: () => apiFetch<GarminStatus>("/api/v1/garmin/status"),
    // Mientras sincroniza, refresca cada 3 s para mostrar el resultado en cuanto acabe.
    refetchInterval: (query) =>
      query.state.data?.last_run?.status === "running" ? 3000 : false,
  });
}

export function useSyncNow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ queued: boolean }>("/api/v1/garmin/sync", { method: "POST" }),
    onSuccess: async () => {
      // La tarea tarda un instante en crear su SyncRun: espera un poco antes de consultar.
      await new Promise((r) => setTimeout(r, 1500));
      await queryClient.invalidateQueries({ queryKey: ["garmin-status"] });
      await queryClient.invalidateQueries({ queryKey: ["activities"] });
      // La próxima sincronización automática cuenta desde esta.
      await queryClient.invalidateQueries({ queryKey: ["sync-settings"] });
    },
  });
}

// ─── Plan ──────────────────────────────────────────────────────────────────

export function usePlans(dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ["plans", dateFrom, dateTo],
    queryFn: () =>
      apiFetch<PlannedSession[]>(
        `/api/v1/plans?date_from=${dateFrom}&date_to=${dateTo}`,
      ),
  });
}

export function useActivitiesInRange(dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ["activities-range", dateFrom, dateTo],
    queryFn: () => {
      // Límite de fechas en hora local del navegador, convertido a UTC para la API.
      const from = new Date(`${dateFrom}T00:00:00`).toISOString();
      const to = new Date(`${dateTo}T23:59:59`).toISOString();
      return apiFetch<ActivityPage>(
        `/api/v1/activities?limit=100&date_from=${from}&date_to=${to}`,
      );
    },
  });
}

export function usePlan(id: number) {
  return useQuery({
    queryKey: ["plan", id],
    queryFn: () => apiFetch<PlannedSessionDetail>(`/api/v1/plans/${id}`),
  });
}

export function usePlanCandidates(id: number, enabled: boolean) {
  return useQuery({
    queryKey: ["plan-candidates", id],
    enabled,
    queryFn: () =>
      apiFetch<ActivitySummary[]>(`/api/v1/plans/${id}/candidates`),
  });
}

function useInvalidatePlans() {
  const queryClient = useQueryClient();
  return (detail?: PlannedSessionDetail) => {
    if (detail) queryClient.setQueryData(["plan", detail.id], detail);
    return queryClient.invalidateQueries({ queryKey: ["plans"] });
  };
}

export function useSavePlan(id?: number) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: (body: PlannedSessionInput) =>
      apiFetch<PlannedSessionDetail>(
        id ? `/api/v1/plans/${id}` : "/api/v1/plans",
        {
          method: id ? "PUT" : "POST",
          body: JSON.stringify(body),
        },
      ),
    onSuccess: invalidate,
  });
}

export function useDeletePlan() {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/plans/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidate(),
  });
}

export function useSetMatch(id: number) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: (body: {
      mode: "auto" | "manual";
      activity_id?: number | null;
    }) =>
      apiFetch<PlannedSessionDetail>(`/api/v1/plans/${id}/match`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });
}

// ─── Progresión ──────────────────────────────────────────────────────────────

export function useFitness(days: number) {
  return useQuery({
    queryKey: ["fitness", days],
    queryFn: () =>
      apiFetch<FitnessResponse>(`/api/v1/progress/fitness?days=${days}`),
  });
}

export function useWeekly(weeks: number) {
  return useQuery({
    queryKey: ["weekly", weeks],
    queryFn: () =>
      apiFetch<WeekPoint[]>(`/api/v1/progress/weekly?weeks=${weeks}`),
  });
}

export function useMetricSeries(key: string, days: number) {
  return useQuery({
    queryKey: ["metric-series", key, days],
    queryFn: () =>
      apiFetch<SeriesPoint[]>(`/api/v1/progress/metric/${key}?days=${days}`),
  });
}

export function useEfficiency(days: number) {
  return useQuery({
    queryKey: ["efficiency", days],
    queryFn: () =>
      apiFetch<EfficiencyPoint[]>(`/api/v1/progress/efficiency?days=${days}`),
  });
}

export function useRecords() {
  return useQuery({
    queryKey: ["records"],
    queryFn: () => apiFetch<RecordRead[]>("/api/v1/progress/records"),
  });
}

export function useDevices() {
  return useQuery({
    queryKey: ["devices"],
    staleTime: Infinity,
    queryFn: () => apiFetch<DeviceSpan[]>("/api/v1/devices"),
  });
}

export function useSummary() {
  return useQuery({
    queryKey: ["summary"],
    queryFn: () => apiFetch<Summary>("/api/v1/summary"),
  });
}

// ─── Ajustes ─────────────────────────────────────────────────────────────────

export function useSyncSettings() {
  return useQuery({
    queryKey: ["sync-settings"],
    queryFn: () => apiFetch<SyncSettings>("/api/v1/settings/sync"),
  });
}

export function useSaveSyncSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { mode: SyncMode; interval_min: number }) =>
      apiFetch<SyncSettings>("/api/v1/settings/sync", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => queryClient.setQueryData(["sync-settings"], data),
  });
}

export function usePaceCurve(days: number) {
  return useQuery({
    queryKey: ["pace-curve", days],
    queryFn: () =>
      apiFetch<PaceCurve>(`/api/v1/progress/pace-curve?days=${days}`),
  });
}

export function useZones() {
  return useQuery({
    queryKey: ["zones"],
    queryFn: () => apiFetch<ZonesReport>("/api/v1/progress/zones"),
  });
}

export function useInsights(days: number) {
  return useQuery({
    queryKey: ["insights", days],
    queryFn: () =>
      apiFetch<InsightsResponse>(`/api/v1/progress/insights?days=${days}`),
  });
}

// ─── Sensaciones ─────────────────────────────────────────────────────────────

export function useFeedback(activityId: number) {
  return useQuery({
    queryKey: ["feedback", activityId],
    queryFn: () =>
      apiFetch<ActivityFeedback>(`/api/v1/activities/${activityId}/feedback`),
  });
}

export function useSaveFeedback(activityId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      rpe: number | null;
      feeling: number | null;
      notes: string;
    }) =>
      apiFetch<ActivityFeedback>(`/api/v1/activities/${activityId}/feedback`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: async (data) => {
      queryClient.setQueryData(["feedback", activityId], data);
      // El RPE cambia la carga de sesiones sin FC: refresca resumen y progresión.
      await queryClient.invalidateQueries({ queryKey: ["summary"] });
      await queryClient.invalidateQueries({ queryKey: ["fitness"] });
      await queryClient.invalidateQueries({ queryKey: ["insights"] });
    },
  });
}

// ─── Objetivos ───────────────────────────────────────────────────────────────

export function useGoals() {
  return useQuery({
    queryKey: ["goals"],
    queryFn: () => apiFetch<RaceGoal[]>("/api/v1/goals"),
  });
}

export function useGoalReport(id: number) {
  return useQuery({
    queryKey: ["goal-report", id],
    queryFn: () => apiFetch<GoalReport>(`/api/v1/goals/${id}/report`),
  });
}

export function useSaveGoal(id?: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RaceGoalInput) =>
      apiFetch<RaceGoal>(id ? `/api/v1/goals/${id}` : "/api/v1/goals", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["goals"] });
      await queryClient.invalidateQueries({ queryKey: ["goal-report"] });
    },
  });
}

export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/goals/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["goals"] }),
  });
}

export function useGoalCandidates(id: number, enabled: boolean) {
  return useQuery({
    queryKey: ["goal-candidates", id],
    enabled,
    queryFn: () =>
      apiFetch<
        {
          id: number;
          name: string;
          start_time: string;
          distance_m: number;
          duration_s: number;
        }[]
      >(`/api/v1/goals/${id}/candidates`),
  });
}

export function useGoalResult(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (activityId: number | null): Promise<unknown> =>
      activityId == null
        ? apiFetch<void>(`/api/v1/goals/${id}/result`, { method: "DELETE" })
        : apiFetch<RaceGoal>(`/api/v1/goals/${id}/result`, {
            method: "PUT",
            body: JSON.stringify({ activity_id: activityId }),
          }),
    onSuccess: async () => {
      // La calibración afecta a todos los objetivos y a las predicciones de Progresión.
      await queryClient.invalidateQueries({ queryKey: ["goals"] });
      await queryClient.invalidateQueries({ queryKey: ["goal-report"] });
      await queryClient.invalidateQueries({ queryKey: ["insights"] });
    },
  });
}

export function useTrainingPaces() {
  return useQuery({
    queryKey: ["training-paces"],
    staleTime: 10 * 60_000,
    queryFn: () => apiFetch<TrainingPaces>("/api/v1/training-paces"),
  });
}

// ─── Perfil y cuenta ─────────────────────────────────────────────────────────

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    staleTime: Infinity,
    queryFn: () => apiFetch<Me>("/api/v1/auth/me"),
  });
}

/** Marca la configuración guiada como hecha (u omitida) y actualiza `me` sin recargar. */
export function useFinishOnboarding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<void>("/api/v1/auth/me/onboarding", {
        method: "PUT",
        body: JSON.stringify({ done: true }),
      }),
    onSuccess: () =>
      queryClient.setQueryData<Me>(["me"], (old) =>
        old ? { ...old, onboarded: true } : old,
      ),
  });
}

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: () => apiFetch<Profile>("/api/v1/profile"),
  });
}

export function useSaveProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfileInput) =>
      apiFetch<Profile>("/api/v1/profile", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: async (data) => {
      queryClient.setQueryData(["profile"], data);
      // La edad y el sexo cambian percentiles, FC máx., ajuste por edad y previsiones.
      for (const key of ["insights", "records", "goal-report", "fitness"]) {
        await queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

// ─── Conexión con Garmin ─────────────────────────────────────────────────────

export function useStartGarminConnect() {
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      apiFetch<{ connect_id: string }>("/api/v1/garmin/connect", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useConnectState(connectId: string | null) {
  return useQuery({
    queryKey: ["garmin-connect", connectId],
    enabled: !!connectId,
    queryFn: () =>
      apiFetch<ConnectState>(`/api/v1/garmin/connect/${connectId}`),
    // Consulta cada 2 s mientras el worker hace el login.
    refetchInterval: (query) =>
      ["connected", "error", "needs_mfa"].includes(
        query.state.data?.status ?? "",
      )
        ? false
        : 2000,
  });
}

export function useSendMfaCode(connectId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      apiFetch<ConnectState>(`/api/v1/garmin/connect/${connectId}/mfa`, {
        method: "POST",
        body: JSON.stringify({ code }),
      }),
    onSuccess: (data) =>
      queryClient.setQueryData(["garmin-connect", connectId], data),
  });
}

export function useDisconnectGarmin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<void>("/api/v1/garmin/connection", { method: "DELETE" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["garmin-status"] }),
  });
}

// ─── Administración ──────────────────────────────────────────────────────────

export function useAdminUsers(q: string) {
  return useQuery({
    queryKey: ["admin-users", q],
    queryFn: () =>
      apiFetch<UsersPage>(
        `/api/v1/admin/users?limit=200${q ? `&q=${encodeURIComponent(q)}` : ""}`,
      ),
  });
}

/** Acción sobre un usuario; refresca la lista y el estado del sistema. */
export function useAdminUserAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      path,
      method = "POST",
      body,
    }: {
      path: string;
      method?: string;
      body?: unknown;
    }) =>
      apiFetch<unknown>(`/api/v1/admin/users/${path}`, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    onSuccess: async () => {
      for (const key of ["admin-users", "admin-system", "admin-audit"]) {
        await queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useAdminInvitations() {
  return useQuery({
    queryKey: ["admin-invitations"],
    queryFn: () => apiFetch<InvitationRow[]>("/api/v1/admin/invitations"),
  });
}

export function useInvitationAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      path = "",
      method = "POST",
      body,
    }: {
      path?: string;
      method?: string;
      body?: unknown;
    }) =>
      apiFetch<InvitationCreated | undefined>(
        `/api/v1/admin/invitations${path}`,
        {
          method,
          body: body === undefined ? undefined : JSON.stringify(body),
        },
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin-invitations"] });
      await queryClient.invalidateQueries({ queryKey: ["admin-audit"] });
    },
  });
}

export function useAdminSettings() {
  return useQuery({
    queryKey: ["admin-settings"],
    queryFn: () => apiFetch<AdminSettings>("/api/v1/admin/settings"),
  });
}

export function useSaveAdminSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AdminSettingsInput) =>
      apiFetch<AdminSettings>("/api/v1/admin/settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: async (data) => {
      queryClient.setQueryData(["admin-settings"], data);
      await queryClient.invalidateQueries({ queryKey: ["admin-audit"] });
    },
  });
}

export function useAdminAudit() {
  return useQuery({
    queryKey: ["admin-audit"],
    queryFn: () => apiFetch<AuditRow[]>("/api/v1/admin/audit?limit=100"),
  });
}

export function useAdminSystem() {
  return useQuery({
    queryKey: ["admin-system"],
    refetchInterval: 60_000,
    queryFn: () => apiFetch<SystemStatus>("/api/v1/admin/system"),
  });
}

export function useEmailSettings() {
  return useQuery({
    queryKey: ["admin-email"],
    queryFn: () => apiFetch<EmailSettings>("/api/v1/admin/email"),
  });
}

export function useSaveEmailSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: EmailSettingsInput) =>
      apiFetch<EmailSettings>("/api/v1/admin/email", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: async (data) => {
      queryClient.setQueryData(["admin-email"], data);
      // El correo cambia qué se puede hacer: registro sin invitación, recuperar contraseña…
      for (const key of [
        "admin-settings",
        "admin-system",
        "auth-options",
        "admin-audit",
      ]) {
        await queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useTestEmail() {
  return useMutation({
    mutationFn: (to: string | null) =>
      apiFetch<{ ok: boolean; message: string }>("/api/v1/admin/email/test", {
        method: "POST",
        body: JSON.stringify({ to }),
      }),
  });
}

/** Opciones públicas del login (modo de registro y si hay correo). */
export function useAuthOptions() {
  return useQuery({
    queryKey: ["auth-options"],
    staleTime: 5 * 60_000,
    queryFn: () => apiFetch<AuthOptions>("/api/v1/auth/options", {}, false),
  });
}

// ─── Asistente IA ────────────────────────────────────────────────────────────

export function useAiProviders() {
  return useQuery({
    queryKey: ["ai-providers"],
    queryFn: () => apiFetch<AiProviders>("/api/v1/ai/providers"),
  });
}

export function useSaveAiProvider(provider: AiProviderId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AiProviderInput) =>
      apiFetch<AiProviders>(`/api/v1/ai/providers/${provider}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => queryClient.setQueryData(["ai-providers"], data),
  });
}

export function useDeleteAiProvider(provider: AiProviderId) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<void>(`/api/v1/ai/providers/${provider}`, { method: "DELETE" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["ai-providers"] }),
  });
}

export function useAiModels(provider: AiProviderId) {
  return useMutation({
    mutationFn: (apiKey: string | null) =>
      apiFetch<{ models: string[]; recommended: string[] }>(
        `/api/v1/ai/providers/${provider}/models`,
        { method: "POST", body: JSON.stringify({ api_key: apiKey }) },
      ),
  });
}

export function useTestAiProvider(provider: AiProviderId) {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean; model: string; models: string[] }>(
        `/api/v1/ai/providers/${provider}/test`,
        { method: "POST" },
      ),
  });
}

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => apiFetch<ConversationBrief[]>("/api/v1/chat/conversations"),
  });
}

export function useConversation(id: number | null) {
  return useQuery({
    queryKey: ["conversation", id],
    enabled: id != null,
    queryFn: () => apiFetch<Conversation>(`/api/v1/chat/conversations/${id}`),
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/chat/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["conversations"] }),
  });
}
