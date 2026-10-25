import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { moduleOn, type ModuleKey, type Modules } from "@/lib/modules";
import type {
  GeoResult,
  PlannedRouteDetail,
  PlannedRoutePage,
  RoutePlan,
  ActivityReview,
  LatestReview,
  ReviewSettings,
  ImportResult,
  SourcesStatus,
  AppleImport,
  GeoPlace,
  RaceDayPlan,
  CompareResult,
  RouteDetail,
  RouteSummary,
  AchievementsReport,
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
  Gear,
  GearInput,
  InjuryReport,
  NotificationConfig,
  NotificationPrefs,
  GoalReport,
  InsightsResponse,
  PlanPreview,
  TrainingPlanInput,
  TrainingPlanReport,
  PaceCurve,
  ZonesReport,
  ManualTestInput,
  LactateTestInput,
  PerformanceTest,
  TestProtocol,
  ActivityAnalysis,
  CoachMemory,
  CoachSettings,
  PlanProposal,
  WeeklyCheckin,
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

export function useActivities(sport: string | null, q = "") {
  return useInfiniteQuery({
    queryKey: ["activities", sport, q],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: "20" });
      if (sport) params.set("sport", sport);
      if (q.trim()) params.set("q", q.trim());
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

export function useInjuryRisk() {
  return useQuery({
    queryKey: ["injury-risk"],
    queryFn: () => apiFetch<InjuryReport>("/api/v1/progress/injury-risk"),
  });
}

// ─── Material ────────────────────────────────────────────────────────────────

export function useGear() {
  return useQuery({
    queryKey: ["gear"],
    queryFn: () => apiFetch<Gear[]>("/api/v1/gear"),
  });
}

/** Alta (sin id) o edición de unas zapatillas; la API devuelve la lista completa. */
export function useSaveGear() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: GearInput }) =>
      apiFetch<Gear[]>(id ? `/api/v1/gear/${id}` : "/api/v1/gear", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["gear"], data);
      queryClient.invalidateQueries({ queryKey: ["injury-risk"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
  });
}

export function useDeleteGear() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/gear/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gear"] });
      queryClient.invalidateQueries({ queryKey: ["injury-risk"] });
    },
  });
}

export function useSetRace(activityId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (isRace: boolean) =>
      apiFetch<{ activity_id: number; is_race: boolean }>(
        `/api/v1/activities/${activityId}/race`,
        { method: "PUT", body: JSON.stringify({ is_race: isRace }) },
      ),
    onSuccess: () => {
      for (const key of [
        "activity",
        "insights",
        "training-paces",
        "zones",
        "goals",
        "goal-report",
        "race-day",
      ])
        queryClient.invalidateQueries({ queryKey: [key] });
    },
  });
}

export function useSetActivityGear(activityId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (gearId: number | null) =>
      apiFetch<{ activity_id: number; gear_id: number | null }>(
        `/api/v1/activities/${activityId}/gear`,
        { method: "PUT", body: JSON.stringify({ gear_id: gearId }) },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["activity", activityId] });
      queryClient.invalidateQueries({ queryKey: ["gear"] });
    },
  });
}

// ─── Recorridos ──────────────────────────────────────────────────────────────

export function useRoutes() {
  return useQuery({
    queryKey: ["routes"],
    queryFn: () => apiFetch<RouteSummary[]>("/api/v1/routes"),
  });
}

export function useRoute(id: number) {
  return useQuery({
    queryKey: ["routes", id],
    queryFn: () => apiFetch<RouteDetail>(`/api/v1/routes/${id}`),
    enabled: Number.isFinite(id),
  });
}

export function useActivityRoute(activityId: number, enabled = true) {
  return useQuery({
    queryKey: ["routes", "by-activity", activityId],
    queryFn: () =>
      apiFetch<RouteDetail | null>(`/api/v1/routes/by-activity/${activityId}`),
    enabled,
  });
}

export function useCompare(a: number, b: number) {
  return useQuery({
    queryKey: ["compare", a, b],
    queryFn: () =>
      apiFetch<CompareResult>(`/api/v1/routes/compare?a=${a}&b=${b}`),
    enabled: Number.isFinite(a) && Number.isFinite(b) && a !== b,
  });
}

