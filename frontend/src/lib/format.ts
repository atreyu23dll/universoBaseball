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
  reserve_league: 'liga filial'
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
