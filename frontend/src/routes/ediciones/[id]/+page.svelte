<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import type { GameBrief, MobilityProjection, StandingRow } from '$lib/api/types';
  import { formatDate, formatNumber, KIND_LABEL, SCOPE_LABEL } from '$lib/format';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';
  import StandingsCards from '$lib/components/StandingsCards.svelte';
  import TeamsGrid from '$lib/components/TeamsGrid.svelte';
  import CalendarBoard from '$lib/components/CalendarBoard.svelte';
  import LeaderCards from '$lib/components/LeaderCards.svelte';

  const editionId = $derived($page.params.id);
  const tabs = [['general','General'],['equipos','Equipos'],['standings','Standings'],['calendario','Calendario'],['estadisticas','Estadísticas']] as const;
  let detail=$state<any>(null), standings=$state<StandingRow[]>([]), schedule=$state<GameBrief[]>([]), leaders=$state<any>(null), mobility=$state<MobilityProjection|null>(null);
  let error=$state<unknown>(null), tab=$state<(typeof tabs)[number][0]>('general');
  const featuredGames=$derived(schedule.filter((g)=>g.state==='final').slice(-3).reverse());
  onMount(async()=>{try{const[d,s,sc,ld,mb]=await Promise.all([api.get<any>(`/editions/${editionId}`),api.get<{items:StandingRow[]}>(`/editions/${editionId}/standings`),api.get<{items:GameBrief[]}>(`/editions/${editionId}/schedule?limit=500`),api.get<any>(`/editions/${editionId}/leaders`),api.get<MobilityProjection>(`/editions/${editionId}/mobility-projection`)]);detail=d;standings=s.items;schedule=sc.items;leaders=ld;mobility=mb}catch(err){error=err}});
</script>

<ErrorNotice {error}/>
{#if detail}
  <section class="league-hero"><div class="kicker">{KIND_LABEL[detail.competition.kind]??detail.competition.kind} · {SCOPE_LABEL[detail.competition.scope_level]??detail.competition.scope_level}</div><div class="spread"><div><h1>{detail.competition.name}</h1><p class="muted">Temporada {detail.year} · {formatDate(detail.start_date)} — {formatDate(detail.end_date)}</p></div>{#if detail.champion}<div class="champion"><span>Campeón</span><strong>{detail.champion.name}</strong></div>{/if}</div></section>
  <nav class="tabs" aria-label="Secciones de la liga">{#each tabs as [value,label]}<button class:active={tab===value} onclick={()=>tab=value}>{label}</button>{/each}</nav>
  {#if tab==='general'}
    <div class="grid three"><div class="stat"><div class="value">{standings.length}</div><div class="label">equipos</div></div><div class="stat"><div class="value">{formatNumber(schedule.length)}</div><div class="label">partidos</div></div><div class="stat"><div class="value">{detail.structure?.count??1}</div><div class="label">divisiones</div></div></div>
    <div class="grid sidebar" style="margin-top:18px"><section class="panel"><h2>Así va la liga</h2><StandingsCards rows={standings.slice(0,5)} {mobility}/><button class="ghost" style="margin-top:14px" onclick={()=>tab='standings'}>Ver ranking completo</button></section><section class="panel"><h2>Últimos partidos</h2><div class="feed-list">{#each featuredGames as game}<a class="soft-card" href={`/partidos/${game.id}`}><div class="small muted">{formatDate(game.game_date)}</div><strong>{game.away?.short_name} {game.away_score} — {game.home_score} {game.home?.short_name}</strong></a>{/each}</div></section></div>
  {:else if tab==='equipos'}
    <div class="section-title"><div><h2>Equipos</h2><p>Entra al perfil de un club para consultar su estadio y estructura.</p></div></div><TeamsGrid rows={standings}/>
  {:else if tab==='standings'}
    <div class="section-title"><div><h2>Standings</h2><p>Clasificación visual de la temporada.</p></div></div>
    {#each detail.structure?.groups??[{label:''}] as group}{@const rows=group.label?standings.filter((row)=>row.group===group.label):standings}{#if group.label}<h2 style="margin-top:24px">{group.label}</h2>{/if}<StandingsCards {rows} {mobility}/>{/each}
  {:else if tab==='calendario'}
    <div class="section-title"><div><h2>Calendario</h2><p>Cada columna representa un día de competición. Desliza horizontalmente para recorrer la temporada.</p></div></div><CalendarBoard games={schedule}/>
  {:else if tab==='estadisticas'}
    <div class="section-title"><div><h2>Líderes de la temporada</h2><p>{leaders?.qualification_note}</p></div></div><LeaderCards {leaders}/>
  {/if}
{:else if !error}<div class="empty-state">Cargando la liga…</div>{/if}

<style>.league-hero{padding:16px 0 4px}.kicker{color:var(--accent-2);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.12em}.league-hero p{margin:0}.champion{padding:9px 13px;background:rgba(198,243,107,.07);border:1px solid rgba(198,243,107,.2);border-radius:10px}.champion span,.champion strong{display:block}.champion span{font-size:9px;color:var(--accent-2);text-transform:uppercase}</style>
