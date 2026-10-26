<script lang="ts">
  import type { GameBrief } from '$lib/api/types';
  let { games }: { games:GameBrief[] } = $props();
  let compact=$state(false), stateFilter=$state('all');
  const filtered=$derived(stateFilter==='all'?games:games.filter((game)=>game.state===stateFilter));
  const days=$derived.by(()=>{const grouped=new Map<string,GameBrief[]>();for(const game of filtered){if(!grouped.has(game.game_date))grouped.set(game.game_date,[]);grouped.get(game.game_date)!.push(game)}return [...grouped.entries()].sort(([a],[b])=>a.localeCompare(b))});
  function dateParts(value:string){const date=new Date(`${value}T12:00:00`);return {weekday:new Intl.DateTimeFormat('es-MX',{weekday:'short'}).format(date),day:new Intl.DateTimeFormat('es-MX',{day:'numeric'}).format(date),month:new Intl.DateTimeFormat('es-MX',{month:'short'}).format(date)}}
</script>

<div class="calendar-tools"><div class="view-switch"><button class:active={!compact} onclick={()=>compact=false}>Cómodo</button><button class:active={compact} onclick={()=>compact=true}>Compacto</button></div><select bind:value={stateFilter} aria-label="Filtrar partidos"><option value="all">Todos los partidos</option><option value="scheduled">Programados</option><option value="final">Finalizados</option></select></div>
{#if days.length}
  <div class="calendar-scroll" class:compact><div class="calendar-grid">
    {#each days as [date,gamesForDay]}
      {@const parts=dateParts(date)}
      <section class="day-column"><header><span>{parts.weekday}</span><strong>{parts.day}</strong><b>{parts.month}</b><small>{gamesForDay.length} {gamesForDay.length===1?'partido':'partidos'}</small></header><div class="day-games">
        {#each gamesForDay as game}<a class="calendar-match" class:final={game.state==='final'} href={game.state==='final'?`/partidos/${game.id}`:'#'}><span>{game.state==='final'?'Final':game.stage==='playoffs'?'Playoffs':'Pendiente'}</span><div><strong>{game.away?.short_name}</strong><b>{game.away_score??'–'}</b></div><div><strong>{game.home?.short_name}</strong><b>{game.home_score??'–'}</b></div></a>{/each}
      </div></section>
    {/each}
  </div></div>
{:else}<div class="empty-state">No hay partidos con este filtro.</div>{/if}

<style>
  .calendar-tools{display:flex;justify-content:space-between;gap:10px;margin-bottom:10px}.calendar-tools select{width:auto;min-width:180px}.view-switch{display:flex;gap:3px;padding:3px;background:var(--panel);border:1px solid var(--line);border-radius:9px}.view-switch button{padding:6px 10px;background:transparent;color:var(--muted);box-shadow:none}.view-switch button.active{background:var(--accent-soft);color:var(--text)}.calendar-scroll{overflow-x:auto;padding-bottom:10px;scroll-snap-type:x proximity;scrollbar-color:var(--accent) var(--panel)}.calendar-grid{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(235px,1fr);gap:8px;width:max-content;min-width:100%}.day-column{scroll-snap-align:start;min-height:430px;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}.day-column>header{display:grid;grid-template-columns:auto 1fr;column-gap:7px;padding:11px 12px;background:var(--panel-2);border-bottom:1px solid var(--line)}.day-column header span{grid-column:1/-1;color:var(--accent-2);font-size:9px;text-transform:uppercase}.day-column header strong{grid-row:2/4;font:800 30px/1 var(--mono)}.day-column header b{font-size:12px;text-transform:capitalize}.day-column header small{color:var(--muted);font-size:9px}.day-games{display:grid;gap:6px;padding:8px}.calendar-match{display:block;padding:9px;color:var(--text);text-decoration:none;background:var(--panel-2);border:1px solid transparent;border-radius:8px}.calendar-match:hover{border-color:var(--accent)}.calendar-match>span{color:var(--muted);font-size:8px;text-transform:uppercase}.calendar-match.final>span{color:var(--accent-2)}.calendar-match div{display:flex;justify-content:space-between;gap:10px;font-size:11px}.calendar-match b{font-family:var(--mono)}.compact .calendar-grid{grid-auto-columns:minmax(175px,1fr)}.compact .day-column{min-height:300px}.compact .calendar-match{padding:6px}.compact .day-column>header{padding:8px 10px}.compact .day-column header strong{font-size:23px}@media(max-width:600px){.calendar-tools{align-items:stretch}.calendar-tools select{min-width:0}.calendar-grid{grid-auto-columns:82vw}}
</style>
