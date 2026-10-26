<script lang="ts">
  import type { GameBrief } from '$lib/api/types';
  let { games, label = 'Partidos de hoy' }: { games:GameBrief[]; label?:string } = $props();
  const loopGames=$derived(games.length>3?[...games,...games]:games);
</script>

<section class="ticker" aria-label={label}>
  <div class="ticker-label"><i></i><span>{label}</span></div>
  {#if games.length}
    <div class="track-wrap"><div class="track" class:animate={games.length>3}>
      {#each loopGames as game,index (`${game.id}-${index}`)}
        <a class="match" href={game.state==='final'?`/partidos/${game.id}`:'#'} aria-hidden={index>=games.length} tabindex={index>=games.length?-1:0}>
          <span class="state">{game.state==='final'?'Final':game.stage==='playoffs'?'Playoffs':'Programado'}</span>
          <div><strong>{game.away?.short_name}</strong><b>{game.away_score??'–'}</b></div>
          <div><strong>{game.home?.short_name}</strong><b>{game.home_score??'–'}</b></div>
        </a>
      {/each}
    </div></div>
  {:else}<div class="no-games">Sin partidos programados para esta fecha</div>{/if}
</section>

<style>
  .ticker{display:grid;grid-template-columns:115px minmax(0,1fr);min-height:76px;margin:10px 0 14px;background:var(--panel);border:1px solid var(--line);border-radius:11px;overflow:hidden}.ticker-label{display:flex;align-items:center;gap:7px;padding:12px;background:var(--accent-soft);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.ticker-label i{width:7px;height:7px;border-radius:50%;background:var(--accent-2);box-shadow:0 0 0 4px rgba(198,243,107,.1)}.track-wrap{overflow:hidden;mask-image:linear-gradient(90deg,transparent,#000 3%,#000 97%,transparent)}.track{display:flex;width:max-content;height:100%}.track.animate{animation:scroll 32s linear infinite}.track:hover{animation-play-state:paused}.match{display:flex;flex-direction:column;justify-content:center;width:175px;padding:8px 14px;color:var(--text);text-decoration:none;border-right:1px solid var(--line)}.match:hover{background:var(--panel-2)}.match .state{color:var(--muted);font-size:8px;text-transform:uppercase}.match div{display:flex;justify-content:space-between;gap:15px;font-size:11px}.match b{font-family:var(--mono)}.no-games{display:flex;align-items:center;padding:15px;color:var(--muted);font-size:11px}@keyframes scroll{to{transform:translateX(-50%)}}@media(prefers-reduced-motion:reduce){.track.animate{animation:none}.track-wrap{overflow-x:auto}}@media(max-width:600px){.ticker{grid-template-columns:1fr}.ticker-label{padding:7px 12px}.track-wrap{overflow-x:auto}.track.animate{animation:none}}
</style>
