import type { ThresholdSource } from "@/lib/thresholds";

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
  gear_id: number | null;
  is_race: boolean;
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
  /** Sesión de test: al sincronizar el entreno se analiza sola. */
  test_protocol?: string | null;
}

export interface PlannedSession extends PlannedSessionInput {
  id: number;
  activity_id: number | null;
  match_mode: "auto" | "manual";
  compliance_score: number | null;
  /** Sesión generada por un plan de entrenamiento automático. */
  plan_id?: number | null;
  session_kind?: SessionKind | null;
  /** Envío a Garmin Connect: "" (no enviada), sent o error. */
  garmin_status?: "" | "sent" | "error";
  garmin_error?: string;
  garmin_sent_at?: string | null;
  /** Enviada, pero cambiada después: hay que volver a enviarla. */
  garmin_outdated?: boolean;
  /** Envío a COROS (conexión oficial). */
  coros_status?: "" | "sent" | "error";
  coros_error?: string;
  coros_sent_at?: string | null;
  coros_outdated?: boolean;
  planned_duration_s: number;
  planned_distance_m: number | null;
  /** Ruta del mapa asociada a la sesión. */
  planned_route_id?: number | null;
  route?: RouteSummary | null;
}

export type StepStatus = "ok" | "near" | "off";

// ─── Rutas planificadas (Plan → Rutas) ───────────────────────────────────────

export interface RouteSummary {
  id: number;
  nombre: string;
  modo: string;
  distancia_km: number;
  desnivel_positivo_m: number;
  desnivel_negativo_m: number;
}

export interface RouteShare {
  tipo: string;
  distancia_m: number;
  pct: number;
}

/** Ruta calculada (sin guardar): traza [lat, lon, alt] y perfil [distancia_m, alt]. */
export interface RoutePlan {
  mode: string;
  geometry: (number | null)[][];
  distance_m: number;
  ascent_m: number;
  descent_m: number;
  profile: number[][];
  surfaces: RouteShare[];
  waytypes: RouteShare[];
  max_altitude_m: number | null;
  min_altitude_m: number | null;
  estimated_s: number;
  estimate_basis: string;
}

export interface PlannedRouteBrief {
  id: number;
  name: string;
  mode: string;
  distance_m: number;
  ascent_m: number;
  descent_m: number;
  estimated_s: number | null;
  preview: number[][];
  created_at: string;
}

export interface PlannedRouteDetail extends PlannedRouteBrief {
  waypoints: number[][];
  geometry: (number | null)[][];
  profile: number[][];
  surfaces: RouteShare[];
  waytypes: RouteShare[];
  sessions: { id: number; day: string; title: string }[];
}

export interface PlannedRoutePage {
  items: PlannedRouteBrief[];
  total: number;
}

export interface GeoResult {
  label: string;
  lat: number;
  lon: number;
}

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
  training_paces:
    | ({
        easy: [number, number];
        threshold: number;
        interval: number;
        vdot: number;
      } & PacesBasis)
    | null;
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
  /** Hora de salida «HH:MM» (para el clima). */
  start_time?: string | null;
  location_name?: string;
  lat?: number | null;
  lon?: number | null;
  /** Desnivel positivo total si no hay GPX. */
  elevation_gain_m?: number | null;
}

