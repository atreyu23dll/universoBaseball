<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import type { Dashboard, SimStatus } from '$lib/api/types';
  import { formatDate, formatNumber, KIND_LABEL, SCOPE_LABEL } from '$lib/format';
  import Crest from '$lib/components/Crest.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const universeId = $derived($page.params.id);

  let dashboard = $state<Dashboard | null>(null);
  let status = $state<SimStatus | null>(null);
  let error = $state<unknown>(null);
  let advancing = $state(false);
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
</script>

{#if dashboard}
  <div class="spread" style="margin-bottom:18px">
    <div>
      <h1>{dashboard.universe.name}</h1>
      <p class="muted small" style="margin:0">
        Fecha del mundo <strong>{formatDate(dashboard.universe.world_date)}</strong>
        · semilla <span class="mono">{dashboard.universe.master_seed}</span>
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

  <div class="panel">
    <div class="spread">
      <div>
        <h3 style="margin-bottom:6px">Reloj del mundo</h3>
        <div class="row">
          <button onclick={() => advance(1)} disabled={advancing}>+1 día</button>
          <button onclick={() => advance(7)} disabled={advancing}>+1 semana</button>
          <button onclick={() => advance(30)} disabled={advancing}>+30 días</button>
          <button class="ghost" onclick={() => advance(1, true)} disabled={advancing}>
            Hasta fin de temporada
          </button>
        </div>
      </div>
      <div class="row">
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
    </div>

    {#if status?.job}
      <div class="notice info" style="margin-top:14px">
        Trabajo <span class="mono">{status.job.id.slice(0, 8)}</span>:
        <strong>{status.job.status}</strong>
        — {status.job.progress.days_done}/{status.job.progress.days_requested} días,
        {status.job.progress.games_played} partidos simulados.
        {#if status.job.error}<br /><span style="color:var(--danger)">{status.job.error}</span>{/if}
        {#if status.job.progress.notes.length}
          <br /><span class="muted">{status.job.progress.notes.join(' · ')}</span>
        {/if}
      </div>
    {/if}
  </div>

  <div class="grid sidebar">
    <div>
      <div class="panel">
        <h2>Competiciones</h2>
        {#if dashboard.competitions.length === 0}
          <p class="muted small">
            Ninguna todavía. El único acto creativo necesario es definir una
            competición: lo demás lo genera el motor.
          </p>
          <a class="button" href={`/universos/${universeId}/crear-liga`}>Crear la primera</a>
        {:else}
          <table>
            <thead>
              <tr>
                <th>Competición</th>
                <th>Tipo</th>
                <th>Alcance</th>
                <th>Relación</th>
                <th>Ediciones</th>
              </tr>
            </thead>
            <tbody>
              {#each dashboard.competitions as competition (competition.id)}
                <tr>
                  <td>{competition.name}</td>
                  <td class="small">{KIND_LABEL[competition.kind] ?? competition.kind}</td>
                  <td class="small">{SCOPE_LABEL[competition.scope_level] ?? competition.scope_level}</td>
                  <td>
                    <span class={competition.relationship_mode === 'independent' ? 'tag accent' : 'tag warn'}>
                      {competition.relationship_mode === 'independent' ? 'independiente' : 'dependiente'}
                    </span>
                  </td>
                  <td class="small">
                    {#if competition.editions.length === 0}
                      <span class="muted">sin generar</span>
                    {:else}
                      {#each competition.editions as edition (edition.id)}
                        <div>
                          <a href={`/ediciones/${edition.id}`}>{edition.year}</a>
                          <span class="tag">{edition.stage}</span>
                          {#if edition.champion}
                            <span class="tag accent">campeón: {edition.champion}</span>
                          {/if}
                        </div>
                      {/each}
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>

      <div class="panel">
        <h2>Partidos del día {formatDate(dashboard.universe.world_date)}</h2>
        {#if dashboard.today.length === 0}
          <p class="muted small">No hay nada programado para hoy.</p>
        {:else}
          <table>
            <tbody>
              {#each dashboard.today as game (game.id)}
                <tr>
                  <td>
                    <div class="scorebox">
                      {#if game.away}
                        <Crest primary={game.away.primary_color} secondary={game.away.secondary_color}
                               shape={game.away.crest_shape} motif={game.away.crest_motif} size={20} />
                        <span>{game.away.short_name}</span>
                      {/if}
                      <span class="score">{game.away_score ?? '–'}</span>
                      <span class="muted">en</span>
                      {#if game.home}
                        <Crest primary={game.home.primary_color} secondary={game.home.secondary_color}
                               shape={game.home.crest_shape} motif={game.home.crest_motif} size={20} />
                        <span>{game.home.short_name}</span>
                      {/if}
                      <span class="score">{game.home_score ?? '–'}</span>
                    </div>
                  </td>
                  <td class="small muted">{game.stage === 'playoffs' ? `postemporada ${game.series_key}` : ''}</td>
                  <td style="text-align:right">
                    {#if game.state === 'final'}
                      <a class="small" href={`/partidos/${game.id}`}>ver resumen</a>
                    {:else}
                      <span class="tag">programado</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>

      <div class="panel">
        <h2>Resultados recientes</h2>
        {#if dashboard.recent_results.length === 0}
          <p class="muted small">Todavía no se ha jugado nada. Avanza el reloj.</p>
        {:else}
          <table>
            <tbody>
              {#each dashboard.recent_results as game (game.id)}
                <tr>
                  <td class="small muted">{formatDate(game.game_date)}</td>
                  <td>
                    <a href={`/partidos/${game.id}`}>
                      {game.away?.short_name} {game.away_score} – {game.home_score} {game.home?.short_name}
                    </a>
                    {#if (game.innings_played ?? 9) > 9}
                      <span class="tag">{game.innings_played} entradas</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    </div>

    <div>
      <div class="panel">
        <h2>Acontecimientos</h2>
        {#if dashboard.news.length === 0}
          <p class="muted small">Sin noticias: el mundo no ha pasado nada todavía.</p>
        {:else}
          {#each dashboard.news as item}
            <div style="padding:8px 0; border-bottom:1px solid var(--line)">
              <div class="small muted mono">{formatDate(item.world_date)}</div>
              <div class="small">{item.headline}</div>
            </div>
          {/each}
          <p class="small muted" style="margin-top:10px">
            Cada titular se deriva de un evento que el motor registró. Ninguno se
            inventa.
          </p>
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
