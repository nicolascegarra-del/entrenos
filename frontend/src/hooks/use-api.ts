import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  ConnectState,
  InvitationRow,
  Me,
  Profile,
  ProfileInput,
  UserRow,
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

// ─── Usuarios e invitaciones (administrador) ─────────────────────────────────

export function useUsers(enabled: boolean) {
  return useQuery({
    queryKey: ["users"],
    enabled,
    queryFn: () => apiFetch<UserRow[]>("/api/v1/users"),
  });
}

export function useInvitations(enabled: boolean) {
  return useQuery({
    queryKey: ["invitations"],
    enabled,
    queryFn: () => apiFetch<InvitationRow[]>("/api/v1/invitations"),
  });
}

export function useCreateInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (email: string) =>
      apiFetch<InvitationRow>("/api/v1/invitations", {
        method: "POST",
        body: JSON.stringify({ email }),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["invitations"] }),
  });
}

export function useDeleteInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/invitations/${id}`, { method: "DELETE" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["invitations"] }),
  });
}
