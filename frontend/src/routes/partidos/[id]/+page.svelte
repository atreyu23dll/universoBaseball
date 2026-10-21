<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import { formatDate } from '$lib/format';
  import Crest from '$lib/components/Crest.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const gameId = $derived($page.params.id);
  let game = $state<any>(null);
  let events = $state<any[]>([]);
  let error = $state<unknown>(null);

  onMount(async () => {
    try {
      game = await api.get<any>(`/games/${gameId}`);
      const response = await api.get<{ items: any[] }>(`/games/${gameId}/events`);
      events = response.items;
    } catch (err) {
      error = err;
    }
  });

  const innings = $derived(
    game ? Math.max(game.line_score?.home?.length ?? 0, game.line_score?.away?.length ?? 0) : 0
  );
</script>

<ErrorNotice {error} />

{#if game}
  <div class="spread" style="margin-bottom:16px">
    <div>
      <h1>
        {game.away?.name} {game.away_score} – {game.home_score} {game.home?.name}
      </h1>
      <p class="muted small" style="margin:0">
        {formatDate(game.game_date)} · {game.venue?.name}
        · {game.innings_played} entradas
        · <span class="tag">{game.stage === 'playoffs' ? `postemporada ${game.series_key}` : 'temporada regular'}</span>
      </p>
    </div>
    <div class="small muted" style="text-align:right">
      {#if game.weather?.temperature_c !== undefined}
        {game.weather.temperature_c} °C · viento {game.weather.wind_kph} km/h
        {#if game.weather.precipitation_mm > 0}· lluvia {game.weather.precipitation_mm} mm{/if}
        <br />{game.park_note}
        <br /><span class="tag warn">clima modelado, no observado</span>
      {/if}
      <br /><span class="mono">{game.engine_version}</span> · semilla
      <span class="mono">{game.seed}</span>
    </div>
  </div>

  <div class="panel">
    <h2>Marcador por entradas</h2>
    <table>
      <thead>
        <tr>
          <th>Equipo</th>
          {#each Array(innings) as _, index}
            <th class="num">{index + 1}</th>
          {/each}
          <th class="num">C</th>
          <th class="num">H</th>
          <th class="num">E</th>
        </tr>
      </thead>
      <tbody>
        {#each [['away', game.away], ['home', game.home]] as [side, club]}
          <tr>
            <td>
              <span class="row" style="gap:8px">
                <Crest primary={club.primary_color} secondary={club.secondary_color}
                       shape={club.crest_shape} motif={club.crest_motif} size={18} />
                {club.short_name}
              </span>
            </td>
            {#each Array(innings) as _, index}
              <td class="num">{game.line_score?.[side]?.[index] ?? '–'}</td>
            {/each}
            <td class="num"><strong>{club.totals?.runs ?? 0}</strong></td>
            <td class="num">{club.totals?.hits ?? 0}</td>
            <td class="num">{club.totals?.errors ?? 0}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="small muted">
      El guion en la última entrada del local significa que no bateó: ya ganaba.
    </p>
  </div>

  <div class="grid two">
    {#each [game.away, game.home] as club, index}
      <div class="panel">
        <h2>{club.name}</h2>
        <h3>Bateo</h3>
        <table>
          <thead>
            <tr>
              <th>Jugador</th><th>Pos</th><th class="num">VB</th><th class="num">C</th>
              <th class="num">H</th><th class="num">2B</th><th class="num">HR</th>
              <th class="num">CP</th><th class="num">BB</th><th class="num">K</th>
            </tr>
          </thead>
          <tbody>
            {#each club.batting as line}
              <tr>
                <td><a href={`/personas/${line.person_id}`}>{line.name}</a></td>
                <td class="small">{line.position}</td>
                <td class="num">{line.at_bats}</td>
                <td class="num">{line.runs}</td>
                <td class="num">{line.hits}</td>
                <td class="num">{line.doubles}</td>
                <td class="num">{line.home_runs}</td>
                <td class="num">{line.runs_batted_in}</td>
                <td class="num">{line.walks}</td>
                <td class="num">{line.strikeouts}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <h3 style="margin-top:16px">Pitcheo</h3>
        <table>
          <thead>
            <tr>
              <th>Lanzador</th><th class="num">IP</th><th class="num">H</th>
              <th class="num">C</th><th class="num">CL</th><th class="num">BB</th>
              <th class="num">K</th><th class="num">LAN</th><th>Dec.</th>
            </tr>
          </thead>
          <tbody>
            {#each club.pitching as line}
              <tr>
                <td>
                  <a href={`/personas/${line.person_id}`}>{line.name}</a>
                  {#if line.is_starter}<span class="tag">abridor</span>{/if}
                </td>
                <td class="num">{line.innings}</td>
                <td class="num">{line.hits_allowed}</td>
                <td class="num">{line.runs_allowed}</td>
                <td class="num">{line.earned_runs}</td>
                <td class="num">{line.walks}</td>
                <td class="num">{line.strikeouts}</td>
                <td class="num">{line.pitches}</td>
                <td>
                  {#if line.win}<span class="tag accent">G</span>{/if}
                  {#if line.loss}<span class="tag">P</span>{/if}
                  {#if line.save}<span class="tag accent">SV</span>{/if}
                  {#if line.hold}<span class="tag">H</span>{/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if index === 1}
          <p class="small muted">
            Las entradas lanzadas se guardan en outs enteros: «5.2» son cinco
            entradas y dos tercios. Los lanzamientos son una estimación del
            motor, no un conteo de bolas y strikes.
          </p>
        {/if}
      </div>
    {/each}
  </div>

  <div class="panel">
    <h2>Desarrollo turno a turno</h2>
    {#if events.length === 0}
      <p class="muted small">
        Este partido se simuló sin guardar el detalle turno a turno.
      </p>
    {:else}
      <table>
        <thead>
          <tr><th>Ent.</th><th>Resultado</th><th>Bateador</th><th>Lanzador</th><th class="num">Carreras</th><th class="num">Marcador</th></tr>
        </thead>
        <tbody>
          {#each events as event, index (index)}
            <tr>
              <td class="small mono">{event.half === 'top' ? '▲' : '▼'}{event.inning}</td>
              <td class="small">{event.outcome.replace(/_/g, ' ')}</td>
              <td class="small muted mono">{String(event.batter).slice(-10)}</td>
              <td class="small muted mono">{String(event.pitcher).slice(-10)}</td>
              <td class="num">{event.runs || ''}</td>
              <td class="num small">{event.away_score}–{event.home_score}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
{:else if !error}
  <p class="muted">Cargando partido…</p>
{/if}
