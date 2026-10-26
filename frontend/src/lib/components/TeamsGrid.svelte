<script lang="ts">
  import Crest from './Crest.svelte';
  import type { StandingRow } from '$lib/api/types';
  let { rows }: { rows: StandingRow[] } = $props();
</script>
<div class="card-grid">
  {#each rows as row (row.club?.id)}
    {#if row.club}
      <a class="entity-card" href={`/clubes/${row.club.id}`}>
        <Crest primary={row.club.primary_color} secondary={row.club.secondary_color} shape={row.club.crest_shape} motif={row.club.crest_motif} size={52} />
        <h2>{row.club.name}</h2><p class="muted small">{row.group || 'Competición general'}</p>
        <div class="card-meta"><div><strong>{row.wins}</strong><span>Ganados</span></div><div><strong>{row.losses}</strong><span>Perdidos</span></div><div><strong>#{row.rank}</strong><span>Posición</span></div></div>
      </a>
    {/if}
  {/each}
</div>
<style>.entity-card{width:100%;text-align:left}</style>