// ─── Otros relojes ───────────────────────────────────────────────────────────

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: () => apiFetch<SourcesStatus>("/api/v1/sources"),
  });
}

/** Última importación del export de Apple Salud; se refresca sola mientras se procesa. */
export function useAppleImport() {
  return useQuery({
    queryKey: ["apple-import"],
    queryFn: () => apiFetch<AppleImport | null>("/api/v1/imports/apple-health"),
    refetchInterval: (query) =>
      ["queued", "processing"].includes(query.state.data?.status ?? "")
        ? 3000
        : false,
  });
}

export function useImportFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { filename: string; content_b64: string }) =>
      apiFetch<ImportResult>("/api/v1/imports/file", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      for (const key of ["activities", "summary", "insights", "achievements"])
        queryClient.invalidateQueries({ queryKey: [key] });
    },
  });
}

export function useConnectCoros() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { account: string; password: string }) =>
      apiFetch<SourcesStatus>("/api/v1/sources/coros", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => queryClient.setQueryData(["sources"], data),
  });
}

export function useSyncCoros() {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ queued: boolean }>("/api/v1/sources/coros/sync", {
        method: "POST",
      }),
  });
}

export function useDisconnectCoros() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<void>("/api/v1/sources/coros", { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });
}

export function useIngestToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (revoke: boolean) =>
      revoke
        ? apiFetch<void>("/api/v1/sources/health-connect/token", {
            method: "DELETE",
          }).then(() => null)
        : apiFetch<SourcesStatus & { token: string }>(
            "/api/v1/sources/health-connect/token",
            { method: "POST" },
          ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });
}

// ─── Logros ──────────────────────────────────────────────────────────────────

export function useAchievements() {
  return useQuery({
    queryKey: ["achievements"],
    queryFn: () => apiFetch<AchievementsReport>("/api/v1/achievements"),
  });
}

export function useSetWeeklyGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessions: number) =>
      apiFetch<AchievementsReport>("/api/v1/achievements/weekly-goal", {
        method: "PUT",
        body: JSON.stringify({ sessions }),
      }),
    onSuccess: (data) => queryClient.setQueryData(["achievements"], data),
  });
}

// ─── Análisis de entrenos ────────────────────────────────────────────────────

export function useActivityReview(activityId: number) {
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["review", activityId],
    enabled: on,
    queryFn: () =>
      apiFetch<ActivityReview | null>(
        `/api/v1/activities/${activityId}/review`,
      ),
    // Mientras la IA escribe, se consulta cada 4 s hasta que esté listo.
    refetchInterval: (query) =>
      query.state.data?.status === "pending" ? 4000 : false,
  });
}

export function useRequestReview(activityId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<ActivityReview>(`/api/v1/activities/${activityId}/review`, {
        method: "POST",
      }),
    onSuccess: (data) => queryClient.setQueryData(["review", activityId], data),
  });
}

export function useLatestReview() {
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["review", "latest"],
    enabled: on,
    queryFn: () => apiFetch<LatestReview | null>("/api/v1/ai/reviews/latest"),
  });
}

export function useReviewSettings() {
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["review-settings"],
    enabled: on,
    queryFn: () => apiFetch<ReviewSettings>("/api/v1/ai/review-settings"),
  });
}

export function useSaveReviewSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      body: Pick<ReviewSettings, "enabled" | "sports" | "daily_max">,
    ) =>
      apiFetch<ReviewSettings>("/api/v1/ai/review-settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => queryClient.setQueryData(["review-settings"], data),
  });
}

// ─── Notificaciones ──────────────────────────────────────────────────────────

export function useNotifications() {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiFetch<NotificationConfig>("/api/v1/notifications"),
  });
}

function useNotificationsMutation<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: T) =>
      apiFetch<NotificationConfig>(`/api/v1/notifications${path}`, {
        method,
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => queryClient.setQueryData(["notifications"], data),
  });
}

