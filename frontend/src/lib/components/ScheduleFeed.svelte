<script lang="ts">
  import { onMount } from 'svelte';
  import { formatDate } from '$lib/format';
  import type { GameBrief } from '$lib/api/types';
  let { games }: { games: GameBrief[] } = $props();
  let visible = $state(20); let sentinel: HTMLDivElement;
  onMount(() => { const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) visible = Math.min(visible + 20, games.length); }, { rootMargin: '240px' }); observer.observe(sentinel); return () => observer.disconnect(); });
</script>
<div class="feed-list">
  {#each games.slice(0, visible) as game (game.id)}
    <article class="game-card">
      <div><strong>{formatDate(game.game_date)}</strong><div class="small muted">{game.stage === 'playoffs' ? 'Postemporada' : 'Temporada regular'}</div></div>
      <div class="team-pair"><span>{game.away?.short_name}</span><span class="score-pill">{game.away_score ?? '–'} : {game.home_score ?? '–'}</span><span>{game.home?.short_name}</span></div>
      {#if game.state === 'final'}<a class="button ghost" href={`/partidos/${game.id}`}>Ver partido</a>{:else}<span class="tag">Programado</span>{/if}
    </article>
  {/each}
</div>
<div bind:this={sentinel} class="infinite-sentinel">{visible < games.length ? 'Cargando más partidos…' : `${games.length} partidos mostrados`}</div>
