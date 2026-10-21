<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import type { GameBrief, StandingRow } from '$lib/api/types';
  import { formatDate, formatPct, KIND_LABEL, SCOPE_LABEL } from '$lib/format';
  import Crest from '$lib/components/Crest.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const editionId = $derived($page.params.id);

  let detail = $state<any>(null);
  let standings = $state<StandingRow[]>([]);
  let schedule = $state<GameBrief[]>([]);
  let playoffs = $state<any[]>([]);
  let leaders = $state<any>(null);
  let error = $state<unknown>(null);
  let tab = $state<'tabla' | 'calendario' | 'postemporada' | 'lideres' | 'reglas'>('tabla');

  onMount(async () => {
    try {
      const [d, s, sc, po, ld] = await Promise.all([
        api.get<any>(`/editions/${editionId}`),
        api.get<{ items: StandingRow[] }>(`/editions/${editionId}/standings`),
        api.get<{ items: GameBrief[] }>(`/editions/${editionId}/schedule?limit=200`),
        api.get<{ items: any[] }>(`/editions/${editionId}/playoffs`),
        api.get<any>(`/editions/${editionId}/leaders`)
      ]);
      detail = d;
      standings = s.items;
      schedule = sc.items;
      playoffs = po.items;
      leaders = ld;
    } catch (err) {
      error = err;
    }
  });
</script>

<ErrorNotice {error} />

