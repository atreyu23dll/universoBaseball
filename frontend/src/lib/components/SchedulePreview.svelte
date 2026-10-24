<!--
  Lo que producen los números del paso de calendario, dibujado mientras se
  mueven. Seis controles que se multiplican entre sí —partidos objetivo,
  partidos por serie, días entre series, descanso semanal, vueltas dentro y
  fuera de la división— no se entienden leyéndolos: hay que verlos.

  Todo lo que se pinta viene del motor por `POST /schedule/preview`, así que no
  es una maqueta: es el calendario que se va a construir. Las tablas son tablas
  de verdad —navegables con teclado y legibles por un lector de pantalla— y
  cada color lleva su número al lado, nunca solo el color.
-->
<script lang="ts">
  import { api } from '$lib/api/client';
  import { formatDate } from '$lib/format';
  import type { SchedulePreview } from '$lib/api/types';
  import BracketPreview from './BracketPreview.svelte';

  interface Props {
    /** Lo que se manda a `/schedule/preview`. Lo arma quien usa el componente. */
    payload: Record<string, unknown>;
    /** `bracket` dibuja solo la postemporada, para el paso del reglamento. */
    view?: 'full' | 'bracket' | 'headless';
    /** Se llama con cada respuesta, para que el editor marque los desajustes. */
    onresult?: (preview: SchedulePreview | null) => void;
    /** El lienzo de estructura puede mostrar el cuadro en el mismo flujo. */
    showBracket?: boolean;
  }

  const props: Props = $props();

  let preview = $state<SchedulePreview | null>(null);
  let loading = $state(false);
  let failure = $state<string | null>(null);
  let pending: ReturnType<typeof setTimeout> | null = null;

  const intent = $derived(JSON.stringify(props.payload));

  // Se recalcula al soltar el control, no en cada tecla: el motor construye el
  // calendario completo en cada llamada.
  $effect(() => {
    const body = intent;
    if (pending) clearTimeout(pending);
    pending = setTimeout(async () => {
      loading = true;
      failure = null;
      try {
        preview = await api.post<SchedulePreview>('/schedule/preview', JSON.parse(body));
        props.onresult?.(preview);
      } catch (err) {
        failure = err instanceof Error ? err.message : 'no se pudo calcular el calendario';
        preview = null;
        props.onresult?.(null);
      } finally {
        loading = false;
      }
    }, 260);
    return () => {
      if (pending) clearTimeout(pending);
    };
  });

  const DIAS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

  /** Clubes agrupados por división, para pintar cada tabla y cada barra. */
  const porGrupo = $derived.by(() => {
    if (!preview?.ok || !preview.structure) return [];
    const grupos = preview.structure.groups.map((g) => g.label);
    const lista = grupos.length ? grupos : [''];
    return lista.map((label) => ({
      label,
      clubs: preview!.clubs.filter((c) => (label ? c.group === label : true))
    }));
  });

  const maxPartidos = $derived(
    preview?.ok ? Math.max(1, ...preview.clubs.map((c) => c.games)) : 1
  );

  /** Intensidad de una celda de la matriz: 0 sin partidos, 1 el máximo. */
  function intensidad(valor: number): number {
    if (!preview?.ok) return 0;
    const tope = Math.max(
      1,
      ...Object.values(preview.matchups).flatMap((fila) => Object.values(fila))
    );
    return valor / tope;
  }

  function colorCelda(rival: string, clubGrupo: string, valor: number): string {
    if (!valor) return 'transparent';
    const rivalGrupo = preview?.clubs.find((c) => c.key === rival)?.group ?? '';
    const base = rivalGrupo && rivalGrupo === clubGrupo ? 'var(--accent)' : 'var(--accent-2)';
    const peso = Math.round(18 + 62 * intensidad(valor));
    return `color-mix(in srgb, ${base} ${peso}%, var(--panel))`;
  }
</script>