export interface RaceGoal extends RaceGoalInput {
  id: number;
  result_activity_id: number | null;
  result_time_s: number | null;
  predicted_time_s: number | null;
  probable_s: number | null;
  days_left: number;
  has_course: boolean;
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

/** De dónde salen los ritmos de entrenamiento y las alternativas del umbral. */
export interface PacesBasis {
  basis: "marcas" | "umbral" | null;
  vdot_marks?: number | null;
  vdot_from_races?: boolean;
  threshold_pace_s_km?: number | null;
  threshold_source?: ThresholdSource | null;
  alternatives?: Partial<Record<ThresholdSource, number>>;
}

export interface TrainingPaces extends PacesBasis {
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
  /** Datos que consultó el asistente para responder. */
  tools?: string[] | null;
  /** Lo que hizo el entrenador: datos guardados en la ficha, propuestas del plan… */
  effects?: CoachEffect[] | null;
  /** Valoración: 1 útil, -1 no útil. */
  feedback?: number | null;
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
    lthr_source: "test" | "garmin" | "fc_max" | null;
    threshold_pace_s_km: number | null;
    pace_source: ThresholdSource | null;
    vdot: number | null;
    candidates?: Partial<Record<ThresholdSource, number>>;
    garmin_date?: string | null;
    test_date?: string | null;
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

// ─── Planes de entrenamiento automáticos ────────────────────────────────────

export type PlanPhase = "base" | "build" | "peak" | "taper";
export type SessionKind =
  "easy" | "long" | "threshold" | "intervals" | "race_pace" | "race" | "test";

export interface TrainingPlanInput {
  goal_id: number;
  weekdays: number[];
  long_run_weekday: number;
}

export interface PlanPreviewWeek {
  index: number;
  start: string;
  phase: PlanPhase;
  phase_label: string;
  target_km: number;
  is_recovery: boolean;
  sessions: { day: string; title: string; kind: SessionKind; km: number }[];
}

export interface PlanPreview {
  weeks: PlanPreviewWeek[];
  start_km_week: number;
}

export interface PlanAdjustment {
  action: "progress" | "hold" | "reduce";
  reason: string;
  at: string;
}

export interface TrainingPlanWeekOut {
  index: number;
  start: string;
  phase: PlanPhase;
  phase_label: string;
  target_km: number;
  done_km: number;
  is_recovery: boolean;
  is_current: boolean;
  adjustment: PlanAdjustment | null;
  sessions: {
    id: number;
    day: string;
    title: string;
    kind: SessionKind | null;
    done: boolean;
    compliance: number | null;
  }[];
}

export interface TrainingPlanReport {
  id: number;
  status: "active" | "cancelled" | "done";
  goal_id: number | null;
  goal_name: string | null;
  race_date: string;
  distance_m: number;
  weekdays: number[];
  long_run_weekday: number;
  vdot: number | null;
  weeks: TrainingPlanWeekOut[];
  current_week: number | null;
  total_weeks: number;
}

// ─── Material y avisos de lesión ─────────────────────────────────────────────

export type GearStatus = "ok" | "soon" | "replace" | "retired";

export interface Gear {
  id: number;
  name: string;
  brand: string;
  model: string;
  sport: string;
  start_km: number;
  alert_km: number;
  first_use: string | null;
  is_default: boolean;
  retired: boolean;
  from_garmin: boolean;
  total_km: number;
  status: GearStatus;
}

export interface GearInput {
  name: string;
  brand: string;
  model: string;
  start_km: number;
  alert_km: number;
  first_use: string | null;
  is_default: boolean;
  retired: boolean;
}

export type RiskStatus = "good" | "watch" | "alert";

export interface InjuryCheck {
  key: "volume" | "acwr" | "monotony" | "long_run" | "shoes";
  status: RiskStatus;
  title: string;
  message: string;
  evidence: string[];
}

export interface InjuryReport {
  status: RiskStatus;
  summary: string;
  checks: InjuryCheck[];
  week_km: number;
  disclaimer: string;
}

// ─── Notificaciones ──────────────────────────────────────────────────────────

export interface NotificationPrefs {
  daily_session: boolean;
  daily_hour: number;
  timezone: string;
  overload: boolean;
  sync_error: boolean;
  achievements: boolean;
  plan_changes: boolean;
  activity_reviews: boolean;
  tests: boolean;
  weekly_review: boolean;
}

export interface NotificationConfig {
  public_key: string;
  prefs: NotificationPrefs;
  devices: {
    id: number;
    user_agent: string;
    created_at: string;
    last_ok_at: string | null;
    endpoint_host: string;
  }[];
  recent: { title: string; kind: string; sent_at: string }[];
}

// ─── Rachas, logros y retos ──────────────────────────────────────────────────

export type AchievementKind = "milestone" | "streak" | "record" | "challenge";

export interface AchievementsReport {
  streak: {
    current: number;
    best: number;
    target: number;
    this_week: number;
    weeks: { start: string; count: number; ok: boolean }[];
  };
  challenges: {
    key: "km" | "sessions" | "elevation";
    title: string;
    unit: string;
    target: number;
    current: number;
    done: boolean;
    month: string;
    ends: string;
  }[];
  achievements: {
    key: string;
    kind: AchievementKind;
    title: string;
    description: string;
    achieved_on: string;
    activity_id: number | null;
  }[];
  upcoming: {
    key: string;
    group: "single_run" | "run_km" | "count" | "elevation" | "streak";
    title: string;
    description: string;
    current: number;
    target: number;
    unit: string;
    pct: number;
  }[];
  milestones: { unlocked: number; total: number };
}

// ─── Recorridos y comparador ─────────────────────────────────────────────────

export interface RouteEffort {
  activity_id: number;
  day: string;
  name: string;
  duration_s: number;
  distance_m: number | null;
  pace_s_km: number | null;
  avg_hr: number | null;
  elevation_gain_m: number | null;
}

export interface RouteSummary {
  id: number;
  name: string;
  sport: string;
  distance_m: number | null;
  count: number;
  best: RouteEffort | null;
  last: RouteEffort;
  first_day: string;
}

export interface RouteDetail extends RouteSummary {
  efforts: RouteEffort[];
  track: [number, number][];
  /** Solo al pedirlo desde una actividad: su puesto por ritmo (1 = mejor). */
  rank?: number | null;
}

export interface ComparePoint {
  distance_m: number;
  time_a: number | null;
  time_b: number | null;
  pace_a: number | null;
  pace_b: number | null;
  hr_a: number | null;
  hr_b: number | null;
  alt_a: number | null;
  alt_b: number | null;
  gap_s: number | null;
}

export interface CompareResult {
  a: RouteEffort;
  b: RouteEffort;
  distance_m: number;
  points: ComparePoint[];
  splits: {
    km: number;
    a: number | null;
    b: number | null;
    diff: number | null;
  }[];
  track_a: [number, number][];
  track_b: [number, number][];
}

// ─── Día de carrera ──────────────────────────────────────────────────────────

export interface GeoPlace {
  name: string;
  region: string;
  country: string;
  lat: number;
  lon: number;
}

export interface PacingKm {
  km: number;
  distance_m: number;
  factor: number;
  time_s: number;
  pace_s_km: number;
  cum_s: number;
}

export type RaceDayPlan =
  | { available: false; reason: string }
  | {
      available: true;
      base_s: number;
      base_source: "forecast" | "target";
      elevation_pct: number;
      heat_pct: number;
      adjusted_s: number;
      target_s: number | null;
      weather: {
        source: "forecast" | "history" | "climate";
        label: string;
        temp_c: number | null;
        temp_max_c: number | null;
        dew_point_c: number | null;
        humidity_pct: number | null;
        wind_kmh: number | null;
        rain_prob_pct: number | null;
      } | null;
      weather_error: string | null;
      heat: {
        pct: number;
        status: "good" | "watch" | "alert";
        advice: string;
        evidence: string[];
      } | null;
      course: {
        source: "gpx" | "gain";
        name?: string;
        gain_m: number;
        loss_m: number;
        distance_m?: number;
        profile?: [number, number][];
        track?: [number, number][];
      } | null;
      pacing: PacingKm[];
      pacing_target: PacingKm[] | null;
      fueling: {
        carbs_g_h: [number, number];
        gels: number;
        gel_times_min: number[];
        fluid_ml_h: [number, number];
        sodium: boolean;
        note: string;
        evidence: string[];
      };
      elevation_evidence: string[];
    };

// ─── Otros relojes ───────────────────────────────────────────────────────────

export interface SourcesStatus {
  coros: {
    account: string;
    status: "ok" | "expired" | "error";
    last_sync_at: string | null;
    last_error: string;
  } | null;
  coros_official?: {
    status: "ok" | "expired" | "error";
    connected_at: string;
    last_sync_at?: string | null;
    last_error: string;
  } | null;
  health_connect: {
    hint: string;
    created_at: string;
    last_used_at: string | null;
  } | null;
  ingest_url: string;
  apple_shortcut_url: string;
  apple_last_at: string | null;
}

export interface AppleImport {
  id: string;
  filename: string;
  size_bytes: number;
  received_bytes: number;
  status: "uploading" | "queued" | "processing" | "done" | "error";
  progress: number;
  result: { workouts?: number; duplicates?: number; days?: number };
  error: string;
  created_at: string;
  chunk_bytes: number;
}

export interface ImportResult {
  activity_id: number;
  created: boolean;
  source: string;
}

// ─── Análisis de entrenos con la IA ──────────────────────────────────────────

export type ReviewSport =
  "running" | "cycling" | "strength" | "swimming" | "other";

export interface ActivityReview {
  activity_id: number;
  status: "pending" | "done" | "error";
  content: string;
  error: string;
  model_label: string | null;
  tools: string[] | null;
  updated_at: string | null;
  created_at: string;
}

export interface LatestReview extends ActivityReview {
  activity_name: string;
  activity_day: string;
}

export interface ReviewSettings {
  enabled: boolean;
  sports: ReviewSport[];
  daily_max: number;
  has_ai: boolean;
  used_today: number;
}

// ─── Tests de rendimiento ────────────────────────────────────────────────────

export type TestSport = "running" | "cycling" | "swimming";

export interface TestProtocol {
  key: string;
  label: string;
  sport: TestSport;
  summary: string;
  how: string;
  detectable: boolean;
  template: Partial<PlannedBlock>[];
}

export interface TestCheck {
  key: string;
  ok: boolean;
  message: string;
  critical: boolean;
}

export interface TestResults {
  lthr?: number;
  threshold_pace_s_km?: number;
  vo2max?: number;
  hr_max?: number;
  vdot?: number;
  time_s?: number;
  distance_m?: number;
  cs_speed?: number;
  d_prime_m?: number;
  hr_zones?: { name: string; min: number; max: number | null }[];
  window_s?: [number, number];
  ftp?: number;
  best_power_w?: number;
  power_zones?: { name: string; min: number; max: number | null }[];
  css_pace_s_100m?: number;
  t400_s?: number;
  t200_s?: number;
  css_zones?: { name: string; fast: number | null; slow: number | null }[];
  lt1_hr?: number;
  lt1_pace_s_km?: number;
  lt1_power?: number;
  obla_pace_s_km?: number;
  obla_power?: number;
  lt2_method?: "dmax" | "obla";
  baseline_mmol?: number;
  lactate_steps?: { intensity: number; lactate: number; hr: number | null }[];
}

export interface PerformanceTest {
  id: number;
  sport: TestSport;
  protocol: string;
  protocol_label: string;
  test_date: string;
  activity_id: number | null;
  activity_name: string | null;
  source: "manual" | "activity" | "planned";
  status: "detected" | "confirmed" | "failed";
  confidence: "alta" | "media" | "baja" | "";
  results: TestResults;
  checks: TestCheck[];
  notes: string;
  summary: string;
  created_at: string;
  confirmed_at: string | null;
}

export interface ManualTestInput {
  protocol?: "manual" | "lab" | "swim_css";
  sport: TestSport;
  test_date: string;
  lthr?: number | null;
  threshold_pace_s_km?: number | null;
  vo2max?: number | null;
  hr_max?: number | null;
  ftp?: number | null;
  vt1_hr?: number | null;
  vt1_pace_s_km?: number | null;
  vt1_power?: number | null;
  vt2_hr?: number | null;
  vt2_pace_s_km?: number | null;
  vt2_power?: number | null;
  t400_s?: number | null;
  t200_s?: number | null;
  notes?: string;
}

export interface LactateStepInput {
  lactate: number;
  pace_s_km?: number | null;
  power?: number | null;
  hr?: number | null;
  lap_index?: number | null;
}

export interface LactateTestInput {
  sport: "running" | "cycling";
  test_date: string;
  activity_id?: number | null;
  steps: LactateStepInput[];
  notes?: string;
}

// ─── Análisis de una actividad ───────────────────────────────────────────────

export interface ActivityAnalysis {
  hr_zones: {
    zones: {
      name: string;
      min: number;
      max: number | null;
      seconds: number;
      pct: number;
    }[];
    lthr: number | null;
    source: string;
  };
  vo2max: {
    activity: number | null;
    source: "reloj" | "estimado" | null;
    current: number | null;
    current_day: string | null;
    percentile: {
      percentile: number;
      bound: "below" | "above" | null;
      age_group: string;
      median: number;
    } | null;
  };
  splits: {
    km: number;
    distance_m: number;
    seconds: number;
    /** Tiempo desde la salida hasta el final de este km. */
    elapsed_s: number;
    pace_s_km: number;
    avg_hr: number | null;
    /** Pasos por minuto (media sin paradas). */
    avg_cadence: number | null;
    elevation_gain_m: number;
  }[];
  decoupling: {
    pct: number;
    first_ef: number;
    second_ef: number;
    level: "bien" | "alta" | "muy alta";
  } | null;
}

// ─── Entrenador IA ───────────────────────────────────────────────────────────

export type CoachEffect =
  | {
      tipo: "memoria";
      accion: "guardado" | "corregido" | "olvidado";
      id: number;
      categoria: string;
      categoria_nombre: string;
      dato: string;
    }
  | {
      tipo: "propuesta";
      id: number;
      sesion_id: number;
      resumen: string;
      motivo: string;
    }
  | { tipo: "perfil"; cambios: Record<string, string> }
  | { tipo: "umbrales"; id: number; cambios: Record<string, string> }
  | { tipo: "entrevista"; accion: "terminada" }
  /** Respuestas rápidas a la pregunta del entrenador (botones). */
  | { tipo: "opciones"; opciones: string[] }
  /** Preguntas para seguir la conversación (botones). */
  | { tipo: "sugerencias"; sugerencias: string[] }
  /** La respuesta se cortó: se guardó lo que llevaba escrito. */
  | { tipo: "incompleta" };

export interface CoachSettings {
  health_consent: boolean;
  health_consent_at: string | null;
  interview_done: boolean;
  weekly_review: boolean;
  categories: Record<string, string>;
  health_categories: string[];
}

export interface CoachMemory {
  id: number;
  category: string;
  content: string;
  source: "ia" | "usuario" | "entrevista" | "revision";
  created_at: string;
  updated_at: string | null;
}

export interface WeeklyCheckin {
  id: number;
  week_start: string;
  status: "pending" | "processing" | "done" | "error";
  answers: Record<string, number | string>;
  summary: string;
  error: string;
  effects: CoachEffect[] | null;
  updated_at: string | null;
}

export interface PlanProposal {
  id: number;
  planned_session_id: number;
  session_title: string | null;
  session_day: string | null;
  summary: string;
  reason: string;
  change: Record<string, unknown>;
  status: "pending" | "accepted" | "rejected" | "expired";
  created_at: string;
}