export const useSaveNotificationPrefs = () =>
  useNotificationsMutation<NotificationPrefs>("/prefs", "PUT");

export const useSubscribePush = () =>
  useNotificationsMutation<{
    endpoint: string;
    keys: { p256dh: string; auth: string };
    user_agent: string;
    timezone: string;
  }>("/subscriptions", "POST");

export const useUnsubscribePush = () =>
  useNotificationsMutation<{ endpoint: string }>(
    "/subscriptions/remove",
    "POST",
  );

export function useRemovePushDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/notifications/devices/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useTestPush() {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ sent: number; failed: number }>("/api/v1/notifications/test", {
        method: "POST",
      }),
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
      await queryClient.invalidateQueries({ queryKey: ["race-day"] });
    },
  });
}

export function useRaceDay(id: number) {
  return useQuery({
    queryKey: ["race-day", id],
    queryFn: () => apiFetch<RaceDayPlan>(`/api/v1/goals/${id}/race-day`),
  });
}

export function useGeocode() {
  return useMutation({
    mutationFn: (q: string) =>
      apiFetch<GeoPlace[]>(`/api/v1/goals/geocode?q=${encodeURIComponent(q)}`),
  });
}

/** Subir (texto del .gpx) o quitar (null) el recorrido de la carrera. */
export function useGoalCourse(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      body: { gpx: string; name: string } | null,
    ): Promise<RaceGoal | void> =>
      body
        ? apiFetch<RaceGoal>(`/api/v1/goals/${id}/course`, {
            method: "PUT",
            body: JSON.stringify(body),
          })
        : apiFetch<void>(`/api/v1/goals/${id}/course`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["race-day", id] });
      queryClient.invalidateQueries({ queryKey: ["goal-report", id] });
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
      // app-modules: si el administrador se cambia sus propios módulos, se ve al momento.
      for (const key of [
        "admin-users",
        "admin-system",
        "admin-audit",
        "app-modules",
      ]) {
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

// ─── Módulos de la app ───────────────────────────────────────────────────────

/** Módulos activos para tu cuenta (los decide el administrador). Se refrescan cada minuto como mucho. */
export function useModules() {
  return useQuery({
    queryKey: ["app-modules"],
    staleTime: 60_000,
    queryFn: () => apiFetch<Modules>("/api/v1/app/modules"),
  });
}

/** ¿Está activo el módulo? Mientras carga, como estaba (sin parpadeos). */
export function useModuleOn(key: ModuleKey): boolean {
  const { data } = useModules();
  return moduleOn(data, key);
}

/** Valor general de los módulos (Admin → Módulos), sin lo fijado para tu cuenta. */
export function useAdminModules() {
  return useQuery({
    queryKey: ["admin-modules"],
    queryFn: () => apiFetch<Modules>("/api/v1/admin/modules"),
  });
}

export function useSaveModules() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Modules>) =>
      apiFetch<Modules>("/api/v1/admin/modules", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: async (data) => {
      queryClient.setQueryData(["admin-modules"], data);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["app-modules"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-audit"] }),
      ]);
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
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["ai-providers"],
    enabled: on,
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
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["conversations"],
    enabled: on,
    queryFn: () => apiFetch<ConversationBrief[]>("/api/v1/chat/conversations"),
  });
}

export function useConversation(id: number | null) {
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["conversation", id],
    enabled: id != null && on,
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

// ─── Planes de entrenamiento automáticos ────────────────────────────────────

export function useActivePlan() {
  return useQuery({
    queryKey: ["training-plan"],
    queryFn: () =>
      apiFetch<TrainingPlanReport | null>("/api/v1/training-plans/active"),
  });
}

export function usePlanPreview() {
  return useMutation({
    mutationFn: (body: TrainingPlanInput) =>
      apiFetch<PlanPreview>("/api/v1/training-plans/preview", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

/** Tras crear, adaptar o cancelar un plan cambian el calendario y el Resumen. */
async function refreshPlanViews(
  queryClient: ReturnType<typeof useQueryClient>,
) {
  for (const key of ["training-plan", "plans", "summary"]) {
    await queryClient.invalidateQueries({ queryKey: [key] });
  }
}

export function useCreatePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TrainingPlanInput) =>
      apiFetch<TrainingPlanReport>("/api/v1/training-plans", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => refreshPlanViews(queryClient),
  });
}

export function useAdaptPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<{
        adjustment: { action: string; reason: string } | null;
        plan: TrainingPlanReport;
      }>(`/api/v1/training-plans/${id}/adapt`, { method: "POST" }),
    onSuccess: () => refreshPlanViews(queryClient),
  });
}

