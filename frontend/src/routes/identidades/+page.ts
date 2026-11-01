import { error } from '@sveltejs/kit';
import type { PageLoad } from './$types';

export type Quality = {
  score: number; contrast: number; balance: number; legibility: number;
  bounds: number; collisions: number; contour: number; hierarchy: number;
  symmetry: number; issues: string[]; size_scores: Record<string, number>;
};
export type IdentityCard = {
  index: number; seed: string; name: string; place: string; country: string;
  institution: string; year: number; grammar: string; concept: string; family: string;
  style: string; symbols: string[]; palette: Record<string,string>; rationale: string;
  quality: Record<string,Quality>;
};
export type Gallery = {
  seed: number; version: string; total: number; structures: number;
  unique_logos: number; items: IdentityCard[];
};

export const load: PageLoad = async ({ fetch, url }) => {
  const seed = Number(url.searchParams.get('seed') ?? '20261030');
  if (!Number.isInteger(seed) || seed < 0 || seed > 4294967295) error(400, 'Semilla fuera de rango.');
  const response = await fetch('/api/v1/identity-gallery?seed=' + seed);
  if (!response.ok) error(response.status, 'No se pudo generar la galería de identidades.');
  return { gallery: await response.json() as Gallery };
};
