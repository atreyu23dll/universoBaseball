/** Tipos del contrato de la API. Reflejan lo que el backend devuelve de verdad. */

export type Confidence = 'observed' | 'estimated' | 'fictional' | 'user_configured';

export interface UniverseSummary {
  id: string;
  name: string;
  world_date: string;
  master_seed: number;
  sim_version: string;
  fixture_version: string;
  currency: string;
  status: string;
  competitions: number;
  clubs: number;
  people: number;
  games_played: number;
  busy: boolean;
}

export interface ClubBrief {
  id: string;
  name: string;
  short_name: string;
  nickname: string;
  primary_color: string;
  secondary_color: string;
  crest_shape: string;
  crest_motif: string;
}

export interface GameBrief {
  id: string;
  edition_id: string;
  game_date: string;
  stage: string;
  series_key: string | null;
  state: string;
  home: ClubBrief | null;
  away: ClubBrief | null;
  home_score: number | null;
  away_score: number | null;
  innings_played: number | null;
  park_note: string;
}

export interface NewsItem {
  world_date: string;
  event_type: string;
  headline: string | null;
  payload: Record<string, unknown>;
}

export interface EditionBrief {
  id: string;
  year: number;
  stage: string;
  status: string;
  champion?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  warnings?: string[];
}

export interface DashboardCompetition {
  id: string;
  name: string;
  kind: string;
  scope_level: string;
  relationship_mode: string;
  mobility: { role: 'upper' | 'lower'; slots: number | null; with: string[] } | null;
  editions: EditionBrief[];
}

export interface Dashboard {
  universe: {
    id: string;
    name: string;
    world_date: string;
    master_seed: number;
    sim_version: string;
    fixture_version: string;
    currency: string;
    busy: boolean;
  };
  counts: {
    competitions: number;
    clubs: number;
    people: number;
    games_played: number;
    games_pending: number;
  };
  competitions: DashboardCompetition[];
  today: GameBrief[];
  recent_results: GameBrief[];
  news: NewsItem[];
}

export interface StandingRow {
  rank: number;
  club: ClubBrief | null;
  played: number;
  wins: number;
  losses: number;
  ties: number;
  points: number;
  win_pct: number | null;
  runs_for: number;
  runs_against: number;
  run_differential: number;
  home_record: string;
  away_record: string;
  streak: string;
  last_ten: string[];
  tiebreak_note: string;
}

export interface MarketPreview {
  place_key: string;
  name: string;
  population: number;
  economy_index: number;
  culture_index: number;
  training_opportunity: number;
  confidence: Confidence;
}

/** Una línea de ingreso o gasto, con su causa declarada. */
export interface FinancialComponent {
  kind: 'revenue' | 'expense';
  source: string;
  label: string;
  amount: string | null;
  confidence: string;
  basis: string;
  mandatory: boolean;
}

/** Cuentas de un club: el desglose completo, no solo el total. */
export interface FinancialAssessment {
  currency: string | null;
  period: string;
  operating_budget_period: string | null;
  revenue: string | null;
  expenses: string | null;
  balance: string | null;
  cash_balance: string | null;
  debt: string | null;
  assets: string | null;
  valuation: string | null;
  confidence: string;
  tier: string | null;
  months_of_reference_cost: number | null;
  reference_monthly_cost: string | null;
  components: FinancialComponent[];
  risks: string[];
  notes: string[];
  sources: string[];
}

export interface RoleAssignment {
  role: string;
  paid: boolean;
  vacant: boolean;
  doubles_with: string | null;
}

export interface GenerationPreview {
  ruleset_checksum: string;
  seed: number;
  context: {
    participation_modality: string;
    modality_description: string;
    compensation_rule: string;
    market_score: number;
    /** Nivel competitivo emergente: sale de las cuentas de los clubes. */
    effective_level: number | null;
    resource_tier: string | null;
    aggregate_population: number;
    /** Moneda de la jurisdicción. `null` si el territorio no tiene ancla. */
    currency: string | null;
    reference_monthly_cost: string | null;
    talent_mean: number;
    markets: MarketPreview[];
  };
  clubs: Array<{
    name: string;
    place: string;
    institutional_type: string;
    /** Lo que el motor decidió, no lo que el usuario pidió. */
    governance: string | null;
    has_owner: boolean | null;
    venue_usage: string | null;
    roles: RoleAssignment[];
    annual_budget: string;
    financial_assessment: FinancialAssessment | null;
    venue_name: string;
    venue_type: string;
    capacity: number;
    fan_base: number;
    resource_multiplier: number;
    primary_color: string;
    secondary_color: string;
  }>;
  budget_range: { min: number; median: number; max: number };
  people_generated: number;
  free_agents: number;
  schedule: {
    games: number;
    games_per_club: number;
    requested_games_per_club: number;
    adjusted: boolean;
    first_date: string | null;
    last_date: string | null;
  };
  warnings: string[];
  provenance: Array<{
    entity_kind: string;
    procedure: string;
    notes: Array<{
      field: string;
      value: unknown;
      confidence: Confidence;
      derivation: string;
    }>;
    assumptions: string[];
  }>;
}

export interface SimStatus {
  universe_id: string;
  world_date: string;
  busy: boolean;
  pending_games: number;
  next_scheduled_game_date: string | null;
  job: {
    id: string;
    status: string;
    command_type: string;
    progress: {
      days_requested: number;
      days_done: number;
      games_played: number;
      editions_completed: number;
      transitions_applied: number;
      club_movements: number;
      seasons_opened: number;
      /** Temporadas de club liquidadas al cruzar la frontera. */
      clubs_settled: number;
      /** Clubes que dejaron de existir al no poder sostenerse. */
      clubs_folded: number;
      world_date: string | null;
      notes: string[];
    };
    error: string | null;
  } | null;
}

