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
  connection: {
    status: "none" | "ok" | "expired";
    display_name: string | null;
    connected_at: string | null;
    last_ok_at: string | null;
  };
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
  age_grade: AgeGrade | null;
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
  /** Semáforo de hoy a partir de frescura y carga reciente. */
  readiness: {
    status: "good" | "watch" | "alert" | "nodata";
    title: string;
    message: string;
    acwr: number | null;
  };
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

export type SyncMode = "auto" | "manual";

export interface SyncSettings {
  mode: SyncMode;
  interval_min: number;
  intervals: number[];
  next_sync_at: string | null;
}

export type InsightStatus = "good" | "watch" | "alert" | "info" | "nodata";

export interface Insight {
  status: InsightStatus;
  title: string;
  message: string;
  evidence: { label: string; url: string | null }[];
}

export type InsightSection =
  | "fitness"
  | "acwr"
  | "volume"
  | "intensity"
  | "resting_hr"
  | "vo2max"
  | "efficiency"
  | "records"
  | "recovery"
  | "consistency"
  | "strength";

export interface InsightsResponse {
  overall: { label: string; status: InsightStatus; title: string }[];
  sections: Record<InsightSection, Insight>;
  acwr: { day: string; acwr: number | null }[];
  intensity: {
    split_min: { low: number; moderate: number; high: number };
    weeks: { week: string; low: number; moderate: number; high: number }[];
  };
  decoupling: { day: string; activity_id: number; value: number }[];
  predictions: {
    label: string;
    distance_m: number;
    time_s: number;
    pace_s_km: number;
  }[];
  training_paces: {
    easy: [number, number];
    threshold: number;
    interval: number;
  } | null;
  disclaimer: string;
}

export interface ActivityFeedback {
  rpe: number | null;
  feeling: number | null;
  notes: string;
  day: string;
  context: Partial<
    Record<
      | "sleep_seconds"
      | "sleep_score"
      | "resting_hr"
      | "hrv_last_night"
      | "body_battery_max",
      number
    >
  >;
}

// ─── Objetivos ───────────────────────────────────────────────────────────────

export interface RaceGoalInput {
  name: string;
  race_date: string;
  distance_m: number;
  target_time_s: number | null;
}

export interface RaceGoal extends RaceGoalInput {
  id: number;
  result_activity_id: number | null;
  result_time_s: number | null;
  predicted_time_s: number | null;
  probable_s: number | null;
  days_left: number;
}

export type PaceZone =
  "easy" | "marathon" | "threshold" | "interval" | "repetition";
export type DanielsPaces = Record<PaceZone, [number, number]>;

export interface GoalReport {
  goal: RaceGoal;
  forecast: {
    probable_s: number | null;
    optimistic_s: number | null;
    conservative_s: number | null;
    models: {
      key: string;
      label: string;
      time_s: number;
      weight: number;
      detail: string;
    }[];
    warnings: string[];
    vdot_current: number | null;
    vdot_source: "marca" | "vo2max" | null;
    exponent: number | null;
    exponent_personal: boolean;
    calibration_factor: number | null;
  };
  gap_s: number | null;
  vdot_needed: number | null;
  weeks_left: number;
  evolution: {
    day: string;
    probable_s: number;
    optimistic_s: number;
    conservative_s: number;
  }[];
  checklist: {
    key: string;
    label: string;
    status: "ok" | "pending" | "warn";
    current: string;
  }[];
  paces: DanielsPaces | null;
  explanation: Explanation;
  paces_explanation: PacesExplanation | null;
  age_grade: {
    age: number;
    probable: AgeGrade | null;
    target: AgeGrade | null;
  } | null;
}

export interface TrainingPaces {
  vdot: number | null;
  source: "marca" | "vo2max" | null;
  paces: DanielsPaces | null;
  explanation: PacesExplanation | null;
}

export interface Explanation {
  summary: string;
  points: { title: string; text: string }[];
  sources: { label: string; url: string | null }[];
}

export interface PacesExplanation {
  summary: string;
  zones: { key: PaceZone; label: string; percent: string; purpose: string }[];
  sources: { label: string; url: string | null }[];
}

// ─── Perfil, cuentas y usuarios ──────────────────────────────────────────────

export type Sex = "male" | "female";

export interface ProfileInput {
  birth_date: string | null;
  sex: Sex | null;
  weight_kg: number | null;
  height_cm: number | null;
}

export interface Profile extends ProfileInput {
  source: "garmin" | "manual";
  age: number | null;
  hr_max: number | null;
  hr_max_source: "real" | "tanaka" | null;
  bmi: number | null;
  stride_ratio: number | null;
  vo2max: number | null;
  vo2max_percentile: {
    percentile: number;
    bound: "below" | "above" | null;
    age_group: string;
    median: number;
    out_of_range_age: boolean;
  } | null;
  weight_history: { day: string; weight_kg: number }[];
}

export interface AgeGrade {
  percent: number;
  age_standard_s: number;
  factor: number;
  level: string;
}

export interface ConnectState {
  status: "pending" | "needs_mfa" | "verifying" | "connected" | "error";
  error: string | null;
}

export type AccountTier = "full" | "basic";

/** Límites de la cuenta; null = sin límite. */
export interface AccountLimits {
  history_days: number | null;
  max_goals: number | null;
  max_sessions_week: number | null;
}

export interface Me {
  id: number;
  email: string;
  is_admin: boolean;
  tier: AccountTier;
  /** false = aún no ha hecho (ni omitido) la configuración guiada. */
  onboarded: boolean;
  limits: AccountLimits;
}

