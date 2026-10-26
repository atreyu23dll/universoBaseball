<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import type { Dashboard, SimStatus } from '$lib/api/types';
  import { formatDate, formatNumber, KIND_LABEL, SCOPE_LABEL } from '$lib/format';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';
  import WorldClock from '$lib/components/WorldClock.svelte';
  import MatchTicker from '$lib/components/MatchTicker.svelte';

  const universeId = $derived($page.params.id);

  let dashboard = $state<Dashboard | null>(null);
  let status = $state<SimStatus | null>(null);
  let error = $state<unknown>(null);
  let advancing = $state(false);
  let newsVisible = $state(8);
  let resultsVisible = $state(8);
  let newsSentinel = $state<HTMLDivElement>();
  let resultsSentinel = $state<HTMLDivElement>();
  let poller: ReturnType<typeof setInterval> | null = null;

  async function loadDashboard() {
    try {
      dashboard = await api.get<Dashboard>(`/universes/${universeId}/dashboard`);
      error = null;
    } catch (err) {
      error = err;
    }
  }

  async function loadStatus() {
    try {
      status = await api.get<SimStatus>(`/universes/${universeId}/sim/status`);
    } catch (err) {
      error = err;
    }
  }

  /** El avance corre en el servidor; aquí solo se sondea el estado.
   *  Cerrar esta pestaña no cancela nada. */
  function startPolling() {
    stopPolling();
    poller = setInterval(async () => {
      await loadStatus();
      if (status && !status.busy && status.job?.status !== 'running') {
        stopPolling();
        advancing = false;
        await loadDashboard();
      }
    }, 700);
  }

  function stopPolling() {
    if (poller) clearInterval(poller);
    poller = null;
  }

  async function advance(days: number, untilSeasonEnd = false) {
    advancing = true;
    error = null;
    try {
      await api.post(
        `/universes/${universeId}/sim/advance`,
        { days, until_season_end: untilSeasonEnd },
        { 'Idempotency-Key': `${universeId}:${untilSeasonEnd ? 'season' : days}:${Date.now()}` }
      );
      startPolling();
    } catch (err) {
      error = err;
      advancing = false;
    }
  }

  onMount(async () => {
    await Promise.all([loadDashboard(), loadStatus()]);
    if (status?.busy) startPolling();
  });
  onDestroy(stopPolling);
  $effect(() => {
    const targets = [[newsSentinel, () => newsVisible += 8], [resultsSentinel, () => resultsVisible += 8]] as const;
    const observers = targets.flatMap(([element, more]) => {
      if (!element) return [];
      const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) more(); }, { rootMargin: '180px' });
      observer.observe(element);
      return [observer];
    });
    return () => observers.forEach((observer) => observer.disconnect());
  });
</script>

