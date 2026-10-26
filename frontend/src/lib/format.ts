/** Formateo compartido. El idioma de la interfaz es el castellano. */

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const [year, month, day] = value.split('-').map(Number);
  return new Intl.DateTimeFormat('es-MX', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  }).format(new Date(year, month - 1, day));
}

export function formatMoney(value: string | number, currency: string): string {
  const amount = typeof value === 'string' ? Number(value) : value;
  if (!Number.isFinite(amount)) return '—';
  return new Intl.NumberFormat('es-MX', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0
  }).format(amount);
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('es-MX').format(value);
}

export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toFixed(3).replace(/^0/, '');
}

/** Etiqueta legible del grado de confianza de un dato. */
export const CONFIDENCE_LABEL: Record<string, string> = {
  observed: 'dato observado',
  estimated: 'estimación',
  scenario_assumption: 'supuesto declarado',
  missing: 'sin datos',
  fictional: 'ficticio',
  user_configured: 'configurado por ti'
};

export const SCOPE_LABEL: Record<string, string> = {
  municipal: 'municipal',
  regional: 'regional',
  national: 'nacional',
  multinational: 'multinacional'
};

export const KIND_LABEL: Record<string, string> = {
  municipal_league: 'liga municipal',
  regional_league: 'liga regional',
  national_league: 'liga nacional',
  domestic_league: 'liga doméstica',
  international_club_league: 'liga internacional de clubes',
  domestic_cup: 'copa doméstica',
  continental_club_cup: 'copa continental de clubes',
  youth_league: 'liga juvenil',
  reserve_league: 'liga filial',
  educational_league: 'liga escolar / formativa'
};

/** Estados del borrador de competición (FIX V2 §12.1). */
export const DRAFT_STATE_LABEL: Record<string, string> = {
  draft: 'borrador',
  geography_pending: 'falta resolver el territorio',
  geography_resolved: 'territorio resuelto',
  context_ready: 'listo para previsualizar',
  preview_ready: 'propuesta lista',
  preview_warning: 'propuesta con advertencias',
  preview_blocked: 'propuesta bloqueada',
  committed: 'creada'
};

/** Códigos de problema del §10.4, en lenguaje de persona. */
export const ISSUE_CODE_LABEL: Record<string, string> = {
  RULESET_INVALID: 'reglamento inválido',
  GEOGRAPHY_UNRESOLVED: 'territorio sin resolver',
  GEOGRAPHY_AMBIGUOUS: 'territorio ambiguo',
  GEOGRAPHY_BOUNDARY_MISSING: 'sin límite administrativo',
  ELIGIBILITY_INVALID_AGE_RANGE: 'rango de edad imposible',
  MINOR_SAFEGUARDING_REQUIRED: 'salvaguarda de menores',
  PARTICIPANTS_INFEASIBLE: 'participantes inviables',
  REGIONAL_TALENT_SHORTAGE: 'falta de jugadores en la zona',
  SCHEDULE_UNSATISFIABLE: 'calendario irrealizable',
  VENUE_CONFLICT: 'conflicto de instalaciones',
  ADMISSION_REQUIREMENTS_INCONSISTENT: 'requisitos incoherentes',
  HIERARCHY_INVALID_LINK: 'vínculo inválido',
  CONTEXT_DATA_UNCERTAIN: 'datos del entorno inciertos',
  UNEXPLAINED_BUDGET: 'presupuesto sin sostener',
  INSUFFICIENT_RESOURCE_EVIDENCE: 'faltan datos económicos',
  PREVIEW_BLOCKED: 'propuesta bloqueada',
  DEPRECATED_CLUB_GENERATION_FIELD: 'campo retirado'
};

export const GEO_KIND_LABEL: Record<string, string> = {
  country: 'país',
  region: 'región',
  city: 'localidad',
  district: 'barrio'
};

/** Etiquetas de confianza del FIX V2: el supuesto no es un dato. */
export const GEO_CONFIDENCE_LABEL: Record<string, string> = {
  observed: 'dato con fuente',
  estimated: 'estimación',
  scenario_assumption: 'supuesto declarado',
  missing: 'sin datos',
  fictional: 'ficticio',
  user_configured: 'configurado por ti'
};

export const MODALITY_LABEL: Record<string, string> = {
  llanera: 'llanera',
  amateur_organized: 'amateur organizada',
  school_formative: 'escolar / formativa',
  semi_professional: 'semiprofesional',
  professional: 'profesional'
};

/** Formas de gobierno que el motor genera. Ninguna la elige el usuario. */
export const GOVERNANCE_LABEL: Record<string, string> = {
  collective: 'colectivo sin propietario',
  members_assembly: 'asociación de socios',
  family_private: 'proyecto familiar',
  business_backed: 'respaldado por un negocio',
  school_program: 'programa escolar',
  municipal_program: 'programa municipal',
  foundation: 'fundación',
  sports_company: 'sociedad deportiva',
  franchise: 'franquicia'
};

export const VENUE_USAGE_LABEL: Record<string, string> = {
  public_shared: 'campo público compartido',
  school_facility: 'instalación escolar',
  rented: 'sede alquilada',
  owned: 'instalación propia',
  itinerant: 'sin sede fija'
};

/** Nivel de recursos ya calculado. Es una lectura, no una categoría elegida. */
export const RESOURCE_TIER_LABEL: Record<string, string> = {
  subsistence: 'de subsistencia',
  modest: 'modesto',
  established: 'establecido',
  well_resourced: 'con recursos',
  major: 'de gran escala'
};

/** Cómo se repartieron los clubes entre los grupos de una competición. */
export const GROUP_ASSIGNMENT_LABEL: Record<string, string> = {
  geographic: 'por cercanía geográfica',
  balanced: 'repartiendo los clubes con más recursos',
  declared: 'con los grupos y plazas que declaró el usuario'
};

export const OUTCOME_LABEL: Record<string, string> = {
  healthy: 'cerró en orden',
  strained: 'cerró en apuros',
  insolvent: 'no pudo cubrir sus obligaciones'
};

/** Qué cambió en una institución entre temporadas. */
export const CHANGE_FIELD_LABEL: Record<string, string> = {
  fan_base: 'base social',
  governance: 'forma de gobierno',
  venue_agreement: 'uso de la sede',
  community_reach: 'alcance en su zona'
};

export const COMPONENT_LABEL: Record<string, string> = {
  revenue: 'ingreso',
  expense: 'gasto'
};

export const FINANCIAL_CONFIDENCE_LABEL: Record<string, string> = {
  estimated: 'estimado',
  scenario_assumption: 'supuesto de escenario',
  insufficient_data: 'datos insuficientes'
};

export const TIER_LABEL: Record<string, string> = {
  amateur: 'amateur',
  semi_professional: 'semiprofesional',
  professional: 'profesional',
  elite: 'élite'
};

export const INSTITUTION_LABEL: Record<string, string> = {
  community: 'comunitario',
  corporate: 'empresarial',
  university: 'universitario',
  municipal: 'municipal',
  private: 'privado',
  franchise: 'franquicia'
};

export const VENUE_LABEL: Record<string, string> = {
  neighborhood_field: 'campo de barrio',
  amateur_park: 'parque amateur',
  professional_stadium: 'estadio profesional',
  multipurpose_complex: 'complejo multiusos'
};
