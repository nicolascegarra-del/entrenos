import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  ActivityDetail,
  ActivityPage,
  ActivitySummary,
  DeviceSpan,
  EfficiencyPoint,
  FitnessResponse,
  GarminStatus,
  MetricDefinition,
  PlannedSession,
  PlannedSessionDetail,
  PlannedSessionInput,
  RecordRead,
  SeriesPoint,
  Streams,
  Summary,
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