// ─── Administración ──────────────────────────────────────────────────────────

export type UserStatus = "active" | "unverified" | "pending" | "disabled";
export type RegistrationMode = "invite" | "open" | "approval";

export interface AdminUserRow {
  id: number;
  email: string;
  is_admin: boolean;
  status: UserStatus;
  tier: AccountTier;
  inactivity_warned_at: string | null;
  locked: boolean;
  created_at: string;
  last_login_at: string | null;
  garmin: "none" | "ok" | "expired";
  last_sync: { at: string; status: string; error: string | null } | null;
  activities: number;
  ai_questions_30d: number;
  ai_tokens_30d: number;
}

export interface UsersPage {
  items: AdminUserRow[];
  total: number;
}

export interface LinkOut {
  link: string;
  expires_at: string;
  emailed: boolean;
}

export interface InvitationRow {
  id: number;
  email: string;
  status: "pending" | "used" | "expired";
  created_at: string;
  expires_at: string;
  used_at: string | null;
  used_by_email: string | null;
}

export interface InvitationCreated extends InvitationRow {
  link: string;
  emailed: boolean;
}

export interface BasicLimits {
  basic_history_days: number;
  basic_max_goals: number;
  basic_max_sessions_week: number;
}

export interface AdminSettings {
  registration_mode: RegistrationMode;
  email_enabled: boolean;
  captcha_enabled: boolean;
  blocked_domains: string[];
  limits: BasicLimits;
}

export interface AdminSettingsInput {
  registration_mode?: RegistrationMode;
  blocked_domains?: string[];
  limits?: BasicLimits;
}

export interface AuditRow {
  id: number;
  created_at: string;
  actor_email: string | null;
  action: string;
  target_email: string | null;
  detail: Record<string, unknown>;
}

export interface SystemStatus {
  inactive_warned: number;
  inactive_deleting_7d: number;
  worker_ok: boolean | null;
  last_heartbeat: string | null;
  last_sync_at: string | null;
  garmin_expired: string[];
  sync_failing: { email: string; at: string; error: string | null }[];
  last_backup: {
    file: string;
    at: string;
    size_mb: number;
    count: number;
  } | null;
  email_mode: "smtp" | "file" | "disabled";
  users_by_status: Partial<Record<UserStatus, number>>;
  pending_requests: number;
}

export interface AuthOptions {
  registration: RegistrationMode;
  email_enabled: boolean;
  /** Registro sin invitación posible (modo abierto o con aprobación, y correo configurado). */
  signup_available: boolean;
  /** Clave pública de Cloudflare Turnstile; null = sin captcha. */
  captcha_site_key: string | null;
  /** Días de histórico de Garmin de las cuentas Básicas (autoregistro). */
  basic_history_days: number;
}

// ─── Asistente IA ────────────────────────────────────────────────────────────

export type AiProviderId = "openai" | "gemini" | "anthropic";

export interface AiProviderRow {
  provider: AiProviderId;
  label: string;
  keys_url: string;
  privacy: string;
  default_model: string;
  suggested_models: string[];
  configured: boolean;
  model: string | null;
  key_last4: string | null;
  enabled: boolean;
  is_default: boolean;
  updated_at: string | null;
}

export interface AiProviders {
  providers: AiProviderRow[];
  daily_limit: number;
  used_today: number;
}

export interface AiProviderInput {
  /** Vacía o null = conservar la clave guardada. */
  api_key: string | null;
  model: string;
  enabled: boolean;
  is_default: boolean;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  provider: string | null;
  model: string | null;
  created_at: string;
}

export interface ConversationBrief {
  id: number;
  title: string;
  updated_at: string;
}

export interface Conversation extends ConversationBrief {
  messages: ChatMessage[];
}

// ─── Correo (Admin → Correo) ─────────────────────────────────────────────────

export type SmtpSecurity = "starttls" | "ssl" | "none";

export interface EmailSettings {
  /** De dónde sale la configuración en uso: el panel o las variables de entorno. */
  source: "panel" | "env";
  mode: "smtp" | "file" | "disabled";
  enabled: boolean;
  host: string;
  port: number;
  security: SmtpSecurity;
  user: string;
  has_password: boolean;
  sender: string;
  public_url: string;
  env_configured: boolean;
}

export interface EmailSettingsInput {
  enabled: boolean;
  host: string;
  port: number;
  security: SmtpSecurity;
  user: string;
  /** null = conservar la guardada; "" = borrarla. */
  password: string | null;
  sender: string;
  public_url: string;
}

// ─── Curva de ritmos y zonas ─────────────────────────────────────────────────

export interface PaceBest {
  pace_s_km: number;
  speed: number;
  activity_id: number;
  day: string;
}

export interface PaceCurve {
  durations: {
    seconds: number;
    best: PaceBest | null;
    previous: PaceBest | null;
  }[];
  quarters: { label: string; paces: Record<string, number> }[];
  critical_speed: {
    speed: number;
    pace_s_km: number;
    d_prime_m: number;
  } | null;
}

export interface ZoneSet {
  valid_from: string;
  thresholds: {
    lthr: number | null;
    lthr_source: "garmin" | "fc_max" | null;
    threshold_pace_s_km: number | null;
    pace_source: "vdot" | "velocidad_critica" | "mejor_hora" | null;
    vdot: number | null;
  };
  zones: {
    hr: { name: string; min: number; max: number | null }[];
    pace: { name: string; fast: number | null; slow: number | null }[];
  };
}

export interface ZonesReport {
  current: ZoneSet | null;
  previous: ZoneSet | null;
  history: ZoneSet[];
  changed_recently: boolean;
}
