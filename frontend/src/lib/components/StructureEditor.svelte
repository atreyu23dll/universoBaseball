<!--
  Editor de la estructura del campeonato: divisiones y clasificación, a mano.

  La idea: con N equipos se empieza con una tabla única, se añaden divisiones y
  las plazas se arrastran de una a otra. Cada división es un subproceso de la
  liga y **no tiene por qué parecerse a sus hermanas**: puede tener otro número
  de equipos, otras vueltas internas y otros clasificados.

  La clasificación se marca por puesto: se pulsa la insignia de un puesto y
  cicla entre no clasifica → pase directo (verde) → repechaje (ámbar). Eso es
  la puerta: «el 1.º y el 2.º del Norte pasan directos» es una, «el mejor de
  los que se quedaron fuera entra por repechaje» es otra.

  Arrastrar con el ratón no es accesible, así que cada plaza lleva además dos
  botones para moverla a la división anterior o siguiente, y cada insignia es
  un botón de verdad.
-->
<script lang="ts">
  import { flip } from 'svelte/animate';
  import type {
    BracketPreview,
    EditorDivision,
    EditorGate,
    SchedulePreview as SchedulePreviewData
  } from '$lib/api/types';
  import BracketPreviewView from './BracketPreview.svelte';
  import VisualAdjuster from './VisualAdjuster.svelte';

  interface Props {
    clubCount: number;
    divisions: EditorDivision[];
    gates: EditorGate[];
    /** Problemas que el motor encontró en esta estructura. */
    issues?: string[];
    bracket?: BracketPreview | null;
    preview?: SchedulePreviewData | null;
    currencyPrefix?: string;
    groupAssignment: string;
    gamesPerSeries: number;
    daysBetweenSeries: number;
    offseasonDays: number;
    restDays: number[];
    playoffFormat: string;
    roundLengths: string;
    rosterSize: number;
    designatedHitter: boolean;
    extraInnings: boolean;
    mercyEnabled: boolean;
    mercyRunDiff: number;
    standingsPrimary: string;
    tiebreakers: string[];
    licenceRequired: boolean;
    safetyCertRequired: boolean;
    amateurStatusRequired: boolean;
    minimumVenueCapacityEnabled: boolean;
    minimumVenueCapacity: number;
    compensationRule: string;
    entryFeeEnabled: boolean;
    entryFee: number;
    onback?: () => void;
    oncontinue?: () => void;
  }

  let {
    clubCount,
    divisions = $bindable(),
    gates = $bindable(),
    issues = [],
    bracket = null,
    preview = null,
    currencyPrefix = '$',
    groupAssignment = $bindable(),
    gamesPerSeries = $bindable(),
    daysBetweenSeries = $bindable(),
    offseasonDays = $bindable(),
    restDays = $bindable(),
    playoffFormat = $bindable(),
    roundLengths = $bindable(),
    rosterSize = $bindable(),
    designatedHitter = $bindable(),
    extraInnings = $bindable(),
    mercyEnabled = $bindable(),
    mercyRunDiff = $bindable(),
    standingsPrimary = $bindable(),
    tiebreakers = $bindable(),
    licenceRequired = $bindable(),
    safetyCertRequired = $bindable(),
    amateurStatusRequired = $bindable(),
    minimumVenueCapacityEnabled = $bindable(),
    minimumVenueCapacity = $bindable(),
    compensationRule = $bindable(),
    entryFeeEnabled = $bindable(),
    entryFee = $bindable(),
    onback,
    oncontinue
  }: Props = $props();

  /** Lo que el usuario está arrastrando. */
  let dragging = $state<{ division: string; position: number } | null>(null);
  let dropTarget = $state<string | null>(null);
  let activeView = $state<'structure' | 'schedule' | 'postseason' | 'rules'>('structure');

  const totalSlots = $derived(divisions.reduce((suma, d) => suma + d.slots, 0));
  const directos = $derived(
    gates.filter((g) => g.route === 'direct').reduce((n, g) => n + g.positions.length, 0)
  );
  const repechajes = $derived(
    gates.filter((g) => g.route === 'wildcard').reduce((n, g) => n + g.positions.length, 0)
  );
  const clasificados = $derived(directos + repechajes);
  const expectedRounds = $derived(
    clasificados >= 2 ? Math.ceil(Math.log2(clasificados)) : 0
  );
  const parsedRoundLengths = $derived(
    roundLengths
      .split(',')
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isFinite(value) && value > 0)
  );
  const seriesOptions = [1, 3, 5, 7, 9];
  const weekdays = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  const qualificationCards = $derived(
    gates.flatMap((gate) =>
      gate.positions.map((position) => ({
        key: `${gate.division ?? 'general'}-${gate.route}-${position}`,
        route: gate.route,
        label:
          gate.division === null
            ? `${gate.label || 'Repechaje'} · plaza ${position}`
            : `${position}.º de ${divisions.find((division) => division.key === gate.division)?.label ?? 'división'}`
      }))
    )
  );
  const maxPreviewGames = $derived(
    preview?.ok ? Math.max(1, ...preview.clubs.map((club) => club.games)) : 1
  );

  function nuevaClave(): string {
    let indice = divisions.length + 1;
    while (divisions.some((d) => d.key === `d${indice}`)) indice += 1;
    return `d${indice}`;
  }

  /** Ruta con la que clasifica un puesto de una división, si clasifica. */
  function routeOf(divisionKey: string | null, position: number): 'direct' | 'wildcard' | null {
    const gate = gates.find(
      (g) => g.division === divisionKey && g.positions.includes(position)
    );
    return gate ? gate.route : null;
  }

  /** Pulsar un puesto cicla su ruta: nada → directo → repechaje → nada. */
  function cycleRoute(divisionKey: string | null, position: number) {
    const actual = routeOf(divisionKey, position);
    const siguiente = actual === null ? 'direct' : actual === 'direct' ? 'wildcard' : null;
    quitarPuesto(divisionKey, position);
    if (siguiente) añadirPuesto(divisionKey, position, siguiente);
  }

  function setRoute(
    divisionKey: string | null,
    position: number,
    route: 'direct' | 'wildcard' | null
  ) {
    quitarPuesto(divisionKey, position);
    if (route) añadirPuesto(divisionKey, position, route);
    dragging = null;
  }

  function dropOnRoute(route: 'direct' | 'wildcard' | null) {
    if (!dragging) return;
    setRoute(dragging.division, dragging.position, route);
    dropTarget = null;
  }

  function matchupColor(rival: string, clubGroup: string, value: number): string {
    if (!value || !preview?.ok) return 'transparent';
    const rivalGroup = preview.clubs.find((club) => club.key === rival)?.group ?? '';
    const maximum = Math.max(
      1,
      ...Object.values(preview.matchups).flatMap((row) => Object.values(row))
    );
    const base = rivalGroup && rivalGroup === clubGroup ? 'var(--accent)' : 'var(--accent-2)';
    return `color-mix(in srgb, ${base} ${Math.round(18 + (value / maximum) * 62)}%, var(--panel))`;
  }

  function quitarPuesto(divisionKey: string | null, position: number) {
    gates = gates
      .map((g) =>
        g.division === divisionKey
          ? { ...g, positions: g.positions.filter((p) => p !== position) }
          : g
      )
      .filter((g) => g.positions.length > 0);
  }

  function añadirPuesto(
    divisionKey: string | null,
    position: number,
    route: 'direct' | 'wildcard'
  ) {
    const existente = gates.find((g) => g.division === divisionKey && g.route === route);
    if (existente) {
      gates = gates.map((g) =>
        g === existente
          ? { ...g, positions: [...g.positions, position].sort((a, b) => a - b) }
          : g
      );
    } else {
      gates = [...gates, { division: divisionKey, positions: [position], route }];
    }
  }

  function añadirDivision() {
    const clave = nuevaClave();
    // La división nueva nace con una plaza prestada de la más grande, para que
    // el total siga cuadrando con los equipos de la competición.
    const mayor = [...divisions].sort((a, b) => b.slots - a.slots)[0];
    const presta = mayor && mayor.slots > 2 ? 1 : 0;
    if (presta) ajustarSlots(mayor.key, mayor.slots - 1);
    divisions = [
      ...divisions,
      {
        key: clave,
        label: `División ${divisions.length + 1}`,
        slots: presta,
        intra_cycles: divisions[0]?.intra_cycles ?? 2,
        inter_cycles: divisions.length >= 1 ? Math.max(1, divisions[0]?.inter_cycles ?? 1) : 0
      }
    ];
    // Con más de una división, todas necesitan vueltas contra las otras.
    if (divisions.length === 2) {
      divisions = divisions.map((d) => ({ ...d, inter_cycles: Math.max(1, d.inter_cycles) }));
    }
  }

  function quitarDivision(key: string) {
    const division = divisions.find((d) => d.key === key);
    if (!division || divisions.length <= 1) return;
    const resto = divisions.filter((d) => d.key !== key);
    // Sus plazas vuelven a la primera división: ningún equipo se queda fuera.
    resto[0] = { ...resto[0], slots: resto[0].slots + division.slots };
    divisions = resto.length === 1 ? resto.map((d) => ({ ...d, inter_cycles: 0 })) : resto;
    gates = gates.filter((g) => g.division !== key);
  }

  /** Cambia las plazas de una división y recorta las puertas que se queden sin puesto. */
  function ajustarSlots(key: string, valor: number) {
    const limite = Math.max(0, Math.min(clubCount, valor));
    divisions = divisions.map((d) => (d.key === key ? { ...d, slots: limite } : d));
    gates = gates
      .map((g) => (g.division === key ? { ...g, positions: g.positions.filter((p) => p <= limite) } : g))
      .filter((g) => g.positions.length > 0);
  }

  function moverPlaza(desde: string, hacia: string) {
    if (desde === hacia) return;
    const origen = divisions.find((d) => d.key === desde);
    const destino = divisions.find((d) => d.key === hacia);
    if (!origen || !destino || origen.slots === 0) return;
    ajustarSlots(desde, origen.slots - 1);
    ajustarSlots(hacia, destino.slots + 1);
  }

  function vecina(key: string, direccion: -1 | 1): string | null {
    const indice = divisions.findIndex((d) => d.key === key);
    const otra = divisions[indice + direccion];
    return otra ? otra.key : null;
  }

  function cambiarVueltas(key: string, campo: 'intra_cycles' | 'inter_cycles', delta: number) {
    divisions = divisions.map((d) =>
      d.key === key
        ? { ...d, [campo]: Math.max(0, Math.min(12, (d as any)[campo] + delta)) }
        : d
    );
  }

  function renombrar(key: string, label: string) {
    divisions = divisions.map((d) => (d.key === key ? { ...d, label } : d));
  }

  /** Plazas de repechaje que salen de la tabla general. */
  const repechajeGeneral = $derived(
    gates.find((g) => g.division === null && g.route === 'wildcard')?.positions.length ?? 0
  );

  function cambiarRepechaje(delta: number) {
    const cuantos = Math.max(0, Math.min(16, repechajeGeneral + delta));
    gates = gates.filter((g) => !(g.division === null && g.route === 'wildcard'));
    if (cuantos > 0) {
      gates = [
        ...gates,
        {
          division: null,
          positions: Array.from({ length: cuantos }, (_, i) => i + 1),
          route: 'wildcard',
          label: 'Repechaje'
        }
      ];
    }
  }

  function toggleRestDay(day: number) {
    restDays = restDays.includes(day) ? restDays.filter((value) => value !== day) : [...restDays, day];
  }

  function toggleTiebreaker(value: string) {
    tiebreakers = tiebreakers.includes(value)
      ? tiebreakers.filter((current) => current !== value)
      : [...tiebreakers, value];
  }

  function setRoundLength(roundIndex: number, length: number) {
    const lengths = Array.from(
      { length: expectedRounds },
      (_, index) => parsedRoundLengths[index] ?? (index === expectedRounds - 1 ? 5 : 3)
    );
    lengths[roundIndex] = length;
    roundLengths = lengths.join(',');
  }

  // Una nueva plaza abre una ronda nueva con una serie válida, sin pedir que
  // el usuario edite una lista de números oculta.
  $effect(() => {
    if (playoffFormat !== 'best_of_series' || expectedRounds === 0) return;
    const normalised = Array.from(
      { length: expectedRounds },
      (_, index) => parsedRoundLengths[index] ?? (index === expectedRounds - 1 ? 5 : 3)
    );
    const next = normalised.join(',');
    if (next !== roundLengths) roundLengths = next;
  });