{#if detail}
  <div class="spread" style="margin-bottom:16px">
    <div>
      <h1>{detail.competition.name} · {detail.year}</h1>
      <p class="muted small" style="margin:0">
        {KIND_LABEL[detail.competition.kind] ?? detail.competition.kind}
        · alcance {SCOPE_LABEL[detail.competition.scope_level] ?? detail.competition.scope_level}
        · <span class={detail.competition.relationship_mode === 'independent' ? 'tag accent' : 'tag warn'}>
            {detail.competition.relationship_mode === 'independent' ? 'independiente' : 'dependiente'}
          </span>
        · {formatDate(detail.start_date)} → {formatDate(detail.end_date)}
        · <span class="tag">{detail.stage}</span>
      </p>
    </div>
    {#if detail.champion}
      <div class="stat">
        <div class="value" style="font-size:16px">{detail.champion.name}</div>
        <div class="label">campeón de la edición</div>
      </div>
    {/if}
  </div>

  {#each detail.warnings as warning}
    <div class="notice">{warning}</div>
  {/each}

  <div class="row" style="margin-bottom:14px">
    {#each [['tabla', 'Clasificación'], ['calendario', 'Calendario'], ['postemporada', 'Postemporada'], ['lideres', 'Líderes'], ['reglas', 'Reglamento']] as [value, label]}
      <button class={tab === value ? 'button' : 'button ghost'} onclick={() => (tab = value as any)}>
        {label}
      </button>
    {/each}
  </div>

  {#if tab === 'tabla'}
    <div class="panel">
      <h2>Clasificación</h2>
      <table>
        <thead>
          <tr>
            <th class="num">#</th>
            <th>Club</th>
            <th class="num">PJ</th>
            <th class="num">G</th>
            <th class="num">P</th>
            <th class="num">PCT</th>
            <th class="num">CF</th>
            <th class="num">CC</th>
            <th class="num">DIF</th>
            <th>Casa</th>
            <th>Fuera</th>
            <th>Racha</th>
            <th>Desempate</th>
          </tr>
        </thead>
        <tbody>
          {#each standings as row (row.club?.id)}
            <tr>
              <td class="num">{row.rank}</td>
              <td>
                <span class="row" style="gap:8px">
                  {#if row.club}
                    <Crest primary={row.club.primary_color} secondary={row.club.secondary_color}
                           shape={row.club.crest_shape} motif={row.club.crest_motif} size={18} />
                    <a href={`/clubes/${row.club.id}`}>{row.club.name}</a>
                  {/if}
                </span>
              </td>
              <td class="num">{row.played}</td>
              <td class="num">{row.wins}</td>
              <td class="num">{row.losses}</td>
              <td class="num">{formatPct(row.win_pct)}</td>
              <td class="num">{row.runs_for}</td>
              <td class="num">{row.runs_against}</td>
              <td class="num">{row.run_differential > 0 ? '+' : ''}{row.run_differential}</td>
              <td class="num">{row.home_record}</td>
              <td class="num">{row.away_record}</td>
              <td class="num">{row.streak}</td>
              <td class="small muted">{row.tiebreak_note}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="small muted">
        Se recalcula desde los partidos terminados en cada avance, no se acumula.
        Los empates valen media victoria en el porcentaje.
      </p>
    </div>
  {:else if tab === 'calendario'}
    <div class="panel">
      <h2>Calendario</h2>
      <table>
        <thead>
          <tr><th>Fecha</th><th>Encuentro</th><th>Etapa</th><th>Estado</th></tr>
        </thead>
        <tbody>
          {#each schedule as game (game.id)}
            <tr>
              <td class="small">{formatDate(game.game_date)}</td>
              <td>
                {#if game.state === 'final'}
                  <a href={`/partidos/${game.id}`}>
                    {game.away?.short_name} {game.away_score} – {game.home_score} {game.home?.short_name}
                  </a>
                {:else}
                  {game.away?.short_name} en {game.home?.short_name}
                {/if}
              </td>
              <td class="small muted">{game.stage === 'playoffs' ? `postemporada ${game.series_key}` : 'temporada regular'}</td>
              <td><span class={game.state === 'final' ? 'tag accent' : 'tag'}>{game.state}</span></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else if tab === 'postemporada'}
    <div class="panel">
      <h2>Postemporada</h2>
      {#if playoffs.length === 0}
        <p class="muted small">
          La temporada regular no ha terminado. La postemporada se construye al
          cerrarse, con los clasificados reales.
        </p>
      {:else}
        {#each playoffs as series (series.series_key)}
          <div style="padding:10px 0;border-bottom:1px solid var(--line)">
            <div class="small muted">Ronda {series.round_index + 1} · al mejor de {series.best_of}</div>
            <div class="row">
              <strong>{series.high_seed?.name}</strong>
              <span class="mono">{series.high_seed_wins} – {series.low_seed_wins}</span>
              <strong>{series.low_seed?.name}</strong>
              {#if series.winner}
                <span class="tag accent">avanza {series.winner.name}</span>
              {:else}
                <span class="tag">en curso</span>
              {/if}
            </div>
          </div>
        {/each}
      {/if}
    </div>
  {:else if tab === 'lideres' && leaders}
    <div class="panel">
      <h2>Líderes</h2>
      <p class="small muted">{leaders.qualification_note}</p>
      <div class="grid two">
        <div>
          <h3>Promedio de bateo</h3>
          <table>
            <tbody>
              {#each leaders.batting_average as leader}
                <tr>
                  <td><a href={`/personas/${leader.person_id}`}>{leader.name}</a></td>
                  <td class="small muted">{leader.club}</td>
                  <td class="num">{formatPct(leader.avg)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          <h3 style="margin-top:16px">Jonrones</h3>
          <table>
            <tbody>
              {#each leaders.home_runs as leader}
                <tr>
                  <td><a href={`/personas/${leader.person_id}`}>{leader.name}</a></td>
                  <td class="small muted">{leader.club}</td>
                  <td class="num">{leader.home_runs}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <div>
          <h3>Efectividad</h3>
          <table>
            <tbody>
              {#each leaders.era as leader}
                <tr>
                  <td><a href={`/personas/${leader.person_id}`}>{leader.name}</a></td>
                  <td class="small muted">{leader.club}</td>
                  <td class="num">{leader.era}</td>
                  <td class="num small muted">{leader.innings} inn</td>
                </tr>
              {/each}
            </tbody>
          </table>
          <h3 style="margin-top:16px">Ponches</h3>
          <table>
            <tbody>
              {#each leaders.strikeouts as leader}
                <tr>
                  <td><a href={`/personas/${leader.person_id}`}>{leader.name}</a></td>
                  <td class="small muted">{leader.club}</td>
                  <td class="num">{leader.strikeouts}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  {:else if tab === 'reglas'}
    <div class="panel">
      <h2>Reglamento congelado de esta edición</h2>
      <p class="small muted">
        Versión {detail.rules.version} · firma
        <span class="mono">{detail.rules.checksum.slice(0, 16)}</span> · vigente desde
        {formatDate(detail.rules.effective_from)}. Cambiar las reglas crea una
        versión nueva y afecta a la edición siguiente, nunca a esta.
      </p>
      <pre class="small mono" style="overflow:auto;background:var(--panel-2);padding:14px;border-radius:8px">{JSON.stringify(detail.rules.rules_json, null, 2)}</pre>
    </div>
  {/if}
{:else if !error}
  <p class="muted">Cargando edición…</p>
{/if}
