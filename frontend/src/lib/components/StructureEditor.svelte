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
  import type { EditorDivision, EditorGate } from '$lib/api/types';

  interface Props {
    clubCount: number;
    divisions: EditorDivision[];
    gates: EditorGate[];
    /** Problemas que el motor encontró en esta estructura. */
    issues?: string[];
  }

  let {
    clubCount,
    divisions = $bindable(),
    gates = $bindable(),
    issues = []
  }: Props = $props();

  /** Lo que el usuario está arrastrando. */
  let dragging = $state<{ division: string; position: number } | null>(null);
  let dropTarget = $state<string | null>(null);

  const totalSlots = $derived(divisions.reduce((suma, d) => suma + d.slots, 0));
  const directos = $derived(
    gates.filter((g) => g.route === 'direct').reduce((n, g) => n + g.positions.length, 0)
  );
  const repechajes = $derived(
    gates.filter((g) => g.route === 'wildcard').reduce((n, g) => n + g.positions.length, 0)
  );
  const clasificados = $derived(directos + repechajes);

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
</script>

<div class="panel">
  <div class="spread">
    <h3 style="margin:0">Estructura del campeonato</h3>
    <button type="button" class="button" onclick={añadirDivision}>+ Añadir división</button>
  </div>
  <p class="small muted" style="margin:6px 0 12px">
    Arrastra una plaza de una división a otra, o usa sus flechas. Pulsa la
    insignia de un puesto para decidir si clasifica y cómo:
    <span class="insignia directo">directo</span>
    <span class="insignia repechaje">repechaje</span>.
    Cada división juega las vueltas que tú le pongas, y no tienen por qué ser
    las mismas.
  </p>

  {#if totalSlots !== clubCount}
    <div class="notice">
      Las divisiones tienen <strong>{totalSlots}</strong> plazas y la competición
      {clubCount} equipos. Mueve plazas o cambia el número de equipos en el paso 5.
    </div>
  {/if}
  {#each issues as issue}
    <div class="notice">{issue}</div>
  {/each}

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

  <p class="small muted" style="margin:10px 0 0">
    Clasifican <strong>{clasificados}</strong>
    {#if clasificados}
      ({directos} por su puesto, {repechajes} por repechaje)
    {/if}
    de {totalSlots} equipos.
    {#if clasificados === 0}
      Sin clasificados no hay postemporada: el campeón será el primero de la tabla.
    {/if}
  </p>
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
  @media (prefers-reduced-motion: reduce) {
    .division,
    .plaza { transition: none; }
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
</style>
