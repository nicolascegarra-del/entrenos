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

export type BlockKind =
  "warmup" | "steady" | "interval" | "recovery" | "cooldown";
export type TargetMetric = "pace" | "speed" | "hr" | "power" | "cadence";

export interface PlannedBlock {
  position?: number;
  kind: BlockKind;
  repeat: number;
  duration_s: number | null;
  distance_m: number | null;
  target_metric: TargetMetric | null;
  target_min: number | null;
  target_max: number | null;
  recovery_duration_s: number | null;
  recovery_distance_m: number | null;
}

export interface PlannedSessionInput {
  day: string;
  sport: string;
  title: string;
  notes: string;
  blocks: PlannedBlock[];
}

export interface PlannedSession extends PlannedSessionInput {
  id: number;
  activity_id: number | null;
  match_mode: "auto" | "manual";
  compliance_score: number | null;
  planned_duration_s: number;
  planned_distance_m: number | null;
}

export type StepStatus = "ok" | "near" | "off";

export interface ComplianceStep {
  label: string;
  kind: BlockKind;
  planned: {
    duration_s: number | null;
    distance_m: number | null;
    target_metric: TargetMetric | null;
    target_min: number | null;
    target_max: number | null;
  };
  actual: {
    duration_s: number;
    distance_m: number;
    laps: number[];
    value: number | null;
  };
  completion: number | null;
  score: number | null;
  status: StepStatus | null;
  direction: "fast" | "slow" | "low" | "high" | null;
}

export interface ComplianceDetail {
  score?: number | null;
  method?: "laps" | "streams" | null;
  steps?: ComplianceStep[];
  unplanned_laps?: number[];
}

export interface PlannedSessionDetail extends PlannedSession {
  compliance_detail: ComplianceDetail;
  activity: ActivitySummary | null;
}

// ─── Progresión ──────────────────────────────────────────────────────────────

export interface FitnessPoint {
  day: string;
  load: number;
  ctl: number;
  atl: number;
  tsb: number;
}

export interface FitnessResponse {
  lthr: number | null;
  hr_rest: number;
  points: FitnessPoint[];
}

export interface WeekPoint {
  week: string;
  distance_m: number;
  duration_s: number;
  count: number;
  load: number;
}

export interface SeriesPoint {
  day: string;
  value: number;
}

export interface EfficiencyPoint extends SeriesPoint {
  activity_id: number;
}

export interface RecordBest {
  time_s: number;
  activity_id: number;
  day: string;
}

export interface RecordRead {
  key: string;
  label: string;
  distance_m: number;
  best: RecordBest | null;
  history: RecordBest[];
}

export interface DeviceSpan {
  id: number;
  name: string;
  first_seen: string;
  last_seen: string;
}

export interface WeekTotals {
  distance_m: number;
  duration_s: number;
  count: number;
  load: number;
}

export interface Summary {
  this_week: WeekTotals;
  last_week: WeekTotals;
  fitness: FitnessPoint | null;
  form_label: string | null;
  vo2max: number | null;
  resting_hr: number | null;
  planned_this_week: {
    id: number;
    day: string;
    title: string;
    sport: string;
    compliance_score: number | null;
    activity_id: number | null;
  }[];
  compliance_avg: number | null;
  recent: ActivitySummary[];
}
