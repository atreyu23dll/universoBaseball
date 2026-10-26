<script lang="ts">
  import Crest from './Crest.svelte';
  import { formatPct } from '$lib/format';
  import type { StandingRow } from '$lib/api/types';
  let { rows, mobility = null }: { rows: StandingRow[]; mobility?: any } = $props();
  function zone(id?: string) {
    if (!id || !mobility?.projected?.some((item: any) => item.club_id === id)) return '';
    return mobility.direction === 'promoted' ? '▲' : '▼';
  }
</script>

<div class="ranking-list">
  {#each rows as row (row.club?.id)}
    <article class="ranking-card">
      <div class="ranking-position">{row.group_rank || row.rank}</div>
      <div class="row" style="min-width:0;flex-wrap:nowrap">
        {#if row.club}<Crest primary={row.club.primary_color} secondary={row.club.secondary_color} shape={row.club.crest_shape} motif={row.club.crest_motif} size={30} />{/if}
        <div style="min-width:0"><a href={`/clubes/${row.club?.id}`}><strong>{row.club?.name}</strong></a><div class="small muted">{row.group || row.streak || 'Liga'}</div></div>
      </div>
      <div class="metric"><strong>{row.wins}–{row.losses}</strong><small>Récord</small></div>
      <div class="metric"><strong>{formatPct(row.win_pct)}</strong><small>PCT</small></div>
      <div class="metric"><strong>{row.run_differential > 0 ? '+' : ''}{row.run_differential}</strong><small>Diferencial</small></div>
      <div class="metric"><strong>{row.home_record}</strong><small>Casa</small></div>
      <div class="metric"><strong>{row.away_record}</strong><small>Fuera {zone(row.club?.id)}</small></div>
    </article>
  {/each}
</div>