export interface Place {
  key: string;
  /** Moneda de curso legal del territorio, si sus datos la declaran. */
  currency?: string | null;
  kind: string;
  name: string;
  parent_key: string | null;
  country_code: string;
  lat: number;
  lon: number;
  elevation_m: number;
  confidence: Confidence;
  sources: string[];
  clubs: number;
  profile: {
    ref_year: number;
    population: number;
    economy_index: number;
    baseball_culture_index: number;
    cost_of_living_index: number;
    infrastructure_index: number;
    confidence: Confidence;
    sources: string[];
  } | null;
}

/** Regla efectiva de ascenso y descenso: un solo número para las dos ligas. */
export interface MobilityRules {
  competition_id: string;
  has_hierarchy: boolean;
  note: string;
  role?: 'upper' | 'lower';
  upper?: { competition_id: string; name: string };
  exchange_slots?: number;
  upper_selection?: { method: string; count: number | null };
  allow_unbalanced?: boolean;
  budget_adaptation?: number;
  apply_at?: string;
  branches?: MobilityBranch[];
}

export interface MobilityBranch {
  relationship_id: string;
  competition_id: string;
  name: string;
  slots: number;
  declared_slots: number | null;
  lower_selection: { method: string; count: number | null };
  eligibility_policy: string;
  requirements: { min_venue_capacity: number | null; max_debt_to_budget: number | null };
  on_requirement_failure: string;
  effective_from_season: number | null;
}

export interface MobilityMovement {
  club_id: string;
  club_name: string;
  direction: 'promoted' | 'relegated';
  from_competition_id: string;
  to_competition_id: string;
  rank: number;
  reason: string;
}

export interface MobilityTransition {
  id: string;
  season: number;
  applied_on: string;
  upper: { competition_id: string; name: string };
  promotions: number;
  relegations: number;
  plan: {
    total_slots: number;
    branch_quotas: Record<string, number>;
    movements: MobilityMovement[];
    rejected: {
      club_id: string;
      club_name: string;
      competition_id: string;
      rank: number;
      unmet: string[];
      policy: string;
    }[];
    notes: string[];
  };
}

export interface MobilityProjection {
  edition_id: string;
  has_hierarchy: boolean;
  direction?: 'promoted' | 'relegated';
  slots?: number;
  total_slots?: number;
  ranked?: boolean;
  upper?: { competition_id: string; name: string };
  projected: {
    club_id: string;
    club_name: string;
    rank: number;
    unmet_requirements: string[];
  }[];
  note?: string;
}

/** Una entidad geográfica resuelta del gazetteer mundial. */
export interface GeoEntity {
  id: string;
  name: string;
  kind: 'country' | 'region' | 'city' | 'district';
  country_iso2: string;
  country_name: string;
  admin_path: string | null;
  lat: number;
  lon: number;
  elevation_m: number;
  population: number | null;
  timezone: string;
  feature_code: string;
  currency: string | null;
  source: string;
  source_id: string;
  status: 'verified' | 'incomplete';
  status_notes: string[];
}

export interface GeoSearchResult {
  query: string;
  status: 'candidates' | 'unresolved';
  total: number;
  items: GeoEntity[];
  attribution: string;
  note: string;
}

export interface GeoStatus {
  imported: boolean;
  countries: number;
  entities: number;
  countries_with_currency: number;
  countries_with_reference_cost: number;
  attribution: string;
  note: string;
}

export interface GeoContext {
  entity: GeoEntity;
  population: { value: number | null; confidence: string; sources: string[] };
  currency: {
    code: string | null;
    name: string | null;
    confidence: string;
    reference_monthly_cost: string | null;
    sources: string[];
    note: string;
  };
  indices: {
    economy_index: number;
    baseball_culture_index: number;
    cost_of_living_index: number;
    infrastructure_index: number;
    confidence: string;
    sources: string[];
  };
  boundary: { available: boolean; note?: string; alternatives?: string[]; licence?: string };
  children: number;
  warnings: string[];
}

/** Un problema detectado, con su código tipado. */
export interface Issue {
  code: string;
  severity: 'blocking' | 'warning';
  message: string;
  suggestions: string[];
}

/** Borrador de competición: lo que el usuario va escribiendo. */
export interface Draft {
  id: string;
  universe_id: string;
  name: string;
  state:
    | 'draft'
    | 'geography_pending'
    | 'geography_resolved'
    | 'context_ready'
    | 'preview_ready'
    | 'preview_warning'
    | 'preview_blocked'
    | 'committed';
  intent: Record<string, unknown>;
  intent_fingerprint: string;
  preview_id: string | null;
  preview_is_current: boolean;
  competition_id: string | null;
  issues: Issue[];
  updated_at: string;
}

/** Propuesta inmutable del generador. No ha escrito nada en el mundo. */
export interface Preview {
  preview_id: string;
  schema_version: string;
  intent_fingerprint: string;
  ruleset_checksum: string;
  engine_version: string;
  seed: number;
  status: 'preview_ready' | 'preview_warning' | 'preview_blocked';
  context: GenerationPreview['context'] & {
    schedule: GenerationPreview['schedule'];
    budget_range: GenerationPreview['budget_range'];
    people_generated: number;
    free_agents: number;
    provenance: GenerationPreview['provenance'];
  };
  proposed_clubs: GenerationPreview['clubs'];
  issues: Issue[];
  committed_competition_id: string | null;
  note: string;
}

export interface ValidationResult {
  intent_fingerprint: string;
  blocking: Issue[];
  warnings: Issue[];
  can_commit: boolean;
}

export interface ApiError {
  code: string;
  message: string;
  suggestions: string[];
}