{#if dashboard}
  <div class="spread" style="margin-bottom:18px">
    <div>
      <h1>{dashboard.universe.name}</h1>
      <p class="muted small" style="margin:0">
        Semilla <span class="mono">{dashboard.universe.master_seed}</span>
        · motor <span class="mono">{dashboard.universe.sim_version}</span>
        · fixture geográfico <span class="mono">{dashboard.universe.fixture_version}</span>
      </p>
    </div>
    <div class="row">
      <a class="button ghost" href={`/universos/${universeId}/crear-liga`}>Crear competición</a>
      <a class="button ghost" href={`/universos/${universeId}/geografia`}>Geografía</a>
      <a class="button ghost" href={`/universos/${universeId}/clubes`}>Clubes</a>
    </div>
  </div>

  <ErrorNotice {error} />

  <WorldClock date={dashboard.universe.world_date} busy={advancing || status?.busy} job={status?.job} onadvance={advance} />

  <div class="universe-stats">
        <div class="stat">
          <div class="value">{formatNumber(dashboard.counts.games_played)}</div>
          <div class="label">partidos jugados</div>
        </div>
        <div class="stat">
          <div class="value">{formatNumber(dashboard.counts.games_pending)}</div>
          <div class="label">pendientes</div>
        </div>
        <div class="stat">
          <div class="value">{formatNumber(dashboard.counts.clubs)}</div>
          <div class="label">clubes</div>
        </div>
        <div class="stat">
          <div class="value">{formatNumber(dashboard.counts.people)}</div>
          <div class="label">personas</div>
        </div>
  </div>
  <MatchTicker games={dashboard.today} label={`Partidos · ${formatDate(dashboard.universe.world_date)}`} />

  <div class="grid sidebar">
    <div>
      <div class="panel">
        <div class="section-title"><div><h2>Ligas</h2><p class="small">Elige una liga y entra a su temporada activa.</p></div></div>
        {#if dashboard.competitions.length === 0}
          <p class="muted small">
            Ninguna todavía. El único acto creativo necesario es definir una
            competición: lo demás lo genera el motor.
          </p>
          <a class="button" href={`/universos/${universeId}/crear-liga`}>Crear la primera</a>
        {:else}
          <div class="card-grid">
            {#each dashboard.competitions as competition (competition.id)}
              {@const activeEdition = competition.editions.at(-1)}
              <a class="entity-card" href={activeEdition ? `/ediciones/${activeEdition.id}` : `/universos/${universeId}/crear-liga`}>
                <div class="spread"><div class="icon-box">⚾</div><span class={competition.relationship_mode === 'independent' ? 'tag accent' : 'tag warn'}>{competition.relationship_mode === 'independent' ? 'Independiente' : 'Sistema de ligas'}</span></div>
                <h2>{competition.name}</h2>
                <p class="small muted">{KIND_LABEL[competition.kind] ?? competition.kind} · {SCOPE_LABEL[competition.scope_level] ?? competition.scope_level}</p>
                <div class="card-meta">
                  <div><strong>{competition.editions.length}</strong><span>Ediciones</span></div>
                  <div><strong>{activeEdition?.year ?? '—'}</strong><span>Temporada</span></div>
                  <div><strong>{activeEdition?.stage === 'completed' ? 'Final' : 'Activa'}</strong><span>Estado</span></div>
                </div>
              </a>
            {/each}
          </div>
        {/if}
      </div>

      <div class="panel">
        <h2>Resultados recientes</h2>
        {#if dashboard.recent_results.length === 0}
          <p class="muted small">Todavía no se ha jugado nada. Avanza el reloj.</p>
        {:else}
          <div class="feed-list">
              {#each dashboard.recent_results.slice(0, resultsVisible) as game (game.id)}
                <div class="game-card">
                  <div class="small muted">{formatDate(game.game_date)}</div>
                  <div>
                    <a href={`/partidos/${game.id}`}>
                      {game.away?.short_name} {game.away_score} – {game.home_score} {game.home?.short_name}
                    </a>
                    {#if (game.innings_played ?? 9) > 9}
                      <span class="tag">{game.innings_played} entradas</span>
                    {/if}
                  </div>
                  <span class="tag accent">Final</span>
                </div>
              {/each}
          </div>
          <div bind:this={resultsSentinel} class="infinite-sentinel">{resultsVisible < dashboard.recent_results.length ? 'Cargando más resultados…' : 'Resultados recientes completos'}</div>
        {/if}
      </div>
    </div>

    <div>
      <div class="panel">
        <h2>Acontecimientos</h2>
        {#if dashboard.news.length === 0}
          <p class="muted small">Sin noticias: el mundo no ha pasado nada todavía.</p>
        {:else}
          <div class="news-feed">
          {#each dashboard.news.slice(0, newsVisible) as item}
            <article class="news-card">
              <div class="small muted mono">{formatDate(item.world_date)}</div>
              <div class="small">{item.headline}</div>
            </article>
          {/each}
          </div>
          <div bind:this={newsSentinel} class="infinite-sentinel">{newsVisible < dashboard.news.length ? 'Cargando más acontecimientos…' : 'Acontecimientos al día'}</div>
        {/if}
      </div>
      <div class="panel">
        <h2>Grafo de competiciones</h2>
        <p class="small muted">
          Se distinguen las relaciones jerárquicas de las rutas de clasificación.
        </p>
        <a class="button ghost" href={`/universos/${universeId}/grafo`}>Abrir el grafo</a>
      </div>
    </div>
  </div>
{:else}
  <ErrorNotice {error} />
  {#if !error}<p class="muted">Cargando universo…</p>{/if}
{/if}

<style>
  .universe-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:10px 0 14px}.news-feed{display:grid;gap:7px}.news-card{padding:10px 11px;background:var(--panel-2);border:1px solid var(--line);border-radius:9px}.news-card div+div{margin-top:3px}@media(max-width:700px){.universe-stats{grid-template-columns:1fr 1fr}}
</style>
