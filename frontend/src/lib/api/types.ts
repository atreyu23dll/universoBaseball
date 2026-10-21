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
  competitions: Array<{
    id: string;
    name: string;
    kind: string;
    scope_level: string;
    relationship_mode: string;
    editions: EditionBrief[];
  }>;
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

export interface GenerationPreview {
  ruleset_checksum: string;
  seed: number;
  context: {
    professionalization_score: number;
    professionalization_tier: string;
    economy_score: number;
    maturity_score: number;
    aggregate_population: number;
    currency: string;
    talent_mean: number;
    markets: MarketPreview[];
  };
  clubs: Array<{
    name: string;
    place: string;
    institutional_type: string;
    annual_budget: string;
    venue_name: string;
    venue_type: string;
    capacity: number;
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
      world_date: string | null;
      notes: string[];
    };
    error: string | null;
  } | null;
}

export interface Place {
  key: string;
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

export interface ApiError {
  code: string;
  message: string;
  suggestions: string[];
}