{#if props.view === 'headless'}
  <!-- Esta instancia solo mantiene sincronizado el cálculo del tablero. -->
{:else if (props.view ?? 'full') === 'bracket'}
  {#if failure}
    <div class="notice error">{failure}</div>
  {:else}
    <BracketPreview bracket={preview?.playoffs ?? null} />
  {/if}
{:else}
<div class="panel preview">
  <div class="spread">
    <h3 style="margin:0">Lo que producen estos números</h3>
    {#if loading}<span class="tag">calculando…</span>{/if}
  </div>

  {#if failure}
    <div class="notice error">{failure}</div>
  {:else if preview && !preview.ok}
    <div class="notice error">
      <strong>Todavía no se puede construir el calendario.</strong>
      <div>{preview.error}</div>
      {#if preview.suggestions?.length}
        <ul class="small">
          {#each preview.suggestions as suggestion}<li>{suggestion}</li>{/each}
        </ul>
      {/if}
      {#if preview.issues?.length}
        <ul class="small">
          {#each preview.issues as issue}<li>{issue}</li>{/each}
        </ul>
      {/if}
    </div>
  {:else if preview?.ok && preview.structure}
    {#key preview}
    <div class="live-result">
      <!-- Resumen: las cifras que antes había que deducir -->
      <div class="grid four">
      <div class="stat">
        <div class="value">{preview.totals.games}</div>
        <div class="label">partidos en total</div>
      </div>
      <div class="stat">
        <div class="value">
          {preview.totals.games_per_club_min}{#if preview.totals.games_per_club_max !== preview.totals.games_per_club_min}–{preview.totals.games_per_club_max}{/if}
        </div>
        <div class="label">
          por club
        </div>
      </div>
      <div class="stat">
        <div class="value">{preview.totals.rounds}</div>
        <div class="label">jornadas · {preview.totals.playing_days} días con partido</div>
      </div>
      <div class="stat">
        <div class="value">{preview.totals.calendar_days}</div>
        <div class="label">
          días de temporada
          {#if preview.totals.first_date && preview.totals.last_date}
            · {formatDate(preview.totals.first_date)} a {formatDate(preview.totals.last_date)}
          {/if}
        </div>
      </div>
    </div>

    {#if preview.structure.has_groups}
      <div class="row divisiones-resumen">
        {#each preview.structure.groups as grupo (grupo.label)}
          <span class="tag" class:warn={grupo.clubs < 2}>
            {grupo.label}: {grupo.clubs} club{grupo.clubs === 1 ? '' : 'es'} ·
            {grupo.intra_cycles}v dentro · {grupo.inter_cycles}v fuera
          </span>
        {/each}
      </div>
      <p class="small muted" style="margin:10px 0 0">
        <span class="muestra intra"></span>
        <strong>{preview.totals.intra_games}</strong> partidos dentro de la división
        ·
        <span class="muestra inter"></span>
        <strong>{preview.totals.inter_games}</strong> contra las otras.
        {#if !preview.structure.symmetric}
          Las divisiones <strong>no son iguales</strong>: cada una juega las vueltas
          que declara, y por eso no todos los equipos juegan el mismo número de
          partidos.
        {/if}
      </p>
    {/if}

    {#each preview.warnings as warning}
      <div class="notice" style="margin-top:10px">{warning}</div>
    {/each}

    <!-- Reparto por club: barra apilada con sus dos números -->
    <h4>Partidos de cada club</h4>
    {#each porGrupo as grupo (grupo.label)}
      {#if grupo.label && preview.structure.has_groups}
        <div class="small muted division">{grupo.label} · {grupo.clubs.length} clubes</div>
      {/if}
      {#each grupo.clubs as club (club.key)}
        <div class="fila">
          <span class="nombre small">{club.label}</span>
          <span class="barra" aria-hidden="true">
            {#if preview.structure.has_groups}
              <span
                class="trozo intra"
                style={`width:${(club.intra_games / maxPartidos) * 100}%`}
              ></span>
              <span
                class="trozo inter"
                style={`width:${(club.inter_games / maxPartidos) * 100}%`}
              ></span>
            {:else}
              <span
                class="trozo intra"
                style={`width:${(club.games / maxPartidos) * 100}%`}
              ></span>
            {/if}
          </span>
          <span class="cifra small mono">
            {club.games}
            {#if preview.structure.has_groups}
              <span class="muted">({club.intra_games}+{club.inter_games})</span>
            {/if}
            <span class="muted">· {club.home_games} en casa</span>
          </span>
        </div>
      {/each}
    {/each}

    <!-- Matriz de cruces -->
    <h4>Cuántas veces juega cada club contra cada otro</h4>
    <div class="matriz-envoltura">
      <table class="matriz">
        <caption class="small muted">
          Cada celda es el número de partidos entre los dos clubes.
          <span class="muestra intra"></span> misma división ·
          <span class="muestra inter"></span> división distinta
        </caption>
        <thead>
          <tr>
            <th scope="col"></th>
            {#each preview.clubs as rival (rival.key)}
              <th scope="col" class="small mono" title={rival.label}>{rival.key.slice(1)}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each preview.clubs as club (club.key)}
            <tr>
              <th scope="row" class="small">{club.label}</th>
              {#each preview.clubs as rival (rival.key)}
                {@const valor = preview.matchups[club.key]?.[rival.key] ?? 0}
                <td
                  class="celda mono small"
                  class:propia={club.key === rival.key}
                  style={`background:${colorCelda(rival.key, club.group, valor)}`}
                  title={`${club.label} contra ${rival.label}: ${valor} partido(s)`}
                >
                  {club.key === rival.key ? '—' : valor || ''}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Las dos primeras semanas -->
    <h4>Las dos primeras semanas</h4>
    <div class="tira">
      {#each preview.first_dates as dia (dia.date)}
        <div
          class="dia"
          class:descanso={dia.rest_day}
          class:vacio={!dia.games && !dia.rest_day}
          title={`${dia.date}: ${dia.games} partido(s)${dia.rest_day ? ' · día de descanso' : ''}`}
        >
          <span class="small muted">{DIAS[dia.weekday]}</span>
          <strong class="mono">{dia.games || (dia.rest_day ? '·' : '')}</strong>
        </div>
      {/each}
    </div>
      <p class="small muted" style="margin-top:6px">
        Cada casilla es un día con el número de partidos. Los días marcados son
        los de descanso semanal; los vacíos sin marcar son el hueco que dejan los
        días entre series.
      </p>
    </div>
    {/key}
  {/if}
</div>
{#if (props.view ?? 'full') === 'full' && props.showBracket !== false && preview?.ok}
  <BracketPreview bracket={preview.playoffs} />
{/if}
{/if}

<style>
  .preview h4 {
    margin: 18px 0 8px;
    font-size: 0.95rem;
  }
  .live-result {
    animation: preview-arrives 220ms ease-out both;
  }
  .muestra {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 2px;
    vertical-align: -1px;
  }
  .muestra.intra {
    background: var(--accent);
  }
  .muestra.inter {
    background: var(--accent-2);
  }
  .division {
    margin: 10px 0 4px;
    font-weight: 600;
  }
  .divisiones-resumen {
    margin-top: 10px;
    flex-wrap: wrap;
  }
  .fila {
    display: grid;
    grid-template-columns: 90px 1fr auto;
    gap: 10px;
    align-items: center;
    padding: 2px 0;
  }
  .barra {
    display: flex;
    height: 14px;
    background: var(--panel-2);
    border-radius: 3px;
    overflow: hidden;
  }
  .trozo.intra {
    background: var(--accent);
    transition: width 260ms ease;
  }
  .trozo.inter {
    transition: width 260ms ease;
  }
  .trozo.inter {
    background: var(--accent-2);
  }
  .cifra {
    white-space: nowrap;
  }
  .matriz-envoltura {
    overflow-x: auto;
  }
  .matriz {
    border-collapse: collapse;
    width: auto;
  }
  .matriz caption {
    caption-side: top;
    text-align: left;
    padding-bottom: 6px;
  }
  .matriz th,
  .matriz td {
    border: 1px solid var(--line);
    padding: 3px 7px;
    text-align: center;
  }
  .matriz th[scope='row'] {
    text-align: left;
    white-space: nowrap;
  }
  .celda.propia {
    background: var(--panel-2) !important;
    color: var(--muted);
  }
  .tira {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .dia {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 38px;
    padding: 4px 2px;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: color-mix(in srgb, var(--accent) 16%, var(--panel));
  }
  .dia.descanso {
    background: var(--panel-2);
    border-style: dashed;
  }
  .dia.vacio {
    background: var(--panel);
  }
  @keyframes preview-arrives {
    from { opacity: 0.35; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @media (prefers-reduced-motion: reduce) {
    .live-result { animation: none; }
    .trozo.intra, .trozo.inter { transition: none; }
  }
</style>
