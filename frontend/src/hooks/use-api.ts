import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { ActivityDetail, ActivityPage, GarminStatus, MetricDefinition, Streams } from "@/types/api";

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
  return useQuery({ queryKey: ["sports"], queryFn: () => apiFetch<string[]>("/api/v1/activities/sports") });
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
      apiFetch<Streams>(`/api/v1/activities/${id}/streams?channels=${channels.join(",")}&max_points=800`),
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
    refetchInterval: (query) => (query.state.data?.last_run?.status === "running" ? 3000 : false),
  });
}

export function useSyncNow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ queued: boolean }>("/api/v1/garmin/sync", { method: "POST" }),
    onSuccess: async () => {
      // La tarea tarda un instante en crear su SyncRun: espera un poco antes de consultar.
      await new Promise((r) => setTimeout(r, 1500));
      await queryClient.invalidateQueries({ queryKey: ["garmin-status"] });
      await queryClient.invalidateQueries({ queryKey: ["activities"] });
    },
  });
}