</script>

<div class="league-workbench">
  <header class="workbench-header">
    <div class="workbench-title">
      <span class="eyebrow">PASO 6 · FORMATO DE LIGA</span>
      <strong>Laboratorio de competición</strong>
      <span class="small muted">Arrastra plazas, conecta destinos y observa el resultado en vivo.</span>
    </div>
    <div class="live-metrics" aria-label="Resumen de la estructura">
      <span><strong>{totalSlots}</strong> equipos</span>
      <span><strong>{divisions.length}</strong> tabla{divisions.length === 1 ? '' : 's'}</span>
      <span><strong>{clasificados}</strong> clasifican</span>
      {#if preview?.ok}<span class="live"><strong>{preview.totals.games}</strong> partidos</span>{/if}
    </div>
    <div class="workbench-actions">
      <button type="button" class="button ghost" onclick={onback}>← Participantes</button>
      <button type="button" class="button" onclick={oncontinue}>Relaciones →</button>
    </div>
  </header>

  <nav class="view-tabs" aria-label="Capas del formato">
    <button type="button" class:active={activeView === 'structure'} onclick={() => (activeView = 'structure')}>
      <span>01</span> Divisiones
    </button>
    <button type="button" class:active={activeView === 'schedule'} onclick={() => (activeView = 'schedule')}>
      <span>02</span> Calendario
    </button>
    <button type="button" class:active={activeView === 'postseason'} onclick={() => (activeView = 'postseason')}>
      <span>03</span> Postemporada
    </button>
    <button type="button" class:active={activeView === 'rules'} onclick={() => (activeView = 'rules')}>
      <span>04</span> Reglamento
    </button>
  </nav>

  <div class="workbench-body">
    {#if totalSlots !== clubCount || issues.length}
      <div class="issue-strip">
        {#if totalSlots !== clubCount}
          <span>Hay {totalSlots} plazas para {clubCount} equipos.</span>
        {/if}
        {#each issues as issue}<span>{issue}</span>{/each}
      </div>
    {/if}

    {#if activeView === 'structure'}
    <section class="view-panel structure-view" aria-label="Editor de divisiones">
      <div class="view-heading">
        <div>
          <strong>Tablas de temporada regular</strong>
          <span class="small muted">Mueve una fila entre tablas o suéltala en una puerta de clasificación.</span>
        </div>
        <button type="button" class="button" onclick={añadirDivision}>+ División</button>
      </div>

      <div class="structure-canvas">
      <div class="tablero">
    {#each divisions as division (division.key)}
      <section
        class="division"
        class:objetivo={dropTarget === division.key}
        role="group"
        aria-label={division.label}
        ondragover={(e) => {
          e.preventDefault();
          dropTarget = division.key;
        }}
        ondragleave={() => {
          if (dropTarget === division.key) dropTarget = null;
        }}
        ondrop={(e) => {
          e.preventDefault();
          if (dragging) moverPlaza(dragging.division, division.key);
          dragging = null;
          dropTarget = null;
        }}
      >
        <header>
          <input
            class="nombre"
            value={division.label}
            oninput={(e) => renombrar(division.key, e.currentTarget.value)}
            aria-label={`Nombre de la división ${division.label}`}
          />
          {#if divisions.length > 1}
            <button
              type="button"
              class="button ghost mini"
              onclick={() => quitarDivision(division.key)}
              title="Quitar esta división y devolver sus plazas a la primera"
            >×</button>
          {/if}
        </header>

        <ol class="plazas">
          {#each Array.from({ length: division.slots }, (_, i) => i + 1) as puesto (puesto)}
            {@const ruta = routeOf(division.key, puesto)}
            <li
              class="plaza"
              animate:flip={{ duration: 180 }}
              class:arrastrando={dragging?.division === division.key &&
                dragging?.position === puesto}
              draggable="true"
              ondragstart={() => (dragging = { division: division.key, position: puesto })}
              ondragend={() => {
                dragging = null;
                dropTarget = null;
              }}
            >
              <span class="asa" aria-hidden="true">⠿</span>
              <span class="puesto mono">{puesto}.º</span>
              <button
                type="button"
                class="insignia"
                class:directo={ruta === 'direct'}
                class:repechaje={ruta === 'wildcard'}
                class:ninguna={ruta === null}
                onclick={() => cycleRoute(division.key, puesto)}
                aria-label={`Clasificación del puesto ${puesto} de ${division.label}: ${
                  ruta === 'direct' ? 'pase directo' : ruta === 'wildcard' ? 'repechaje' : 'no clasifica'
                }. Pulsa para cambiar`}
              >
                {ruta === 'direct' ? 'directo' : ruta === 'wildcard' ? 'repechaje' : '—'}
              </button>
              <span class="flechas">
                <button
                  type="button"
                  class="button ghost mini"
                  disabled={!vecina(division.key, -1)}
                  onclick={() => {
                    const otra = vecina(division.key, -1);
                    if (otra) moverPlaza(division.key, otra);
                  }}
                  aria-label={`Mover una plaza de ${division.label} a la división anterior`}
                >◀</button>
                <button
                  type="button"
                  class="button ghost mini"
                  disabled={!vecina(division.key, 1)}
                  onclick={() => {
                    const otra = vecina(division.key, 1);
                    if (otra) moverPlaza(division.key, otra);
                  }}
                  aria-label={`Mover una plaza de ${division.label} a la división siguiente`}
                >▶</button>
              </span>
            </li>
          {/each}
          {#if division.slots === 0}
            <li class="vacia small muted">
              Sin plazas. Arrastra alguna aquí o usa las flechas.
            </li>
          {/if}
        </ol>

        <footer>
          <div class="vueltas">
            <span class="small muted">Vueltas dentro</span>
            <div class="row">
              <button
                type="button"
                class="button ghost mini"
                onclick={() => cambiarVueltas(division.key, 'intra_cycles', -1)}
                aria-label={`Una vuelta menos dentro de ${division.label}`}
              >−</button>
              <span class="puntos" aria-hidden="true">
                {#each Array.from({ length: division.intra_cycles }) as _, i (i)}
                  <span class="punto intra"></span>
                {/each}
              </span>
              <strong class="mono">{division.intra_cycles}</strong>
              <button
                type="button"
                class="button ghost mini"
                onclick={() => cambiarVueltas(division.key, 'intra_cycles', 1)}
                aria-label={`Una vuelta más dentro de ${division.label}`}
              >+</button>
            </div>
          </div>
          {#if divisions.length > 1}
            <div class="vueltas">
              <span class="small muted">Vueltas fuera</span>
              <div class="row">
                <button
                  type="button"
                  class="button ghost mini"
                  onclick={() => cambiarVueltas(division.key, 'inter_cycles', -1)}
                  aria-label={`Una vuelta menos contra las otras divisiones, desde ${division.label}`}
                >−</button>
                <span class="puntos" aria-hidden="true">
                  {#each Array.from({ length: division.inter_cycles }) as _, i (i)}
                    <span class="punto inter"></span>
                  {/each}
                </span>
                <strong class="mono">{division.inter_cycles}</strong>
                <button
                  type="button"
                  class="button ghost mini"
                  onclick={() => cambiarVueltas(division.key, 'inter_cycles', 1)}
                  aria-label={`Una vuelta más contra las otras divisiones, desde ${division.label}`}
                >+</button>
              </div>
            </div>
          {/if}
        </footer>
      </section>
    {/each}
      </div>

      <aside class="route-dock" aria-label="Destinos de clasificación">
        <div class="route-dock-title"><span>PUERTAS</span><strong>Arrastra aquí</strong></div>
        <button
          type="button"
          class="route-drop direct-route"
          ondragover={(event) => event.preventDefault()}
          ondrop={(event) => { event.preventDefault(); dropOnRoute('direct'); }}
        >
          <span class="route-icon">↗</span><strong>Clasifica</strong><small>{directos} plazas</small>
        </button>
        <button
          type="button"
          class="route-drop wildcard-route"
          ondragover={(event) => event.preventDefault()}
          ondrop={(event) => { event.preventDefault(); dropOnRoute('wildcard'); }}
        >
          <span class="route-icon">⇢</span><strong>Repechaje</strong><small>{repechajes} plazas</small>
        </button>
        <button
          type="button"
          class="route-drop closed-route"
          ondragover={(event) => event.preventDefault()}
          ondrop={(event) => { event.preventDefault(); dropOnRoute(null); }}
        >
          <span class="route-icon">×</span><strong>No clasifica</strong><small>limpiar ruta</small>
        </button>
      </aside>
      </div>

  <div class="general">
    <div>
      <strong class="small">Repechaje desde la tabla general</strong>
      <p class="small muted" style="margin:2px 0 0">
        Plazas para los mejores de los que <strong>no</strong> clasificaron por
        su división. Es lo que evita que una división fuerte pierda a su segundo
        mejor equipo.
      </p>
    </div>
    <div class="row">
      <button
        type="button"
        class="button ghost mini"
        onclick={() => cambiarRepechaje(-1)}
        aria-label="Una plaza de repechaje menos"
      >−</button>
      <span class="puntos" aria-hidden="true">
        {#each Array.from({ length: repechajeGeneral }) as _, i (i)}
          <span class="punto repechaje"></span>
        {/each}
      </span>
      <strong class="mono">{repechajeGeneral}</strong>
      <button
        type="button"
        class="button ghost mini"
        onclick={() => cambiarRepechaje(1)}
        aria-label="Una plaza de repechaje más"
      >+</button>
    </div>
  </div>

  <p class="structure-summary small muted">
    Clasifican <strong>{clasificados}</strong>
    {#if clasificados}
      ({directos} por su puesto, {repechajes} por repechaje)
    {/if}
    de {totalSlots} equipos.
    {#if clasificados === 0}
      Sin clasificados no hay postemporada: el campeón será el primero de la tabla.
    {/if}
  </p>
    </section>

    {:else if activeView === 'schedule'}
    <section class="view-panel schedule-view" aria-label="Calendario calculado">
      <div class="schedule-toolbar">
        <VisualAdjuster label="Partidos por visita" bind:value={gamesPerSeries} min={1} max={7} />
        <VisualAdjuster label="Descanso entre series" bind:value={daysBetweenSeries} min={0} max={14} suffix=" días" />
        <VisualAdjuster label="Pausa entre temporadas" bind:value={offseasonDays} min={1} max={180} step={7} suffix=" días" />
        <div class="weekday-control">
          <span class="small muted">Días cerrados</span>
          <div class="phase-choices">
            {#each weekdays as day, index}
              <button type="button" class:active={restDays.includes(index)} onclick={() => toggleRestDay(index)} aria-pressed={restDays.includes(index)}>{day.slice(0, 2)}</button>
            {/each}
          </div>
        </div>
      </div>

      {#if preview?.ok && preview.structure}
        {#key preview}
        <div class="schedule-result">
          <div class="schedule-stats">
            <span><strong>{preview.totals.games}</strong><small>partidos</small></span>
            <span><strong>{preview.totals.games_per_club_min}{#if preview.totals.games_per_club_max !== preview.totals.games_per_club_min}–{preview.totals.games_per_club_max}{/if}</strong><small>por club</small></span>
            <span><strong>{preview.totals.rounds}</strong><small>jornadas</small></span>
            <span><strong>{preview.totals.calendar_days}</strong><small>días</small></span>
          </div>
          <div class="schedule-data-grid">
            <div class="club-load-table">
              <div class="data-heading">CARGA POR CLUB</div>
              {#each preview.clubs as club (club.key)}
                <div class="club-load-row">
                  <span>{club.label}</span>
                  <span class="load-bar" aria-hidden="true"><i style={`width:${(club.games / maxPreviewGames) * 100}%`}></i></span>
                  <strong>{club.games}</strong>
                </div>
              {/each}
            </div>
            <div class="matchup-table-wrap">
              <div class="data-heading">MAPA DE CRUCES</div>
              <table class="matchup-table">
                <thead><tr><th></th>{#each preview.clubs as rival (rival.key)}<th>{rival.key.slice(1)}</th>{/each}</tr></thead>
                <tbody>
                  {#each preview.clubs as club (club.key)}
                    <tr>
                      <th>{club.key.slice(1)}</th>
                      {#each preview.clubs as rival (rival.key)}
                        {@const value = preview.matchups[club.key]?.[rival.key] ?? 0}
                        <td style={`background:${matchupColor(rival.key, club.group, value)}`} title={`${club.label} contra ${rival.label}: ${value}`}>{club.key === rival.key ? '·' : value || ''}</td>
                      {/each}
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        {/key}
      {:else}
        <div class="empty-canvas"><span class="loader-ring"></span><strong>Calculando el calendario…</strong><small>El motor redibuja esta capa cuando cambias una plaza o una vuelta.</small></div>
      {/if}
    </section>

    {:else if activeView === 'postseason'}

  <section class="view-panel flow" aria-label="Camino de las fases del campeonato">
    <div class="flow-heading">
      <span class="flow-step regular">1</span>
      <div>
        <h4>Camino de la competición</h4>
        <p class="small muted">Las insignias de las tablas alimentan esta fase; nada se declara dos veces.</p>
      </div>
    </div>
    <div class="flow-lanes">
      <section class="flow-stage regular-stage">
        <span class="small muted">TEMPORADA REGULAR</span>
        <strong>{divisions.length === 1 ? 'Tabla general' : `${divisions.length} divisiones`}</strong>
        <span class="small muted">{totalSlots} plazas · vueltas editables arriba</span>
      </section>
      <div class="flow-link" aria-hidden="true"><span>clasifican</span></div>
      <section class="flow-stage qualifiers-stage">
        <span class="small muted">PUERTAS</span>
        {#if qualificationCards.length && playoffFormat !== 'none'}
          <div class="qualification-cards">
            {#each qualificationCards as qualifier (qualifier.key)}
              <span class="qualification" class:repechaje={qualifier.route === 'wildcard'}>{qualifier.label}</span>
            {/each}
          </div>
        {:else}
          <span class="small muted">Campeón por la tabla</span>
        {/if}
      </section>
      <div class="flow-link" aria-hidden="true"><span>avanzan</span></div>
      <section class="flow-stage playoffs-stage">
        <span class="small muted">POSTEMPORADA</span>
        <div class="phase-choices" role="group" aria-label="Destino de los clasificados">
          <button
            type="button"
            class={playoffFormat === 'best_of_series' ? 'button' : 'button ghost'}
            onclick={() => (playoffFormat = 'best_of_series')}
          >Series</button>
          <button
            type="button"
            class={playoffFormat === 'single_elimination' ? 'button' : 'button ghost'}
            onclick={() => (playoffFormat = 'single_elimination')}
          >A un partido</button>
          <button
            type="button"
            class={playoffFormat === 'none' ? 'button' : 'button ghost'}
            onclick={() => (playoffFormat = 'none')}
          >Por tabla</button>
        </div>
        {#if playoffFormat !== 'none' && clasificados >= 2}
          <span class="small muted">{clasificados} clubes · {expectedRounds} ronda{expectedRounds === 1 ? '' : 's'}</span>
        {:else if playoffFormat !== 'none'}
          <span class="small muted">Marca dos puestos arriba para abrir el cuadro.</span>
        {/if}
      </section>
      <div class="flow-link champion-link" aria-hidden="true"><span>coronan</span></div>
      <section class="flow-stage champion-stage">
        <span class="small muted">CAMPEÓN</span>
        <strong>⌂</strong>
      </section>
    </div>

    {#if playoffFormat === 'best_of_series' && clasificados >= 2}
      <div class="series-board" aria-label="Series de cada ronda">
        {#each Array.from({ length: expectedRounds }) as _, roundIndex (roundIndex)}
          <div class="round-card">
            <span class="small muted">RONDA {roundIndex + 1}</span>
            <div class="phase-choices">
              {#each seriesOptions as length}
                <button
                  type="button"
                  class={parsedRoundLengths[roundIndex] === length ? 'button' : 'button ghost'}
                  onclick={() => setRoundLength(roundIndex, length)}
                  aria-pressed={parsedRoundLengths[roundIndex] === length}
                >MD{length}</button>
              {/each}
            </div>
          </div>
        {/each}
      </div>
    {/if}

    {#if playoffFormat !== 'none' && clasificados >= 2}
      <div class="bracket-live">
        <BracketPreviewView {bracket} />
      </div>
    {/if}
  </section>

    {:else if activeView === 'rules'}
  <section class="settings-grid" aria-label="Reglas integradas al formato">
    <section class="settings-table rules-settings">
      <div class="settings-heading">
        <span class="flow-step rules">3</span>
        <div><h4>Reglas de la tabla</h4><p class="small muted">Definen cómo se ordena y se juega cada fase.</p></div>
      </div>
      <VisualAdjuster label="Tamaño de plantilla" bind:value={rosterSize} min={14} max={40} />
      <div class="setting-row">
        <span class="small muted">Reglas de juego</span>
        <div class="phase-choices">
          <button type="button" class={designatedHitter ? 'button' : 'button ghost'} onclick={() => (designatedHitter = !designatedHitter)} aria-pressed={designatedHitter}>BD</button>
          <button type="button" class={extraInnings ? 'button' : 'button ghost'} onclick={() => (extraInnings = !extraInnings)} aria-pressed={extraInnings}>Extras</button>
          <button type="button" class={mercyEnabled ? 'button' : 'button ghost'} onclick={() => (mercyEnabled = !mercyEnabled)} aria-pressed={mercyEnabled}>Nocaut</button>
        </div>
      </div>
      {#if mercyEnabled}
        <VisualAdjuster label="Diferencia de nocaut" bind:value={mercyRunDiff} min={5} max={30} suffix=" carreras" />
      {/if}
      <div class="setting-row">
        <span class="small muted">Orden de la tabla</span>
        <div class="phase-choices">
          {#each [['win_percentage', '% victorias'], ['wins', 'Victorias'], ['points', 'Puntos']] as [value, label]}
            <button type="button" class={standingsPrimary === value ? 'button' : 'button ghost'} onclick={() => (standingsPrimary = value)}>{label}</button>
          {/each}
        </div>
      </div>
      <div class="setting-row">
        <span class="small muted">Desempates</span>
        <div class="phase-choices">
          {#each [['head_to_head', 'Entre sí'], ['run_differential', 'Dif. carreras'], ['runs_for', 'Carreras'], ['fewest_runs_against', 'Menos recibidas'], ['coin_flip', 'Sorteo']] as [value, label]}
            <button type="button" class={tiebreakers.includes(value) ? 'button' : 'button ghost'} onclick={() => toggleTiebreaker(value)} aria-pressed={tiebreakers.includes(value)}>{label}</button>
          {/each}
        </div>
      </div>
    </section>

    <section class="settings-table access-settings">
      <div class="settings-heading">
        <span class="flow-step access">4</span>
        <div><h4>Puerta de entrada</h4><p class="small muted">Requisitos verificables para participar en esta estructura.</p></div>
      </div>
      <div class="setting-row">
        <span class="small muted">Requisitos</span>
        <div class="phase-choices">
          <button type="button" class={licenceRequired ? 'button' : 'button ghost'} onclick={() => (licenceRequired = !licenceRequired)} aria-pressed={licenceRequired}>Licencia</button>
          <button type="button" class={safetyCertRequired ? 'button' : 'button ghost'} onclick={() => (safetyCertRequired = !safetyCertRequired)} aria-pressed={safetyCertRequired}>Seguridad</button>
          <button type="button" class={amateurStatusRequired ? 'button' : 'button ghost'} onclick={() => (amateurStatusRequired = !amateurStatusRequired)} aria-pressed={amateurStatusRequired}>Amateur</button>
          <button type="button" class={minimumVenueCapacityEnabled ? 'button' : 'button ghost'} onclick={() => (minimumVenueCapacityEnabled = !minimumVenueCapacityEnabled)} aria-pressed={minimumVenueCapacityEnabled}>Aforo</button>
        </div>
      </div>
      {#if minimumVenueCapacityEnabled}
        <VisualAdjuster label="Aforo mínimo" bind:value={minimumVenueCapacity} min={0} max={200000} step={100} suffix=" personas" />
      {/if}
      <div class="setting-row">
        <span class="small muted">Compensación</span>
        <div class="phase-choices">
          {#each [['', 'Modalidad'], ['unrestricted', 'Libre'], ['expenses_only', 'Gastos'], ['no_salaried_players', 'Sin salarios']] as [value, label]}
            <button type="button" class={compensationRule === value ? 'button' : 'button ghost'} onclick={() => (compensationRule = value)}>{label}</button>
          {/each}
        </div>
      </div>
      <div class="setting-row">
        <span class="small muted">Inscripción</span>
        <div class="phase-choices"><button type="button" class={entryFeeEnabled ? 'button' : 'button ghost'} onclick={() => (entryFeeEnabled = !entryFeeEnabled)} aria-pressed={entryFeeEnabled}>Cuota</button></div>
      </div>
      {#if entryFeeEnabled}
        <VisualAdjuster label="Cuota por club" bind:value={entryFee} min={0} step={100} prefix={currencyPrefix} />
      {/if}
    </section>

    {#if divisions.length > 1}
      <section class="settings-table assignment-settings">
        <div class="settings-heading">
          <span class="flow-step assignment">5</span>
          <div><h4>Reparto al generar clubes</h4><p class="small muted">Ahora organizas plazas; las sedes reales se resuelven después.</p></div>
        </div>
        <div class="setting-row">
          <span class="small muted">Criterio</span>
          <div class="phase-choices">
            <button type="button" class={groupAssignment === 'geographic' ? 'button' : 'button ghost'} onclick={() => (groupAssignment = 'geographic')}>Por cercanía</button>
            <button type="button" class={groupAssignment === 'balanced' ? 'button' : 'button ghost'} onclick={() => (groupAssignment = 'balanced')}>Equilibrado</button>
          </div>
        </div>
      </section>
    {/if}
  </section>
    {/if}
  </div>
</div>

<style>
  .tablero {
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding-bottom: 6px;
    align-items: flex-start;
  }
  .division {
    min-width: 220px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--panel-2);
    padding: 8px;
    transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
  }
  .division.objetivo {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, var(--panel-2));
  }
  .division header {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
  }
  .nombre {
    flex: 1;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 6px;
    color: var(--text);
    padding: 4px 6px;
    font-weight: 600;
    min-width: 0;
  }
  .plazas {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .plaza {
    display: grid;
    grid-template-columns: auto auto 1fr auto;
    gap: 6px;
    align-items: center;
    padding: 3px 5px;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--panel);
    cursor: grab;
    transition: opacity 150ms ease, border-color 150ms ease, transform 150ms ease, background 150ms ease;
  }
  .plaza.arrastrando {
    opacity: 0.4;
    transform: scale(0.97);
  }
  .asa {
    color: var(--muted);
  }
  .puesto {
    font-size: 0.8rem;
    color: var(--muted);
  }
  .insignia {
    font: inherit;
    font-size: 0.72rem;
    padding: 1px 7px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    justify-self: start;
  }
  .insignia.directo {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 55%, var(--line));
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }
  .insignia.repechaje {
    color: var(--accent-2);
    border-color: color-mix(in srgb, var(--accent-2) 55%, var(--line));
    background: color-mix(in srgb, var(--accent-2) 14%, transparent);
  }
  .flechas {
    display: flex;
    gap: 2px;
  }
  .vacia {
    border: 1px dashed var(--line);
    border-radius: 6px;
    padding: 8px;
    text-align: center;
  }
  .division footer {
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .puntos {
    display: inline-flex;
    gap: 2px;
    align-items: center;
  }
  .punto {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--muted);
  }
  .punto.intra {
    background: var(--accent);
  }
  .punto.inter {
    background: var(--accent-2);
  }
  .punto.repechaje {
    background: var(--accent-2);
  }
  .flow {
    margin-top: 20px;
    padding-top: 18px;
    border-top: 1px solid var(--line);
  }
  .flow-heading,
  .settings-heading {
    display: flex;
    align-items: flex-start;
    gap: 9px;
  }
  .flow h4,
  .settings-heading h4 {
    margin: 0;
    font-size: 0.88rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text);
  }
  .flow-heading p,
  .settings-heading p { margin: 3px 0 0; }
  .flow-step {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 24px;
    height: 24px;
    border-radius: 50%;
    font-family: var(--mono);
    font-size: 0.75rem;
    font-weight: 700;
    color: #07120d;
    background: var(--accent);
  }
  .flow-step.rules { background: #a98bd4; }
  .flow-step.access { background: var(--accent-2); }
  .flow-step.assignment { background: #c66d93; }
  .flow-lanes {
    display: flex;
    gap: 8px;
    align-items: stretch;
    overflow-x: auto;
    padding: 14px 2px 6px;
  }
  .flow-stage {
    min-width: 155px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 5px;
    padding: 10px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--panel-2);
  }
  .regular-stage { border-color: color-mix(in srgb, var(--accent) 48%, var(--line)); }
  .playoffs-stage { min-width: 205px; }
  .champion-stage {
    min-width: 82px;
    align-items: center;
    border-color: color-mix(in srgb, var(--accent-2) 60%, var(--line));
  }
  .champion-stage strong { font-size: 1.35rem; color: var(--accent-2); }
  .flow-link {
    position: relative;
    align-self: center;
    min-width: 58px;
    height: 2px;
    background: repeating-linear-gradient(90deg, var(--accent) 0 7px, transparent 7px 12px);
    animation: flow-dashes 900ms linear infinite;
  }
  .flow-link::after {
    content: '';
    position: absolute;
    right: -1px;
    top: -3px;
    width: 8px;
    height: 8px;
    border-top: 2px solid var(--accent);
    border-right: 2px solid var(--accent);
    transform: rotate(45deg);
  }
  .flow-link span {
    position: absolute;
    top: -18px;
    left: 0;
    width: 100%;
    text-align: center;
    color: var(--muted);
    font-size: 0.65rem;
  }
  .champion-link { background-image: repeating-linear-gradient(90deg, var(--accent-2) 0 7px, transparent 7px 12px); }
  .champion-link::after { border-color: var(--accent-2); }
  .qualification-cards { display: grid; gap: 4px; }
  .qualification {
    padding: 3px 5px;
    border-left: 2px solid var(--accent);
    border-radius: 3px;
    background: var(--panel);
    font-size: 0.7rem;
  }
  .qualification.repechaje { border-left-color: var(--accent-2); }
  .phase-choices {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 3px;
  }
  .phase-choices button { padding: 4px 7px; font-size: 0.7rem; }
  .series-board {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
    gap: 8px;
    margin-top: 8px;
  }
  .round-card {
    padding: 8px;
    border: 1px solid var(--line);
    border-radius: 7px;
    background: var(--panel);
  }
  .bracket-live { margin-top: 10px; }
  .settings-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-top: 18px;
  }
  .settings-table {
    display: grid;
    align-content: start;
    gap: 8px;
    padding: 11px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: color-mix(in srgb, var(--panel-2) 82%, var(--panel));
  }
  .rules-settings { border-top: 3px solid #a98bd4; }
  .access-settings { border-top: 3px solid var(--accent-2); }
  .assignment-settings { border-top: 3px solid #c66d93; }
  .setting-row {
    display: grid;
    grid-template-columns: 100px 1fr;
    align-items: start;
    gap: 8px;
    padding-top: 8px;
    border-top: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
  }
  .setting-row .phase-choices { margin-top: 0; }
  @keyframes flow-dashes { to { background-position: 18px 0; } }
  @media (max-width: 760px) {
    .settings-grid { grid-template-columns: 1fr; }
    .setting-row { grid-template-columns: 1fr; }
  }
  @media (prefers-reduced-motion: reduce) {
    .division,
    .plaza { transition: none; }
    .flow-link { animation: none; }
  }
  .general {
    display: flex;
    gap: 12px;
    justify-content: space-between;
    align-items: center;
    margin-top: 12px;
    padding: 8px;
    border-radius: var(--radius);
    background: var(--panel-2);
    border: 1px solid var(--line);
    flex-wrap: wrap;
  }
  .league-workbench {
    width: min(1480px, calc(100vw - 24px));
    height: calc(100dvh - 190px);
    min-height: 570px;
    max-height: 820px;
    margin: 0 0 0 50%;
    transform: translateX(-50%);
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--line));
    border-radius: 14px;
    background:
      radial-gradient(circle at 18% 0%, color-mix(in srgb, var(--accent) 9%, transparent), transparent 27%),
      var(--panel);
    box-shadow: 0 24px 70px rgb(0 0 0 / 28%);
  }
  .workbench-header {
    display: grid;
    grid-template-columns: minmax(250px, 1fr) auto auto;
    gap: 18px;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--line);
    background: color-mix(in srgb, var(--panel-2) 76%, transparent);
  }
  .workbench-title { display: grid; line-height: 1.25; }
  .workbench-title > strong { font-size: 1.05rem; letter-spacing: 0.2px; }
  .eyebrow { color: var(--accent); font: 700 0.62rem var(--mono); letter-spacing: 1.2px; }
  .live-metrics { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
  .live-metrics span {
    display: grid;
    grid-auto-flow: column;
    gap: 4px;
    align-items: baseline;
    padding: 5px 8px;
    border: 1px solid var(--line);
    border-radius: 999px;
    color: var(--muted);
    font-size: 0.7rem;
    background: var(--panel);
  }
  .live-metrics strong { color: var(--text); font-family: var(--mono); }
  .live-metrics .live { border-color: color-mix(in srgb, var(--accent) 52%, var(--line)); }
  .live-metrics .live::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 14%, transparent);
    animation: live-pulse 1.4s ease-in-out infinite;
  }
  .workbench-actions { display: flex; gap: 7px; }
  .workbench-actions button { white-space: nowrap; padding: 7px 10px; font-size: 0.75rem; }
  .view-tabs {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    padding: 0 16px;
    border-bottom: 1px solid var(--line);
    background: var(--panel);
  }
  .view-tabs button {
    position: relative;
    padding: 10px 12px;
    border: 0;
    border-radius: 0;
    color: var(--muted);
    background: transparent;
    font-size: 0.78rem;
  }
  .view-tabs button span { margin-right: 5px; color: color-mix(in srgb, var(--muted) 60%, transparent); font-family: var(--mono); }
  .view-tabs button.active { color: var(--text); }
  .view-tabs button.active::after {
    content: '';
    position: absolute;
    right: 10px;
    bottom: -1px;
    left: 10px;
    height: 2px;
    background: var(--accent);
    box-shadow: 0 0 12px var(--accent);
  }
  .workbench-body { position: relative; min-height: 0; overflow: hidden; }
  .view-panel { height: 100%; min-height: 0; padding: 12px 16px; animation: view-enters 240ms ease-out both; }
  .issue-strip {
    position: absolute;
    z-index: 5;
    right: 16px;
    bottom: 12px;
    left: 16px;
    display: flex;
    gap: 8px;
    pointer-events: none;
  }
  .issue-strip span { padding: 5px 9px; border-radius: 6px; color: var(--accent-2); background: color-mix(in srgb, var(--panel) 92%, transparent); border: 1px solid color-mix(in srgb, var(--accent-2) 45%, var(--line)); font-size: 0.7rem; }
  .structure-view { display: grid; grid-template-rows: auto minmax(0, 1fr) auto auto; gap: 8px; }
  .view-heading { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
  .view-heading > div { display: grid; }
  .structure-canvas { display: grid; grid-template-columns: minmax(0, 1fr) 155px; gap: 10px; min-height: 0; }
  .tablero { height: 100%; min-height: 0; padding: 2px 2px 6px; }
  .division { min-width: min(255px, 74vw); height: max-content; max-height: 100%; overflow: auto; }
  .plaza { min-height: 28px; }
  .route-dock { display: grid; grid-template-rows: auto repeat(3, 1fr); gap: 7px; }
  .route-dock-title { display: grid; padding: 3px 2px; }
  .route-dock-title span { color: var(--accent); font: 700 0.62rem var(--mono); letter-spacing: 1px; }
  .route-drop {
    position: relative;
    display: grid;
    align-content: center;
    justify-items: center;
    gap: 2px;
    min-height: 70px;
    overflow: hidden;
    border: 1px dashed var(--line);
    border-radius: 9px;
    background: color-mix(in srgb, var(--panel-2) 78%, transparent);
    color: var(--text);
    padding: 8px;
    font-size: inherit;
    transition: transform 150ms ease, border-color 150ms ease, background 150ms ease;
  }
  .route-drop::before { content: ''; position: absolute; inset: 0; opacity: 0; background: linear-gradient(110deg, transparent 25%, color-mix(in srgb, var(--accent) 16%, transparent) 50%, transparent 75%); transform: translateX(-100%); }
  .route-drop:hover { transform: translateY(-2px); border-color: var(--accent); }
  .route-drop:hover::before { opacity: 1; animation: route-sweep 900ms linear infinite; }
  .route-drop small { color: var(--muted); }
  .route-icon { font-size: 1.15rem; color: var(--accent); }
  .wildcard-route .route-icon { color: var(--accent-2); }
  .wildcard-route:hover { border-color: var(--accent-2); }
  .closed-route { opacity: 0.72; }
  .general { margin-top: 0; padding: 6px 8px; }
  .general p { display: none; }
  .structure-summary { margin: 0; }
  .schedule-view { display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 10px; }
  .schedule-toolbar { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
  .weekday-control { display: flex; flex-direction: column; justify-content: center; padding: 7px 9px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); }
  .weekday-control .phase-choices { flex-wrap: nowrap; }
  .weekday-control button { min-width: 25px; padding: 4px; background: transparent; color: var(--muted); border: 1px solid var(--line); }
  .weekday-control button.active { color: #07120d; border-color: var(--accent); background: var(--accent); }
  .schedule-result { display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; gap: 9px; animation: data-refresh 260ms ease-out both; }
  .schedule-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; }
  .schedule-stats > span { display: flex; align-items: baseline; gap: 6px; padding: 6px 9px; border-left: 2px solid var(--accent); background: var(--panel-2); border-radius: 4px; }
  .schedule-stats strong { font: 700 1rem var(--mono); }
  .schedule-stats small { color: var(--muted); }
  .schedule-data-grid { display: grid; grid-template-columns: minmax(240px, 0.65fr) minmax(0, 1.35fr); gap: 10px; min-height: 0; }
  .club-load-table,
  .matchup-table-wrap { min-height: 0; overflow: auto; padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: color-mix(in srgb, var(--panel-2) 84%, transparent); }
  .data-heading { position: sticky; top: -8px; z-index: 2; padding: 2px 0 7px; color: var(--muted); background: var(--panel-2); font: 700 0.64rem var(--mono); letter-spacing: 0.8px; }
  .club-load-row { display: grid; grid-template-columns: 72px 1fr 28px; gap: 7px; align-items: center; padding: 3px 0; font-size: 0.72rem; }
  .club-load-row > span:first-child { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .club-load-row strong { text-align: right; font-family: var(--mono); }
  .load-bar { height: 7px; border-radius: 99px; overflow: hidden; background: var(--panel); }
  .load-bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), var(--accent-2)); transition: width 260ms ease; }
  .matchup-table { width: max-content; min-width: 100%; }
  .matchup-table th,
  .matchup-table td { min-width: 28px; padding: 3px 5px; text-align: center; font: 0.67rem var(--mono); border: 1px solid var(--line); }
  .empty-canvas { display: grid; place-content: center; justify-items: center; gap: 7px; color: var(--muted); }
  .empty-canvas strong { color: var(--text); }
  .loader-ring { width: 28px; height: 28px; border: 2px solid var(--line); border-top-color: var(--accent); border-radius: 50%; animation: spin 800ms linear infinite; }
  .flow { margin: 0; padding: 12px 16px; border-top: 0; overflow: auto; }
  .flow-lanes { overflow: visible; }
  .bracket-live :global(.panel) { padding: 10px; margin: 0; }
  .settings-grid { height: 100%; margin: 0; padding: 12px 16px; grid-template-columns: repeat(3, minmax(0, 1fr)); overflow: auto; animation: view-enters 240ms ease-out both; }
  .settings-table { min-height: 0; overflow: auto; }
  @keyframes view-enters { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes data-refresh { from { opacity: 0.45; } to { opacity: 1; } }
  @keyframes route-sweep { to { transform: translateX(100%); } }
  @keyframes live-pulse { 50% { opacity: 0.45; transform: scale(0.75); } }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 980px) {
    .league-workbench { height: auto; min-height: 690px; max-height: none; }
    .workbench-header { grid-template-columns: 1fr auto; }
    .live-metrics { grid-column: 1 / -1; grid-row: 2; justify-content: flex-start; }
    .schedule-toolbar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .settings-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 680px) {
    .league-workbench { width: calc(100vw - 12px); min-height: 760px; }
    .workbench-header { grid-template-columns: 1fr; }
    .workbench-actions { position: absolute; right: 12px; top: 12px; }
    .workbench-actions button { padding: 6px; font-size: 0; }
    .workbench-actions button:first-child::after { content: '←'; font-size: 0.9rem; }
    .workbench-actions button:last-child::after { content: '→'; font-size: 0.9rem; }
    .view-tabs { padding: 0 5px; }
    .view-tabs button { padding: 9px 3px; font-size: 0.68rem; }
    .view-tabs button span { display: none; }
    .structure-canvas { grid-template-columns: 1fr; }
    .route-dock { grid-template-columns: repeat(3, 1fr); grid-template-rows: auto 76px; }
    .route-dock-title { grid-column: 1 / -1; }
    .schedule-toolbar,
    .schedule-data-grid,
    .settings-grid { grid-template-columns: 1fr; }
    .schedule-data-grid { overflow: auto; }
  }
  @media (prefers-reduced-motion: reduce) {
    .live-metrics .live::before,
    .route-drop:hover::before,
    .loader-ring,
    .view-panel,
    .settings-grid,
    .schedule-result { animation: none; }
  }
</style>
