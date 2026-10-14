/** Tipos de la API (espejo de app/schemas del backend). */

export interface ActivitySummary {
  id: number;
  sport: string;
  name: string;
  start_time: string;
  timezone: string | null;
  duration_s: number;
  distance_m: number | null;
  avg_hr: number | null;
  elevation_gain_m: number | null;
  metrics: Record<string, number>;
}

export interface ActivityPage {
  items: ActivitySummary[];
  next_cursor: string | null;
}

export interface Lap {
  index: number;
  start_offset_s: number;
  duration_s: number;
  distance_m: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_speed: number | null;
  metrics: Record<string, number>;
}

export interface ActivityDetail extends ActivitySummary {
  moving_duration_s: number | null;
  max_hr: number | null;
  calories: number | null;
  device: { id: number; name: string } | null;
  laps: Lap[];
  channels: string[];
}

export interface Streams {
  points: number;
  channels: Record<string, (number | null)[]>;
}

export interface MetricDefinition {
  key: string;
  scope: "activity" | "stream" | "daily";
  label: string;
  unit: string;
  higher_is_better: boolean | null;
  sports: string[];
}

export interface SyncRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "error";
  new_activities: number;
  daily_days: number;
  error: string | null;
}

export interface GarminStatus {
  connected: boolean;
  last_run: SyncRun | null;
}