export function useCancelPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/training-plans/${id}`, { method: "DELETE" }),
    onSuccess: () => refreshPlanViews(queryClient),
  });
}

// ─── Tests de rendimiento ────────────────────────────────────────────────────

/** Lo que cambia al confirmar o borrar un test: zonas, ritmos e indicadores que usan el umbral. */
const TEST_KEYS = [
  "tests",
  "activity-test",
  "zones",
  "training-paces",
  "summary",
  "insights",
];

function useInvalidateTests() {
  const queryClient = useQueryClient();
  return () => {
    for (const key of TEST_KEYS)
      queryClient.invalidateQueries({ queryKey: [key] });
  };
}

export function useTestProtocols() {
  return useQuery({
    queryKey: ["test-protocols"],
    queryFn: () => apiFetch<TestProtocol[]>("/api/v1/tests/protocols"),
    staleTime: 60 * 60_000,
  });
}

export function useTests() {
  return useQuery({
    queryKey: ["tests"],
    queryFn: () => apiFetch<PerformanceTest[]>("/api/v1/tests"),
  });
}

export function useActivityTest(activityId: number) {
  return useQuery({
    queryKey: ["activity-test", activityId],
    queryFn: () =>
      apiFetch<PerformanceTest | null>(`/api/v1/activities/${activityId}/test`),
  });
}

export function useMarkTest(activityId: number) {
  const invalidate = useInvalidateTests();
  return useMutation({
    mutationFn: (protocol: string) =>
      apiFetch<PerformanceTest>(`/api/v1/activities/${activityId}/test`, {
        method: "POST",
        body: JSON.stringify({ protocol }),
      }),
    onSuccess: invalidate,
  });
}

export function useConfirmTest() {
  const invalidate = useInvalidateTests();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<PerformanceTest>(`/api/v1/tests/${id}/confirm`, {
        method: "POST",
      }),
    onSuccess: invalidate,
  });
}

export function useDeleteTest() {
  const invalidate = useInvalidateTests();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/tests/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useCreateManualTest() {
  const invalidate = useInvalidateTests();
  return useMutation({
    mutationFn: (body: ManualTestInput) =>
      apiFetch<PerformanceTest>("/api/v1/tests", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });
}

export function useCreateLactateTest() {
  const invalidate = useInvalidateTests();
  return useMutation({
    mutationFn: (body: LactateTestInput) =>
      apiFetch<PerformanceTest>("/api/v1/tests/lactate", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });
}

export function useTestPrefs() {
  return useQuery({
    queryKey: ["test-prefs"],
    queryFn: () =>
      apiFetch<{ lactate_tests: boolean }>("/api/v1/tests/preferences"),
  });
}

export function useSaveTestPrefs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { lactate_tests: boolean }) =>
      apiFetch<{ lactate_tests: boolean }>("/api/v1/tests/preferences", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => queryClient.setQueryData(["test-prefs"], data),
  });
}

// ─── Enviar entrenos al reloj ────────────────────────────────────────────────

export interface WorkoutSettings {
  auto: boolean;
  garmin_connected: boolean;
  coros_connected: boolean;
  days: number;
}

export function useWorkoutSettings() {
  const on = useModuleOn("reloj");
  return useQuery({
    queryKey: ["workout-settings"],
    enabled: on,
    queryFn: () => apiFetch<WorkoutSettings>("/api/v1/workouts/settings"),
  });
}

export function useSaveWorkoutSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (auto: boolean) =>
      apiFetch<WorkoutSettings>("/api/v1/workouts/settings", {
        method: "PUT",
        body: JSON.stringify({ auto }),
      }),
    onSuccess: (data) => queryClient.setQueryData(["workout-settings"], data),
  });
}

/** Enviar (o quitar) una sesión de Garmin Connect. */
export function useGarminWorkout(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (remove: boolean) =>
      apiFetch<{ garmin_status: string; garmin_error: string }>(
        `/api/v1/plans/${planId}/garmin`,
        { method: remove ? "DELETE" : "POST" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plan", planId] });
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
}

export function useSendUpcoming() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ sent: number; unchanged: number; error: number }>(
        "/api/v1/workouts/send-upcoming",
        { method: "POST" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plans"] });
      queryClient.invalidateQueries({ queryKey: ["plan"] });
    },
  });
}

/** Enviar (o actualizar) una sesión en el calendario de COROS. */
export function useCorosWorkout(planId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ coros_status: string; coros_error: string }>(
        `/api/v1/plans/${planId}/coros`,
        { method: "POST" },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plan", planId] });
      queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
}

export function useSyncCorosOfficial() {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ queued: boolean }>("/api/v1/sources/coros-official/sync", {
        method: "POST",
      }),
  });
}

export function useActivityAnalysis(activityId: number) {
  return useQuery({
    queryKey: ["activity-analysis", activityId],
    queryFn: () =>
      apiFetch<ActivityAnalysis>(`/api/v1/activities/${activityId}/analysis`),
  });
}

/** Borrar una o varias actividades (no vuelven con la sincronización). */
export function useDeleteActivities() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) =>
      apiFetch<{ deleted: number }>("/api/v1/activities/delete", {
        method: "POST",
        body: JSON.stringify({ ids }),
      }),
    onSuccess: () => {
      for (const key of [
        "activities",
        "summary",
        "insights",
        "achievements",
        "plans",
        "zones",
        "fitness",
      ])
        queryClient.invalidateQueries({ queryKey: [key] });
    },
  });
}

// ─── Entrenador IA ───────────────────────────────────────────────────────────

export function useCoachSettings() {
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["coach-settings"],
    enabled: on,
    queryFn: () => apiFetch<CoachSettings>("/api/v1/coach/settings"),
  });
}

export function useSaveCoachSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { health_consent?: boolean; weekly_review?: boolean }) =>
      apiFetch<CoachSettings>("/api/v1/coach/settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["coach-settings"], data);
      queryClient.invalidateQueries({ queryKey: ["coach-memories"] });
    },
  });
}

export function useCoachMemories() {
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["coach-memories"],
    enabled: on,
    queryFn: () => apiFetch<CoachMemory[]>("/api/v1/coach/memories"),
  });
}

/** Añadir (sin id), corregir (con id) o borrar (remove) un dato de la ficha. */
export function useSaveCoachMemory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (m: {
      id?: number;
      category?: string;
      content?: string;
      remove?: boolean;
    }): Promise<void> => {
      if (m.remove) {
        await apiFetch<void>(`/api/v1/coach/memories/${m.id}`, {
          method: "DELETE",
        });
        return;
      }
      await apiFetch<CoachMemory>(
        m.id ? `/api/v1/coach/memories/${m.id}` : "/api/v1/coach/memories",
        {
          method: m.id ? "PUT" : "POST",
          body: JSON.stringify({ category: m.category, content: m.content }),
        },
      );
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["coach-memories"] }),
  });
}

export function useCheckin() {
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["coach-checkin"],
    enabled: on,
    queryFn: () => apiFetch<WeeklyCheckin | null>("/api/v1/coach/checkin"),
    refetchInterval: (query) =>
      query.state.data?.status === "processing" ? 2500 : false,
  });
}

export function useOpenCheckin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<WeeklyCheckin>("/api/v1/coach/checkin", { method: "POST" }),
    onSuccess: (data) => queryClient.setQueryData(["coach-checkin"], data),
  });
}

export function useAnswerCheckin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; answers: Record<string, number | string> }) =>
      apiFetch<WeeklyCheckin>(`/api/v1/coach/checkin/${v.id}/answers`, {
        method: "POST",
        body: JSON.stringify(v.answers),
      }),
    onSuccess: (data) => queryClient.setQueryData(["coach-checkin"], data),
  });
}

export function useProposals() {
  const on = useModuleOn("ia");
  return useQuery({
    queryKey: ["coach-proposals"],
    enabled: on,
    queryFn: () => apiFetch<PlanProposal[]>("/api/v1/coach/proposals"),
  });
}

/** ¿El entrenador tiene algo pendiente (revisión semanal o propuesta)? Para el punto de aviso del menú. */
export function useCoachBadge(): boolean {
  const ia = useModuleOn("ia");
  const { data: ai } = useAiProviders();
  const hasAi = !!ai?.providers.some((p) => p.configured && p.enabled);
  const { data: checkin } = useCheckin();
  const { data: proposals } = useProposals();
  return ia && hasAi && (checkin?.status === "pending" || !!proposals?.length);
}

export function useDecideProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; accept: boolean }) =>
      apiFetch<PlanProposal>(
        `/api/v1/coach/proposals/${v.id}/${v.accept ? "accept" : "reject"}`,
        { method: "POST" },
      ),
    onSuccess: () => {
      for (const key of ["coach-proposals", "plans", "plan"])
        queryClient.invalidateQueries({ queryKey: [key] });
    },
  });
}

// ─── Rutas planificadas ──────────────────────────────────────────────────────

export interface RoutePointsInput {
  mode: string;
  points: { lat: number; lon: number }[];
}

/** Calcular una ruta sin guardarla (el editor la recalcula al mover los puntos). */
export function usePlanRoute() {
  return useMutation({
    mutationFn: (body: RoutePointsInput) =>
      apiFetch<RoutePlan>("/api/v1/planned-routes/plan", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function usePlannedRoutes() {
  const on = useModuleOn("rutas");
  return useQuery({
    queryKey: ["planned-routes"],
    enabled: on,
    queryFn: () =>
      apiFetch<PlannedRoutePage>("/api/v1/planned-routes?limit=100"),
  });
}

export function usePlannedRoute(id: number | null) {
  const on = useModuleOn("rutas");
  return useQuery({
    queryKey: ["planned-route", id],
    enabled: id != null && on,
    queryFn: () => apiFetch<PlannedRouteDetail>(`/api/v1/planned-routes/${id}`),
  });
}

export function useSaveRoute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: RoutePointsInput & { id?: number; name: string }) =>
      apiFetch<PlannedRouteDetail>(
        id ? `/api/v1/planned-routes/${id}` : "/api/v1/planned-routes",
        { method: id ? "PUT" : "POST", body: JSON.stringify(body) },
      ),
    onSuccess: (route) => {
      queryClient.setQueryData(["planned-route", route.id], route);
      void queryClient.invalidateQueries({ queryKey: ["planned-routes"] });
    },
  });
}

export function useDeleteRoute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/planned-routes/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["planned-routes"] });
      void queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
}

/** Asociar (o quitar) la ruta de una sesión del plan. */
export function useSetSessionRoute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      planId,
      routeId,
    }: {
      planId: number;
      routeId: number | null;
    }) =>
      apiFetch<{ planned_route_id: number | null }>(
        `/api/v1/plans/${planId}/route`,
        {
          method: "PUT",
          body: JSON.stringify({ planned_route_id: routeId }),
        },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["plans"] });
      void queryClient.invalidateQueries({ queryKey: ["plan"] });
      void queryClient.invalidateQueries({ queryKey: ["planned-route"] });
    },
  });
}

export function geocodePlace(q: string) {
  return apiFetch<GeoResult[]>(
    `/api/v1/planned-routes/geocode?q=${encodeURIComponent(q)}`,
  );
}

/** Valorar una respuesta del entrenador (1 útil, -1 no útil, 0 quitar). */
export function useMessageFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, value }: { id: number; value: -1 | 0 | 1 }) =>
      apiFetch<{ feedback: number | null }>(
        `/api/v1/chat/messages/${id}/feedback`,
        {
          method: "PUT",
          body: JSON.stringify({ value }),
        },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["conversation"] }),
  });
}
