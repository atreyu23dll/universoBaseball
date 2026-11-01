<!--
  Editor de la estructura del campeonato: divisiones y clasificación, a mano.

  La idea: con N equipos se empieza con una tabla única, se añaden divisiones y
  las plazas se arrastran de una a otra. Cada división es un subproceso de la
  liga y **no tiene por qué parecerse a sus hermanas**: puede tener otro número
  de equipos, otras vueltas internas y otros clasificados.

  La clasificación **no** se decide aquí ni se etiqueta: se dibuja en la
  pestaña de postemporada, en un tablero donde la primera columna es la
  competición entera —todos los puestos de todas las divisiones— y las demás
  son las rondas que el usuario añade y nombra. Una plaza clasifica porque
  está puesta en una ronda, y nada más. Ya no hay «pase directo» ni
  «repechaje»: lo que significa cada entrada lo dicen su procedencia —su
  división, o la tabla general— y la ronda en la que empieza.

  Eso es lo que permite dibujar tanto una copa antigua —ocho divisiones, los
  primeros a octavos y los ganadores avanzando solos— como una postemporada de
  la MLB, donde los campeones de división no juegan la primera ronda y entran
  en la segunda contra los supervivientes del repechaje.

  Arrastrar con el ratón no es accesible, así que cada plaza lleva botones para
  moverse de división, de ronda y de orden dentro de su ronda.
-->
<script lang="ts">
  import { flip } from 'svelte/animate';
  import type {
    BracketPreview,
    EditorBracketKeyConfig,
    EditorBracketRoute,
    EditorDivision,
    EditorGate,
    PairingPolicy,
    SchedulePreview as SchedulePreviewData
  } from '$lib/api/types';
  import { formatDate as diaLargo } from '$lib/format';
  import BracketPreviewView from './BracketPreview.svelte';
  import SeasonCalendar from './SeasonCalendar.svelte';
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
    /** Día de la jornada inaugural, `YYYY-MM-DD`. Vacío = el día del mundo. */
    startDate: string;
    /** El día del mundo: ninguna temporada puede empezar antes. */
    worldDate?: string;
    /**
     * Las demás competiciones del universo con su fecha declarada. Si esta
     * liga se vincula con alguna, sus temporadas tienen que cuadrar.
     */
    otherSeasons?: Array<{ name: string; start: string | null }>;
    restDays: number[];
    playoffFormat: string;
    /** Una longitud de serie por ronda. Su tamaño **es** el número de rondas. */
    roundLengths: number[];
    roundLabels: string[];
    roundPairings: PairingPolicy[];
    bracketKeyConfigs: Record<string, EditorBracketKeyConfig>;
    bracketOutputRoutes: Record<string, EditorBracketRoute>;
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
    startDate = $bindable(),
    worldDate = '',
    otherSeasons = [],
    restDays = $bindable(),
    playoffFormat = $bindable(),
    roundLengths = $bindable(),
    roundLabels = $bindable(),
    roundPairings = $bindable(),
    bracketKeyConfigs = $bindable(),
    bracketOutputRoutes = $bindable(),
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

  /** La plaza que se arrastra entre divisiones, en la pestaña de divisiones. */
  let dragging = $state<{ division: string; position: number } | null>(null);
  /** La entrada que se arrastra por el tablero de la postemporada. */
  let draggingEntry = $state<{ division: string | null; position: number } | null>(null);
  let roundDropTarget = $state<number | null>(null);
  let keySlotTarget = $state<string | null>(null);
  let draggingOutput = $state<string | null>(null);
  /**
   * Qué llaves están desplegadas. Antes era **una sola**: abrir otra cerraba la
   * anterior, así que no se podían comparar dos llaves ni arrastrar una salida
   * de una a un puerto de la otra sin perderla de vista.
   */
  let expandedKeys = $state<Record<string, boolean>>({});
  /** Qué salida tiene abierto su menú de destinos. */
  let outputMenu = $state<string | null>(null);
  let poolIsTarget = $state(false);
  let dropTarget = $state<string | null>(null);
  let activeView = $state<'structure' | 'schedule' | 'postseason' | 'rules'>('structure');

  const totalSlots = $derived(divisions.reduce((suma, d) => suma + d.slots, 0));
  const roundCount = $derived(roundLengths.length);
  /**
   * Columnas del tablero de divisiones.
   *
   * Cuatro es el tope porque una tabla más estrecha que eso deja los nombres
   * de las divisiones sin sitio; ocho divisiones caen entonces en dos filas de
   * cuatro, que se leen de un vistazo.
   */
  const columnasDeTablero = $derived(Math.min(Math.max(divisions.length, 1), 4));
  const seriesOptions = [1, 3, 5, 7, 9];
  const weekdays = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
  const PAIRING_OPTIONS: Array<{ value: PairingPolicy; label: string; help: string }> = [
    {
      value: 'high_low',
      label: 'Mejor·peor',
      help: 'Se resiembra por la tabla: el mejor que sigue vivo contra el peor.'
    },
    {
      value: 'adjacent',
      label: 'Vecinos',
      help: 'Se resiembra por la tabla y se cruzan vecinos: 1.º-2.º, 3.º-4.º.'
    },
    {
      value: 'fixed',
      label: 'Fijas',
      help: 'El cuadro no se mueve: el ganador de un cruce espera al del cruce de al lado.'
    },
    {
      value: 'draw',
      label: 'Sorteo',
      help: 'Se sortea cada ronda. El mismo reglamento da siempre los mismos cruces.'
    }
  ];

  /**
   * Una plaza colocada en el cuadro. El editor escribe **una puerta por
   * plaza**, así que una puerta y una entrada son lo mismo y no hay que
   * deshacer agrupaciones al mover una sola.
   */
  type Placed = { division: string | null; position: number; round: number; order: number };

  const placed = $derived.by<Placed[]>(() =>
    gates.flatMap((gate) =>
      gate.positions.map((position, offset) => ({
        division: gate.division,
        position,
        round: gate.target_round ?? 0,
        order: (gate.order ?? 0) + offset
      }))
    )
  );
  const clasificados = $derived(placed.length);
  /** Plazas de la tabla general que ya están en el cuadro. */
  const generalPositions = $derived(
    placed.filter((item) => item.division === null).map((item) => item.position)
  );
  /**
   * Cuántas plazas de la tabla general ofrece el plantel: las colocadas y una
   * libre, para que siempre haya la siguiente a mano sin pedir un número.
   */
  const generalRows = $derived(Math.max(0, ...generalPositions) + 1);
  const maxPreviewGames = $derived(
    preview?.ok ? Math.max(1, ...preview.clubs.map((club) => club.games)) : 1
  );

  function entryId(division: string | null, position: number): string {
    return `${division ?? '·general'}#${position}`;
  }

  function divisionLabel(key: string | null): string {
    if (key === null) return 'Tabla general';
    return divisions.find((division) => division.key === key)?.label ?? 'división';
  }

  /** Cómo se llama una plaza. Es el mismo nombre que le pone el motor. */
  function entryLabel(division: string | null, position: number): string {
    return division === null
      ? `${position}.º de los restantes`
      : `${position}.º de ${divisionLabel(division)}`;
  }

  function placementOf(division: string | null, position: number): Placed | null {
    return (
      placed.find((item) => item.division === division && item.position === position) ?? null
    );
  }

  function roundOf(division: string | null, position: number): number | null {
    return placementOf(division, position)?.round ?? null;
  }

  function entrantsAt(roundIndex: number): Placed[] {
    return placed
      .filter((item) => item.round === roundIndex)
      .sort((a, b) => a.order - b.order);
  }

  /**
   * Escribe las puertas desde la lista de plazas colocadas.
   *
   * Hace dos cosas que el reglamento necesita y el usuario no debería pensar:
   * numera el orden de cada entrada —que es el cruce que dibujó— y cierra los
   * huecos de las plazas de la tabla general, porque «el 3.º de los
   * restantes» sin que exista un 2.º no significaría nada.
   */
  function commit(entries: Placed[]) {
    const ordered = [...entries]
      .sort((a, b) => a.round - b.round || a.order - b.order || a.position - b.position)
      .map((item) => ({ ...item }));
    let libre = 0;
    ordered
      .filter((item) => item.division === null)
      .sort((a, b) => a.position - b.position)
      .forEach((item) => {
        libre += 1;
        item.position = libre;
      });
    gates = ordered.map((item, index) => ({
      division: item.division,
      positions: [item.position],
      route: 'seed' as const,
      target_round: item.round,
      order: index
    }));
  }

  /** Coloca una plaza en una ronda, al final de las que ya están ahí. */
  function place(division: string | null, position: number, roundIndex: number) {
    if (roundIndex < 0 || roundIndex >= roundCount) return;
    const resto = placed.filter(
      (item) => !(item.division === division && item.position === position)
    );
    const ultimo = Math.max(
      -1,
      ...resto.filter((item) => item.round === roundIndex).map((item) => item.order)
    );
    commit([...resto, { division, position, round: roundIndex, order: ultimo + 1 }]);
  }

  /** Coloca una plaza en un puerto concreto de una llave, no solo en la ronda. */
  function placeAt(
    division: string | null,
    position: number,
    roundIndex: number,
    slotIndex: number
  ) {
    if (roundIndex < 0 || roundIndex >= roundCount) return;
    const resto = placed.filter(
      (item) => !(item.division === division && item.position === position)
    );
    const deLaRonda = resto
      .filter((item) => item.round === roundIndex)
      .sort((a, b) => a.order - b.order);
    deLaRonda.splice(Math.max(0, Math.min(slotIndex, deLaRonda.length)), 0, {
      division,
      position,
      round: roundIndex,
      order: slotIndex
    });
    const otras = resto.filter((item) => item.round !== roundIndex);
    commit([...otras, ...deLaRonda.map((item, index) => ({ ...item, order: index }))]);
    // Una colocación en una llave específica debe respetar el dibujo.
    setPairing(roundIndex, 'fixed');
  }

  /** Devuelve una plaza al plantel: deja de clasificar. */
  function unplace(division: string | null, position: number) {
    commit(placed.filter((item) => !(item.division === division && item.position === position)));
  }

  function toggleEntry(division: string | null, position: number) {
    if (placementOf(division, position)) unplace(division, position);
    else place(division, position, 0);
  }

  function shiftRound(division: string | null, position: number, delta: -1 | 1) {
    const actual = roundOf(division, position);
    if (actual === null) return;
    place(division, position, Math.max(0, Math.min(roundCount - 1, actual + delta)));
  }

  /** Mueve una entrada dentro de su ronda: con llaves fijas, cambia el cruce. */
  function reorderEntry(division: string | null, position: number, delta: -1 | 1) {
    const actual = placementOf(division, position);
    if (!actual) return;
    const hermanas = entrantsAt(actual.round);
    const indice = hermanas.findIndex(
      (item) => item.division === division && item.position === position
    );
    const vecina = hermanas[indice + delta];
    if (!vecina) return;
    commit(
      placed.map((item) => {
        if (item.division === division && item.position === position) {
          return { ...item, order: vecina.order };
        }
        if (item.division === vecina.division && item.position === vecina.position) {
          return { ...item, order: actual.order };
        }
        return item;
      })
    );
    setPairing(actual.round, 'fixed');
  }

  function dropOnRound(roundIndex: number) {
    if (!draggingEntry) return;
    place(draggingEntry.division, draggingEntry.position, roundIndex);
    draggingEntry = null;
    roundDropTarget = null;
  }

  function dropOnKeySlot(roundIndex: number, slotIndex: number) {
    if (draggingOutput) {
      const sourceRound = Number(draggingOutput.match(/^r(\d+)k/)?.[1] ?? 0) - 1;
      if (roundIndex > sourceRound) {
        bracketOutputRoutes = {
          ...bracketOutputRoutes,
          [draggingOutput]: { target_round: roundIndex, target_slot: slotIndex }
        };
      }
      draggingOutput = null;
      keySlotTarget = null;
      roundDropTarget = null;
      return;
    }
    if (!draggingEntry) return;
    placeAt(draggingEntry.division, draggingEntry.position, roundIndex, slotIndex);
    draggingEntry = null;
    roundDropTarget = null;
    keySlotTarget = null;
  }

  function dropOnPool() {
    if (!draggingEntry) return;
    unplace(draggingEntry.division, draggingEntry.position);
    draggingEntry = null;
    poolIsTarget = false;
  }

  function addRound() {
    if (roundCount >= 8) return;
    roundLengths = [...roundLengths, roundLengths.at(-1) ?? 5];
    roundLabels = [...roundLabels, `Ronda ${roundLengths.length}`];
    roundPairings = [...roundPairings, roundPairings.at(-1) ?? 'fixed'];
  }

  /** Quita una ronda. Sus entradas vuelven al plantel; las de después, se corren. */
  function removeRound(roundIndex: number) {
    if (roundCount <= 1) return;
    roundLengths = roundLengths.filter((_, index) => index !== roundIndex);
    roundLabels = roundLabels.filter((_, index) => index !== roundIndex);
    roundPairings = roundPairings.filter((_, index) => index !== roundIndex);
    commit(
      placed
        .filter((item) => item.round !== roundIndex)
        .map((item) => ({ ...item, round: item.round > roundIndex ? item.round - 1 : item.round }))
    );
  }

  function setRoundLength(roundIndex: number, length: number) {
    roundLengths = roundLengths.map((actual, index) => (index === roundIndex ? length : actual));
  }

  function renameRound(roundIndex: number, label: string) {
    roundLabels = Array.from({ length: roundCount }, (_, index) =>
      index === roundIndex ? label : roundLabels[index] || `Ronda ${index + 1}`
    );
  }

  function setPairing(roundIndex: number, policy: PairingPolicy) {
    roundPairings = Array.from({ length: roundCount }, (_, index) =>
      index === roundIndex ? policy : roundPairings[index] || 'fixed'
    );
  }

  function pairingOf(roundIndex: number): PairingPolicy {
    return roundPairings[roundIndex] || 'fixed';
  }

  function keyId(roundIndex: number, keyIndex: number): string {
    return `r${roundIndex + 1}k${keyIndex + 1}`;
  }

  function keyConfig(roundIndex: number, keyIndex: number): EditorBracketKeyConfig {
    return bracketKeyConfigs[keyId(roundIndex, keyIndex)] ?? {
      format: 'series',
      participants: 2,
      best_of: seriesOf(roundIndex),
      games_per_pair: 1,
      qualifying_positions: [1]
    };
  }

  function configureKey(
    roundIndex: number,
    keyIndex: number,
    patch: Partial<EditorBracketKeyConfig>
  ) {
    const id = keyId(roundIndex, keyIndex);
    bracketKeyConfigs = {
      ...bracketKeyConfigs,
      [id]: { ...keyConfig(roundIndex, keyIndex), ...patch }
    };
    setPairing(roundIndex, 'fixed');
  }

  function resizeMiniLeague(roundIndex: number, keyIndex: number, participants: number) {
    const size = Math.max(3, Math.min(64, participants));
    const current = keyConfig(roundIndex, keyIndex);
    const advancing = Math.min(current.qualifying_positions.length, size - 1);
    configureKey(roundIndex, keyIndex, {
      format: 'mini_league',
      participants: size,
      qualifying_positions: Array.from({ length: Math.max(1, advancing) }, (_, index) => index + 1)
    });
  }

  function resizeMiniQualifiers(roundIndex: number, keyIndex: number, count: number) {
    const config = keyConfig(roundIndex, keyIndex);
    const maximum = Math.max(1, config.participants - 1);
    const amount = Math.max(1, Math.min(maximum, count));
    configureKey(roundIndex, keyIndex, {
      qualifying_positions: Array.from({ length: amount }, (_, index) => index + 1)
    });
  }

  /**
   * A qué puertos puede ir una salida. Arrastrar funciona, pero con varias
   * llaves abiertas es un ejercicio de puntería: esta lista hace lo mismo con
   * un clic y, de paso, **enseña** que la salida se puede conectar.
   */
  function destinosPara(sourceRound: number) {
    const destinos: Array<{ round: number; slot: number; label: string; ocupado: boolean }> = [];
    for (let round = sourceRound + 1; round < roundCount; round += 1) {
      let absoluto = 0;
      for (const key of keysAt(round)) {
        key.slots.forEach((slot, slotIndex) => {
          destinos.push({
            round,
            slot: absoluto,
            label: `${roundLabels[round] || `Ronda ${round + 1}`} · llave ${key.number} · puerto ${slotIndex + 1}`,
            ocupado: slot !== null
          });
          absoluto += 1;
        });
      }
      // Un puerto que todavía no existe: es lo que convierte al perdedor en un
      // cruce nuevo (tercer puesto, repechaje) en vez de obligarle a desalojar
      // a alguien de una llave ya dibujada.
      destinos.push({
        round,
        slot: absoluto,
        label: `${roundLabels[round] || `Ronda ${round + 1}`} · cruce nuevo`,
        ocupado: false
      });
    }
    return destinos;
  }

  /** Cómo se dice un destino ya conectado, para la propia pastilla. */
  function destinoLabel(route: EditorBracketRoute): string {
    const ronda = roundLabels[route.target_round] || `Ronda ${route.target_round + 1}`;
    let absoluto = 0;
    for (const key of keysAt(route.target_round)) {
      for (let slotIndex = 0; slotIndex < key.slots.length; slotIndex += 1) {
        if (absoluto === route.target_slot) return `${ronda} · llave ${key.number}`;
        absoluto += 1;
      }
    }
    return ronda;
  }

  function connectOutput(token: string, round: number, slot: number) {
    bracketOutputRoutes = { ...bracketOutputRoutes, [token]: { target_round: round, target_slot: slot } };
    outputMenu = null;
  }

  function clearOutputRoute(token: string) {
    if (!bracketOutputRoutes[token]) return;
    const next = { ...bracketOutputRoutes };
    delete next[token];
    bracketOutputRoutes = next;
  }

  /**
   * Participantes visibles de una ronda, ya separados en llaves. Los
   * ganadores anteriores son puertos reales: no se reducen con una división
   * entera que pudiera hacer desaparecer al participante impar.
   */
  function keysAt(roundIndex: number): Array<{
    number: number;
    format: 'series' | 'mini_league';
    qualifying: number[];
    slots: Array<Placed | { winner: number; sourceRound: number; token: string; unresolved: boolean; position?: number } | null>;
  }> {
    type Incoming = {
      winner: number;
      sourceRound: number;
      token: string;
      unresolved: boolean;
      position?: number;
      targetSlot?: number;
    };
    const arriving: Incoming[] = [];
    for (let sourceRound = 0; sourceRound < roundIndex; sourceRound += 1) {
      for (const key of keysAt(sourceRound)) {
        const outputs: Array<{ suffix: string; position?: number }> = key.format === 'mini_league'
          ? key.qualifying.map((position) => ({ suffix: `position:${position}`, position }))
          : [
              { suffix: 'winner' },
              ...(bracketOutputRoutes[`${keyId(sourceRound, key.number - 1)}:loser`]
                ? [{ suffix: 'loser' }]
                : [])
            ];
        for (const output of outputs) {
          const { suffix, position } = output;
          const token = `${keyId(sourceRound, key.number - 1)}:${suffix}`;
          const route = bracketOutputRoutes[token];
          const targetRound = route?.target_round ?? sourceRound + 1;
          if (targetRound !== roundIndex) continue;
          arriving.push({
            winner: key.number - 1,
            sourceRound,
            token,
            unresolved: key.slots.includes(null),
            ...(key.format === 'mini_league' ? { position } : {}),
            ...(route ? { targetSlot: route.target_slot } : {})
          });
        }
      }
    }
    const fixed = arriving.filter((item) => item.targetSlot !== undefined);
    const flexible: Array<Placed | Incoming> = [
      ...arriving.filter((item) => item.targetSlot === undefined),
      ...entrantsAt(roundIndex)
    ];
    const participantCount = fixed.length + flexible.length;
    const furthestSlot = Math.max(-1, ...fixed.map((item) => item.targetSlot ?? -1));
    const participants: Array<Placed | Incoming | null> = Array.from(
      { length: Math.max(participantCount, furthestSlot + 1) },
      () => null
    );
    for (const item of fixed) {
      const slot = item.targetSlot ?? 0;
      if (participants[slot] === null) participants[slot] = item;
      else flexible.push(item);
    }
    for (const item of flexible) {
      const empty = participants.indexOf(null);
      if (empty === -1) participants.push(item);
      else participants[empty] = item;
    }
    const keys: Array<{
      number: number;
      format: 'series' | 'mini_league';
      qualifying: number[];
      slots: Array<Placed | Incoming | null>;
    }> = [];
    let offset = 0;
    while (offset < participants.length) {
      const config = keyConfig(roundIndex, keys.length);
      const size = config.format === 'mini_league' ? Math.max(3, config.participants) : 2;
      const slots: Array<Placed | Incoming | null> = participants.slice(offset, offset + size);
      while (slots.length < size) slots.push(null);
      keys.push({
        number: keys.length + 1,
        format: config.format,
        qualifying: config.format === 'mini_league' ? config.qualifying_positions : [1],
        slots
      });
      offset += size;
    }
    return keys;
  }

  /** Lo que se va a jugar de verdad: una eliminatoria es siempre a un partido. */
  function seriesOf(roundIndex: number): number {
    return playoffFormat === 'single_elimination' ? 1 : roundLengths[roundIndex];
  }

  /** Cruces que el motor calculó para una ronda, si ya respondió. */
  function crossesAt(roundIndex: number): Array<{ high: string; low: string }> {
    if (!bracket?.drawn) return [];
    return bracket.rounds.find((ronda) => ronda.round === roundIndex + 1)?.series ?? [];
  }

  function nuevaClave(): string {
    let indice = divisions.length + 1;
    while (divisions.some((d) => d.key === `d${indice}`)) indice += 1;
    return `d${indice}`;
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

  /**
   * Cuánta gente juega una ronda y cuánta sobrevive.
   *
   * Es la cuenta que decide si el camino se puede jugar: los que entran por
   * una puerta más los ganadores de la ronda anterior tienen que ser pares y
   * al menos dos. La hace el editor al instante para que el usuario vea el
   * desajuste mientras arrastra; la autoridad sigue siendo el motor, que
   * responde con sus problemas en `issues`.
   */
  function roundFlow(roundIndex: number): {
    entrants: number;
    arriving: number;
    participants: number;
    survivors: number;
    valid: boolean;
  } {
    let survivors = 0;
    for (let index = 0; index <= roundIndex; index += 1) {
      const entrants = entrantsAt(index).length;
      const keys = keysAt(index);
      const arriving = keys
        .flatMap((key) => key.slots)
        .filter((slot) => slot !== null && 'winner' in slot).length;
      const participants = keys.flatMap((key) => key.slots).filter((slot) => slot !== null).length;
      // Los que sobreviven a la ronda, sin contar la consolación: el ganador
      // del tercer puesto no sigue compitiendo por el título.
      survivors = keys.reduce(
        (total, key, keyIndex) =>
          total + (consolationKeys.has(keyId(index, keyIndex)) ? 0 : key.qualifying.length),
        0
      );
      if (index === roundIndex) {
        return {
          entrants,
          arriving,
          participants,
          survivors,
          valid: participants >= 2 && keys.every((key) => !key.slots.includes(null))
        };
      }
    }
    return { entrants: 0, arriving: 0, participants: 0, survivors: 0, valid: false };
  }

  /**
   * Las llaves a las que solo se llega perdiendo: el tercer puesto, un
   * repechaje, un cuadro de perdedores. Su ganador es una salida final
   * legítima que no disputa el título, así que no cuenta para decidir si el
   * camino al campeonato está cerrado. La misma regla que aplica el motor
   * (`consolation_keys` en `simulation/competitions/structure.py`).
   */
  const consolationKeys = $derived.by(() => {
    const salida = new Set<string>();
    for (let round = 0; round < roundCount; round += 1) {
      keysAt(round).forEach((key, keyIndex) => {
        if (!key.slots.length || key.slots.includes(null)) return;
        const todos = key.slots.every(
          (slot) =>
            slot !== null &&
            'winner' in slot &&
            (slot.token.endsWith(':loser') || salida.has(keyId(slot.sourceRound, slot.winner)))
        );
        if (todos) salida.add(keyId(round, keyIndex));
      });
    }
    return salida;
  });

  const pathIsValid = $derived.by(() => {
    if (roundCount === 0 || clasificados < 2) return false;
    return Array.from({ length: roundCount }, (_, index) => roundFlow(index)).every(
      (estado, index) => estado.valid && (index < roundCount - 1 || estado.survivors === 1)
    );
  });

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

  /**
   * Reparte las plazas en partes iguales. Con ocho divisiones y 32 equipos eso
   * son 24 pulsaciones de flecha, y es una cuenta, no una decisión.
   *
   * Si el reparto no es exacto, las primeras divisiones se quedan con la plaza
   * de más: sigue siendo una estructura asimétrica legítima y el editor la
   * enseña como tal.
   */
  function repartirPorIgual() {
    const cuantas = divisions.length;
    if (!cuantas) return;
    const base = Math.floor(clubCount / cuantas);
    const resto = clubCount % cuantas;
    divisions = divisions.map((division, indice) => ({
      ...division,
      slots: base + (indice < resto ? 1 : 0)
    }));
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

  function toggleRestDay(day: number) {
    restDays = restDays.includes(day) ? restDays.filter((value) => value !== day) : [...restDays, day];
  }

  function toggleTiebreaker(value: string) {
    tiebreakers = tiebreakers.includes(value)
      ? tiebreakers.filter((current) => current !== value)
      : [...tiebreakers, value];
  }

  // Si una división se encoge, sus plazas de más dejan de existir y salen del
  // cuadro; si se quita una ronda por otro camino, las entradas que apuntaban
  // más allá se recogen en la última. El tablero nunca guarda una entrada que
  // no se pueda jugar.
  $effect(() => {
    const vivas = placed.filter(
      (item) =>
        item.division === null ||
        item.position <= (divisions.find((d) => d.key === item.division)?.slots ?? 0)
    );
    const dentro = vivas.map((item) => ({
      ...item,
      round: Math.min(item.round, Math.max(0, roundCount - 1))
    }));
    const cambia =
      dentro.length !== placed.length ||
      dentro.some((item, index) => item.round !== placed[index]?.round);
    if (cambia) commit(dentro);
  });
</script>

<div class="league-workbench">
  <header class="workbench-header">
    <div class="workbench-title">
      <span class="eyebrow">PASO 6 · FORMATO DE LIGA</span>
      <strong>Laboratorio de competición</strong>
      <span class="small muted">Reparte las plazas, dibuja las rondas y observa el resultado en vivo.</span>
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
          <span class="small muted">
            Mueve una plaza de una tabla a otra, ajusta las vueltas, y
            <strong>pulsa la insignia</strong> de un puesto para que clasifique.
          </span>
        </div>
        <div class="row">
          {#if divisions.length > 1}
            <button
              type="button"
              class="button ghost"
              onclick={repartirPorIgual}
              title="Reparte las plazas en partes iguales entre las divisiones"
            >Igualar</button>
          {/if}
          <button type="button" class="button" onclick={añadirDivision}>+ División</button>
        </div>
      </div>

      <div class="structure-canvas">
      <!--
        Las columnas las dice cuántas divisiones hay, no un número fijo: con
        una, ocupa el lienzo; con ocho, se reparten en dos filas de cuatro en
        vez de esconderse tras un desplazamiento lateral.
      -->
      <div class="tablero" style={`--columnas:${columnasDeTablero}`}>
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
            {@const ronda = roundOf(division.key, puesto)}
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
              <!--
                Marcar que un puesto clasifica se puede hacer aquí, que es
                donde se está mirando la tabla. No son dos modelos: pulsar
                aquí lo mete en la **primera** ronda, y en qué ronda empieza
                se dibuja en el tablero de postemporada.
              -->
              <button
                type="button"
                class="insignia"
                class:clasifica={ronda !== null}
                class:ninguna={ronda === null}
                onclick={() => toggleEntry(division.key, puesto)}
                aria-pressed={ronda !== null}
                title={ronda === null
                  ? `El ${puesto}.º de ${division.label} no clasifica. Pulsa para meterlo en ${roundLabels[0] || 'la primera ronda'}.`
                  : `El ${puesto}.º de ${division.label} entra en ${roundLabels[ronda] || `la ronda ${ronda + 1}`}. Pulsa para quitarlo del cuadro.`}
              >
                {ronda === null ? '—' : roundLabels[ronda] || `R${ronda + 1}`}
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

      </div>

  <p class="structure-summary small muted">
    Clasifican <strong>{clasificados}</strong> de {totalSlots} equipos.
    {#if clasificados === 0}
      Sin clasificados no hay postemporada: el campeón será el primero de la
      tabla. Pulsa la insignia «—» de un puesto para meterlo en el cuadro.
    {:else}
      Pulsar la insignia mete o saca un puesto; <strong>en qué ronda empieza</strong>
      se dibuja en <strong>Postemporada</strong>.
    {/if}
  </p>
    </section>

    {:else if activeView === 'schedule'}
    <section class="view-panel schedule-view" aria-label="Calendario calculado">
      <div class="schedule-toolbar">
        <!--
          La fecha de inicio es una decisión del reglamento, no del momento en
          que se pulsa «crear»: antes toda liga arrancaba el día en que se
          creaba. El final no se pide, lo dice el calendario que sale de las
          vueltas, los partidos por serie y los descansos.
        -->
        <div class="date-control">
          <label for="inicio-temporada">Inicio de temporada</label>
          <input
            id="inicio-temporada"
            type="date"
            bind:value={startDate}
            min={worldDate || undefined}
          />
          <span class="small muted">
            {#if preview?.ok && preview.totals.last_date}
              Termina el {diaLargo(preview.totals.last_date)}, según el calendario.
            {:else}
              Si lo dejas vacío, arranca el día del mundo.
            {/if}
          </span>
        </div>
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
          <div class="calendar-block">
            <div class="data-heading">CALENDARIO · DÍAS DE PARTIDO</div>
            <SeasonCalendar
              calendar={preview.calendar ?? []}
              clubs={preview.clubs}
              firstDate={preview.totals.first_date}
              lastDate={preview.totals.last_date}
              restDays={preview.rest_days_weekday ?? restDays}
              complete={preview.calendar_complete ?? true}
            />
            {#if otherSeasons.length}
              <p class="small muted linked-note">
                En este universo ya hay
                {#each otherSeasons as otra, indice (otra.name)}{indice > 0
                  ? ', '
                  : ' '}«{otra.name}»{#if otra.start}, que empieza el {diaLargo(otra.start)}{/if}{/each}.
                Si vinculas esta liga con alguna de ellas (paso de relaciones),
                las dos abrirán su siguiente temporada el mismo día —el más
                tardío de las dos—, porque el intercambio de plazas no se puede
                resolver hasta que ambas hayan terminado.
              </p>
            {/if}
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

  <section class="view-panel postseason-editor" aria-label="Tablero de la postemporada">
    <div class="postseason-toolbar">
      <span class="eyebrow">MAPA DE POSTEMPORADA</span>
      <h4>Construye el camino al campeonato</h4>
      <p class="small muted">
        Cada llave es un cruce y lleva abajo sus <strong>salidas</strong>: a
        dónde va el ganador y a dónde el perdedor. Arrastra una salida al puerto
        de una ronda posterior, o pulsa «⋯» para elegir el destino. Un perdedor
        sin conectar queda eliminado; conectarlo es lo que crea el partido por
        el tercer puesto, un repechaje o un cuadro de perdedores.
      </p>
    </div>

    <!--
      Una sola banda de mandos. Antes el formato estaba arriba a la derecha, el
      recuento del camino en otra tira y «+ Ronda» repetido en las dos: tres
      sitios para tres cosas que se deciden a la vez.
    -->
    <div class="postseason-controls">
      <div class="phase-choices" role="group" aria-label="Formato de la postemporada">
        <button type="button" class={playoffFormat === 'best_of_series' ? 'button' : 'button ghost'} onclick={() => (playoffFormat = 'best_of_series')}>Series</button>
        <button type="button" class={playoffFormat === 'single_elimination' ? 'button' : 'button ghost'} onclick={() => (playoffFormat = 'single_elimination')}>Partido único</button>
        <button type="button" class={playoffFormat === 'none' ? 'button' : 'button ghost'} onclick={() => (playoffFormat = 'none')}>Campeón por tabla</button>
      </div>
      {#if playoffFormat !== 'none'}
        <div class="path-summary">
          <span><strong>{clasificados}</strong> clasificados</span>
          <span><strong>{roundCount}</strong> ronda{roundCount === 1 ? '' : 's'}</span>
          <span><strong>{totalSlots - clasificados}</strong> se queda{totalSlots - clasificados === 1 ? '' : 'n'} fuera</span>
          <span class:flow-ok={pathIsValid} class:flow-bad={!pathIsValid}>
            {pathIsValid ? 'camino cerrado ✓' : 'camino incompleto'}
          </span>
        </div>
        <button
          type="button"
          class="button ghost round-add"
          onclick={addRound}
          disabled={roundCount >= 8}
        >+ Ronda</button>
      {/if}
    </div>

    {#if playoffFormat !== 'none'}

      <div class="kanban bracket-roadmap" aria-label="Cuadro y rutas de la postemporada">
        {#each Array.from({ length: roundCount }) as _, roundIndex (roundIndex)}
          {@const flujo = roundFlow(roundIndex)}
          {@const cruces = crossesAt(roundIndex)}
          <section
            class="editable-round"
            class:first-round={roundIndex === 0}
            style={`--round-depth:${roundIndex}`}
            role="group"
            aria-label={`${roundLabels[roundIndex] || `Ronda ${roundIndex + 1}`}: ${flujo.participants} participantes`}
            class:drop-active={roundDropTarget === roundIndex}
            class:invalid={!flujo.valid}
            ondragover={(event) => {
              event.preventDefault();
              roundDropTarget = roundIndex;
            }}
            ondragleave={() => {
              if (roundDropTarget === roundIndex) roundDropTarget = null;
            }}
            ondrop={(event) => {
              event.preventDefault();
              dropOnRound(roundIndex);
            }}
          >
            <header class="round-editor-header">
              <span class="round-number mono">{String(roundIndex + 1).padStart(2, '0')}</span>
              <input
                class="round-name"
                value={roundLabels[roundIndex] ?? `Ronda ${roundIndex + 1}`}
                oninput={(event) => renameRound(roundIndex, event.currentTarget.value)}
                aria-label={`Nombre de la ronda ${roundIndex + 1}`}
              />
              <span class="round-count" class:bad={!flujo.valid}>
                {flujo.participants} → {flujo.survivors}
              </span>
              <button
                type="button"
                class="button ghost mini"
                onclick={() => removeRound(roundIndex)}
                disabled={roundCount <= 1}
                title="Quitar esta ronda: sus plazas vuelven al plantel"
                aria-label={`Quitar la ronda ${roundIndex + 1}`}
              >×</button>
            </header>

            <div class="round-rules">
              <span class="small muted" title="Longitud de las llaves de la ronda que no tengan una serie propia">Serie por omisión</span>
              <div class="phase-choices">
                {#each seriesOptions as length}
                  <button
                    type="button"
                    class={seriesOf(roundIndex) === length ? 'button' : 'button ghost'}
                    onclick={() => setRoundLength(roundIndex, length)}
                    disabled={playoffFormat === 'single_elimination'}
                    aria-pressed={seriesOf(roundIndex) === length}
                  >{length === 1 ? '1 juego' : `MD${length}`}</button>
                {/each}
              </div>
              <span class="small muted" title="Cómo se forman los cruces de la ronda. Al configurar una llave a mano el cuadro pasa a cruces fijas.">Cruces</span>
              <div class="phase-choices">
                {#each PAIRING_OPTIONS as option}
                  <button
                    type="button"
                    class={pairingOf(roundIndex) === option.value ? 'button' : 'button ghost'}
                    onclick={() => setPairing(roundIndex, option.value)}
                    title={option.help}
                    aria-pressed={pairingOf(roundIndex) === option.value}
                  >{option.label}</button>
                {/each}
              </div>
            </div>
            <div class="round-entries key-list">
              {#each keysAt(roundIndex) as bracketKey, keyIndex (bracketKey.number)}
                {@const config = keyConfig(roundIndex, keyIndex)}
                {@const currentKeyId = keyId(roundIndex, keyIndex)}
                <!-- Cerrada, la llave enseña hasta cuatro participantes (una
                     mini-liga de doce no puede alargar la columna doce filas).
                     Abierta, no enseña ninguno: los puertos de abajo dicen lo
                     mismo y además se pueden mover. -->
                {@const visibles = expandedKeys[currentKeyId] ? 0 : Math.min(bracketKey.slots.length, 4)}
                <article class="bracket-key" class:expanded={expandedKeys[currentKeyId]} class:incomplete={bracketKey.slots.includes(null)}>
                  <!--
                    La cabecera dice qué llave es y en qué se juega **sin
                    abrirla**: antes «Llave 3» y «MD7» vivían dentro del
                    pliegue, así que una columna de llaves cerradas eran cuatro
                    tarjetas iguales.
                  -->
                  <button
                    type="button"
                    class="key-summary"
                    aria-expanded={!!expandedKeys[currentKeyId]}
                    onclick={() => (expandedKeys = { ...expandedKeys, [currentKeyId]: !expandedKeys[currentKeyId] })}
                  >
                    <span class="key-head">
                      <b>Llave {bracketKey.number}</b>
                      <span class="key-badge">
                        {config.format === 'mini_league'
                          ? `Mini-liga · ${Math.max(3, config.participants)} equipos · pasan ${config.qualifying_positions.length}`
                          : playoffFormat === 'single_elimination'
                            ? 'Partido único'
                            : config.best_of === 1
                              ? '1 juego'
                              : `MD${config.best_of}`}{consolationKeys.has(currentKeyId)
                          ? ' · consolación'
                          : ''}
                      </span>
                      <span class="summary-toggle" aria-hidden="true">{expandedKeys[currentKeyId] ? '−' : '+'}</span>
                    </span>
                    {#each bracketKey.slots.slice(0, visibles) as slot, slotIndex}
                      <span class="summary-team">
                        <small>{slotIndex + 1}</small>
                        <strong>
                          {#if slot === null}
                            Por definir
                          {:else if 'winner' in slot}
                            {slot.token.endsWith(':loser')
                              ? 'Perdedor'
                              : slot.position
                                ? `${slot.position}.º clasificado`
                                : 'Ganador'} de llave {slot.winner + 1}
                          {:else}
                            {entryLabel(slot.division, slot.position)}
                          {/if}
                        </strong>
                      </span>
                    {/each}
                    {#if !expandedKeys[currentKeyId] && bracketKey.slots.length > visibles}
                      <span class="summary-team more">
                        <small>+</small>
                        <strong>y {bracketKey.slots.length - visibles} más</strong>
                      </span>
                    {/if}
                  </button>

                  {#if expandedKeys[currentKeyId]}
                  <div class="key-title">
                    <div class="key-mode" role="group" aria-label={`Modalidad de llave ${bracketKey.number}`}>
                      <button type="button" class:active={config.format === 'series'} onclick={() => configureKey(roundIndex, keyIndex, { format: 'series', participants: 2, qualifying_positions: [1] })}>Serie</button>
                      <button type="button" class:active={config.format === 'mini_league'} onclick={() => resizeMiniLeague(roundIndex, keyIndex, Math.max(3, config.participants))}>Mini-liga</button>
                    </div>
                  </div>
                  {#if config.format === 'mini_league'}
                    <div class="key-settings">
                      <span>Equipos</span>
                      <button type="button" disabled={config.participants <= 3} onclick={() => resizeMiniLeague(roundIndex, keyIndex, config.participants - 1)}>−</button>
                      <b>{Math.max(3, config.participants)}</b>
                      <button type="button" disabled={config.participants >= 64} onclick={() => resizeMiniLeague(roundIndex, keyIndex, config.participants + 1)}>+</button>
                      <span>Partidos por pareja</span>
                      {#each [1, 2, 3] as games}
                        <button type="button" class:active={config.games_per_pair === games} onclick={() => configureKey(roundIndex, keyIndex, { games_per_pair: games })}>{games}</button>
                      {/each}
                      <span>Avanzan</span>
                      <button type="button" disabled={config.qualifying_positions.length <= 1} onclick={() => resizeMiniQualifiers(roundIndex, keyIndex, config.qualifying_positions.length - 1)}>−</button>
                      <b>{config.qualifying_positions.length}</b>
                      <button type="button" disabled={config.qualifying_positions.length >= Math.max(3, config.participants) - 1} onclick={() => resizeMiniQualifiers(roundIndex, keyIndex, config.qualifying_positions.length + 1)}>+</button>
                    </div>
                  {:else}
                    <div class="key-settings">
                      <span>Serie</span>
                      {#each seriesOptions as length}
                        <button type="button" class:active={(playoffFormat === 'single_elimination' ? 1 : config.best_of) === length} disabled={playoffFormat === 'single_elimination'} onclick={() => configureKey(roundIndex, keyIndex, { best_of: length })}>{length === 1 ? '1' : `MD${length}`}</button>
                      {/each}
                    </div>
                  {/if}
                  {#each bracketKey.slots as slot, slotIndex (slotIndex)}
                    {@const absoluteSlot = keysAt(roundIndex).slice(0, keyIndex).reduce((total, key) => total + key.slots.length, 0) + slotIndex}
                    {@const slotTarget = `${roundIndex}:${absoluteSlot}`}
                    <div
                      class="key-port"
                      class:drop-active={keySlotTarget === slotTarget}
                      role="group"
                      aria-label={`Puerto ${slotIndex + 1} de la llave ${bracketKey.number}`}
                      ondragover={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        keySlotTarget = slotTarget;
                      }}
                      ondragleave={() => {
                        if (keySlotTarget === slotTarget) keySlotTarget = null;
                      }}
                      ondrop={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        dropOnKeySlot(roundIndex, absoluteSlot);
                      }}
                    >
                      {#if slot === null}
                        <div class="key-slot missing"><span>Suelta aquí el rival</span></div>
                      {:else if 'winner' in slot}
                        <div class="key-slot incoming" class:missing={slot.unresolved}>
                          <span class="pulse-dot"></span>
                          {slot.unresolved
                            ? 'Salida sin resolver'
                            : slot.token.endsWith(':loser')
                              ? 'Perdedor'
                              : (slot.position ? `${slot.position}.º` : 'Ganador')} de llave {slot.winner + 1} · {roundLabels[slot.sourceRound] || `Ronda ${slot.sourceRound + 1}`}
                        </div>
                      {:else}
                        {@const posicion = entrantsAt(roundIndex).findIndex((item) => entryId(item.division, item.position) === entryId(slot.division, slot.position))}
                        <div
                          class="key-slot entry-token"
                          class:wildcard={slot.division === null}
                          role="group"
                          aria-label={entryLabel(slot.division, slot.position)}
                          draggable="true"
                          ondragstart={() => (draggingEntry = { division: slot.division, position: slot.position })}
                          ondragend={() => {
                            draggingEntry = null;
                            roundDropTarget = null;
                            keySlotTarget = null;
                          }}
                        >
                          <span class="grip" aria-hidden="true">⠿</span>
                          <span class="entry-text">{entryLabel(slot.division, slot.position)}</span>
                          <span class="entry-arrows">
                            <button type="button" disabled={posicion === 0} onclick={() => reorderEntry(slot.division, slot.position, -1)} aria-label="Mover una posición arriba">↑</button>
                            <button type="button" disabled={posicion === entrantsAt(roundIndex).length - 1} onclick={() => reorderEntry(slot.division, slot.position, 1)} aria-label="Mover una posición abajo">↓</button>
                            <button type="button" disabled={roundIndex === 0} onclick={() => shiftRound(slot.division, slot.position, -1)} aria-label="Mover a la ronda anterior">←</button>
                            <button type="button" disabled={roundIndex === roundCount - 1} onclick={() => shiftRound(slot.division, slot.position, 1)} aria-label="Mover a la ronda siguiente">→</button>
                          </span>
                        </div>
                      {/if}
                    </div>
                  {/each}
                  {/if}

                  <!--
                    Las salidas viven **fuera** del cuerpo desplegable: son el
                    cableado del cuadro y antes sólo existían con la llave
                    abierta, así que con varias llaves no se veían. Cada una se
                    puede arrastrar a un puerto o conectar desde su lista.
                  -->
                  <div class="key-outputs">
                    {#if bracketKey.slots.includes(null)}
                      <span class="key-output unresolved">Salida sin resolver</span>
                    {:else}
                      {@const salidas = bracketKey.format === 'mini_league'
                        ? bracketKey.qualifying.map((position) => ({
                            token: `${currentKeyId}:position:${position}`,
                            texto: `${position}.º`,
                            opcional: false
                          }))
                        : [
                            { token: `${currentKeyId}:winner`, texto: 'Ganador', opcional: false },
                            { token: `${currentKeyId}:loser`, texto: 'Perdedor', opcional: true }
                          ]}
                      {@const destinos = destinosPara(roundIndex)}
                      {#each salidas as salida (salida.token)}
                        {@const ruta = bracketOutputRoutes[salida.token]}
                        <span class="key-output-group">
                          <button
                            type="button"
                            class="key-output"
                            class:routed={!!ruta}
                            class:optional={salida.opcional && !ruta}
                            draggable="true"
                            title={ruta
                              ? 'Conectada. Pulsa para desconectarla'
                              : salida.opcional
                                ? 'Sin conectar: este equipo queda eliminado. Arrástrala o usa «conectar» para darle otro partido'
                                : 'Arrástrala a un puerto posterior, o usa «conectar»'}
                            onclick={() => clearOutputRoute(salida.token)}
                            ondragstart={() => (draggingOutput = salida.token)}
                            ondragend={() => {
                              draggingOutput = null;
                              keySlotTarget = null;
                            }}
                          >⠿ {salida.texto} → {ruta
                            ? destinoLabel(ruta)
                            : salida.opcional
                              ? 'eliminado'
                              : roundIndex === roundCount - 1
                                ? consolationKeys.has(currentKeyId)
                                  ? '3.er puesto'
                                  : 'Campeón'
                                : 'siguiente ronda'}</button>
                          {#if destinos.length}
                            <button
                              type="button"
                              class="key-output-more"
                              aria-label={`Conectar la salida ${salida.texto} de la llave ${bracketKey.number}`}
                              aria-expanded={outputMenu === salida.token}
                              onclick={() => (outputMenu = outputMenu === salida.token ? null : salida.token)}
                            >⋯</button>
                          {/if}
                          {#if outputMenu === salida.token}
                            <div class="output-menu" role="menu">
                              <p class="small muted">Enviar a…</p>
                              {#each destinos as destino}
                                <button
                                  type="button"
                                  role="menuitem"
                                  onclick={() => connectOutput(salida.token, destino.round, destino.slot)}
                                >{destino.label}{destino.ocupado ? ' · ocupado' : ''}</button>
                              {/each}
                              {#if ruta}
                                <button type="button" role="menuitem" class="danger" onclick={() => { clearOutputRoute(salida.token); outputMenu = null; }}>Desconectar</button>
                              {/if}
                            </div>
                          {/if}
                        </span>
                      {/each}
                    {/if}
                  </div>
                </article>
              {/each}
              {#if flujo.participants === 0}
                <div class="round-drop-hint">
                  {roundIndex === 0
                    ? 'Suelta aquí los puestos que abren el cuadro'
                    : 'Solo ganadores. Suelta un puesto si alguien entra aquí'}
                </div>
              {/if}
            </div>

            <!--
              Los cruces los calcula el motor con la misma función que los
              formará en el campo, así que esto no es una maqueta de la
              política de emparejamiento: es la política.
            -->
            {#if cruces.length}
              <div class="round-crosses" aria-label={`Cruces de la ronda ${roundIndex + 1}`}>
                {#each cruces as cruce, indice (indice)}
                  <div class="cross">
                    <span>{cruce.high}</span>
                    <i aria-hidden="true">vs</i>
                    <span>{cruce.low}</span>
                  </div>
                {/each}
              </div>
            {/if}

            {#if roundIndex < roundCount - 1}<div class="animated-route" aria-hidden="true"></div>{/if}
          </section>
        {/each}

        <section class="champion-box">
          <span>CAMPEÓN</span>
          <strong aria-hidden="true">★</strong>
          <small>Destino final</small>
        </section>
      </div>

      <!--
        El plantel es también la papelera del cuadro: antes para sacar una
        plaza había que soltarla en una columna que ya no existe.
      -->
      <section
        class="postseason-pool-bottom"
        class:drop-active={poolIsTarget}
        aria-label="Quién entra al cuadro"
        ondragover={(event) => {
          event.preventDefault();
          poolIsTarget = true;
        }}
        ondragleave={() => (poolIsTarget = false)}
        ondrop={(event) => {
          event.preventDefault();
          poolIsTarget = false;
          dropOnPool();
        }}
      >
        <header>
          <div>
            <span class="eyebrow">QUIÉN ENTRA AL CUADRO</span>
            <strong>Puestos de origen, división por división</strong>
          </div>
          <small>
            Son <strong>puestos</strong>, no clubes todavía. Púlsalo para meterlo
            en {roundLabels[0] || 'la primera ronda'}, arrástralo al puerto exacto
            donde debe jugar, o suéltalo aquí para que deje de clasificar.
          </small>
        </header>
        <div class="bottom-pool-grid">
          {#each divisions as division (division.key)}
            <section class="bottom-division">
              <strong>{division.label}</strong>
              <div>
                {#each Array.from({ length: division.slots }, (_, index) => index + 1) as position}
                  {@const placedRound = roundOf(division.key, position)}
                  <button
                    type="button"
                    class:placed={placedRound !== null}
                    draggable="true"
                    onclick={() => toggleEntry(division.key, position)}
                    ondragstart={() => (draggingEntry = { division: division.key, position })}
                    ondragend={() => {
                      draggingEntry = null;
                      roundDropTarget = null;
                      keySlotTarget = null;
                    }}
                  >
                    <span>{position}.º</span>
                    <small>{placedRound === null ? 'fuera' : roundLabels[placedRound] || `R${placedRound + 1}`}</small>
                  </button>
                {/each}
              </div>
            </section>
          {/each}
          <section class="bottom-division general">
            <strong>Mejores restantes <span class="small muted">repesca</span></strong>
            <div>
              {#each Array.from({ length: generalRows }, (_, index) => index + 1) as position}
                {@const placedRound = roundOf(null, position)}
                <button
                  type="button"
                  class:placed={placedRound !== null}
                  draggable="true"
                  onclick={() => toggleEntry(null, position)}
                  ondragstart={() => (draggingEntry = { division: null, position })}
                  ondragend={() => {
                    draggingEntry = null;
                    roundDropTarget = null;
                    keySlotTarget = null;
                  }}
                >
                  <span>{position}.º restante</span>
                  <small>{placedRound === null ? 'libre' : roundLabels[placedRound] || `R${placedRound + 1}`}</small>
                </button>
              {/each}
            </div>
          </section>
        </div>
      </section>

      <!-- Los problemas los enseña la tira del taller, que está en todas las
           pestañas: repetirlos aquí era leer dos veces lo mismo. -->
      {#if !issues.length && bracket?.note}
        <div class="path-note small muted">{bracket.note}</div>
      {/if}
      <details class="engine-preview">
        <summary>Ver el cuadro completo calculado por el motor</summary>
        <BracketPreviewView {bracket} />
      </details>
    {:else}
      <div class="empty-canvas">
        <strong>El campeón sale de la tabla</strong>
        <small>El tablero queda guardado si después vuelves a activar la postemporada.</small>
      </div>
    {/if}
  </section>


    {:else if activeView === 'rules'}
  <!-- La tercera ficha sólo existe con divisiones, así que las columnas las
       dice cuántas fichas hay: con dos, no se queda un tercio en blanco. -->
  <section
    class="settings-grid"
    style={`--fichas:${divisions.length > 1 ? 3 : 2}`}
    aria-label="Reglas integradas al formato"
  >
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
  /*
    `app.css` da a `header` y `footer` el aspecto de la cabecera y el pie de la
    página: 18px de relleno, 24px de margen abajo, 40px de margen arriba y una
    línea. Dentro del taller hay seis de esos elementos —la cabecera de cada
    división, la de cada ronda, su pie, el plantel— y cada uno se estaba
    comiendo hasta 60px de alto que les hacían falta a las fichas. Esto los
    devuelve a cero. La clase puntúa más que la etiqueta, así que gana a
    `app.css`; y `:where` no suma nada, así que las reglas de abajo —que
    también valen una clase— ganan a esta por venir después.
  */
  .league-workbench .button.mini {
    min-height: 0;
    padding: 2px 6px;
    font-size: 0.72rem;
    line-height: 1.25;
  }

  .league-workbench :where(header, footer) {
    margin: 0;
    padding: 0;
    border: 0;
    color: inherit;
    font-size: inherit;
  }

  .tablero {
    /* Las divisiones se reparten el ancho en columnas iguales y bajan de fila
       cuando no caben. Una tira con desplazamiento horizontal escondía la
       mitad de las tablas y dejaba el resto del lienzo vacío. */
    display: grid;
    grid-template-columns: repeat(var(--columnas, 1), minmax(0, 1fr));
    grid-auto-rows: max-content;
    align-content: start;
    gap: 12px;
    padding-bottom: 6px;
  }
  .division {
    min-width: 0;
    max-width: 560px;
    display: flex;
    flex-direction: column;
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
    flex: 1 1 auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(186px, 1fr));
    grid-auto-rows: max-content;
    gap: 3px;
    min-height: 0;
    overflow: auto;
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
    max-width: 112px;
    overflow: hidden;
    padding: 1px 7px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: transparent;
    color: var(--muted);
    font-size: 0.7rem;
    white-space: nowrap;
    text-overflow: ellipsis;
    justify-self: start;
  }
  .insignia.clasifica {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 55%, var(--line));
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }
  .flechas {
    display: flex;
    gap: 2px;
  }
  .vacia {
    grid-column: 1 / -1;
    border: 1px dashed var(--line);
    border-radius: 6px;
    padding: 8px;
    text-align: center;
  }
  .division footer {
    flex: 0 0 auto;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid var(--line);
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
  .settings-heading {
    display: flex;
    align-items: flex-start;
    gap: 9px;
  }
  .settings-heading h4 {
    margin: 0;
    font-size: 0.88rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text);
  }
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
  .phase-choices {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 3px;
  }
  .phase-choices button { padding: 4px 7px; font-size: 0.7rem; }
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
  }
  .league-workbench {
    width: min(1760px, calc(100vw - 24px));
    height: auto;
    min-height: 820px;
    max-height: min(1280px, calc(100dvh - 70px));
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
  .workbench-body { position: relative; display: flex; flex-direction: column; gap: 6px; min-height: 0; overflow: hidden; }
  .view-panel { flex: 1 1 auto; min-height: 0; padding: 12px 16px; animation: view-enters 240ms ease-out both; }
  .issue-strip {
    flex: 0 0 auto;
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
  .structure-view { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; gap: 8px; }
  .view-heading { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
  .view-heading > div:first-child { display: grid; }
  .structure-canvas { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; min-height: 0; }
  .tablero { min-height: 0; overflow: auto; padding: 2px 2px 6px; }
  .plaza { min-height: 28px; }
  .structure-summary { margin: 0; }
  .schedule-view { display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 10px; }
  .date-control { display: grid; gap: 3px; align-content: start; }
  .date-control label { color: var(--muted); font-size: 0.72rem; }
  .date-control input { padding: 7px 9px; border: 1px solid var(--line); border-radius: 8px; color: var(--text); background: var(--panel); font: inherit; font-size: 0.82rem; }
  .date-control input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .calendar-block { display: grid; gap: 7px; }
  .linked-note { margin: 0; padding-top: 6px; border-top: 1px dotted var(--line); }
  /* Cinco controles a lo ancho dejaban «Partidos por visita» partido en dos
     líneas en una pantalla de 1366: mejor que bajen de fila. */
  .schedule-toolbar { display: grid; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); gap: 8px; }
  .weekday-control { display: flex; flex-direction: column; justify-content: center; padding: 7px 9px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); }
  .weekday-control .phase-choices { flex-wrap: nowrap; }
  .weekday-control button { min-width: 25px; padding: 4px; background: transparent; color: var(--muted); border: 1px solid var(--line); }
  .weekday-control button.active { color: #07120d; border-color: var(--accent); background: var(--accent); }
  /* Filas automáticas y un solo desplazamiento. Con `auto minmax(0, 1fr)` la
     tira de en medio —el calendario— se quedaba con la altura que sobrara y su
     contenido se salía por debajo, encima de la carga por club: tres bloques en
     dos filas declaradas. */
  .schedule-result { display: grid; grid-auto-rows: auto; align-content: start; min-height: 0; gap: 9px; overflow-y: auto; animation: data-refresh 260ms ease-out both; }
  .schedule-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; }
  .schedule-stats > span { display: flex; align-items: baseline; gap: 6px; padding: 6px 9px; border-left: 2px solid var(--accent); background: var(--panel-2); border-radius: 4px; }
  .schedule-stats strong { font: 700 1rem var(--mono); }
  .schedule-stats small { color: var(--muted); }
  .schedule-data-grid { display: grid; grid-template-columns: minmax(240px, 0.65fr) minmax(0, 1.35fr); gap: 10px; min-height: 0; }
  .club-load-table,
  .matchup-table-wrap { min-height: 0; max-height: 380px; overflow: auto; padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: color-mix(in srgb, var(--panel-2) 84%, transparent); }
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
  .settings-grid { flex: 1 1 auto; min-height: 0; margin: 0; padding: 12px 16px; grid-template-columns: repeat(var(--fichas, 3), minmax(280px, 470px)); justify-content: center; align-content: start; overflow: auto; animation: view-enters 240ms ease-out both; }
  .settings-table { min-height: 0; height: max-content; }
  .postseason-editor { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto auto; gap: 9px; overflow: hidden; }
  .postseason-toolbar { display: grid; gap: 1px; }
  .postseason-toolbar h4 { margin: 2px 0; font-size: 1.35rem; letter-spacing: -0.02em; }
  .postseason-toolbar p { max-width: 860px; margin: 0; }
  .postseason-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 7px 9px; border: 1px solid var(--line); border-radius: 10px; background: color-mix(in srgb, var(--panel-2) 70%, transparent); }
  .postseason-controls .path-summary { margin-left: auto; }
  .round-add { flex: 0 0 auto; white-space: nowrap; }
  .path-summary { display: flex; flex-wrap: wrap; gap: 6px; }
  .path-summary span { padding: 4px 8px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); background: var(--panel-2); font-size: 0.68rem; }
  .path-summary strong { color: var(--text); font-family: var(--mono); }
  .path-summary .flow-ok { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 52%, var(--line)); }
  .path-summary .flow-bad { color: var(--accent-2); border-color: color-mix(in srgb, var(--accent-2) 52%, var(--line)); }
  .kanban { display: flex; align-items: stretch; gap: 64px; min-height: 0; overflow: auto; padding: 18px 72px 28px 10px; }
  .bracket-roadmap {
    position: relative;
    border: 1px solid color-mix(in srgb, var(--accent) 18%, var(--line));
    border-radius: 16px;
    background:
      radial-gradient(circle at 100% 50%, color-mix(in srgb, var(--accent-2) 10%, transparent), transparent 25%),
      linear-gradient(90deg, color-mix(in srgb, var(--panel-2) 92%, transparent), color-mix(in srgb, var(--panel) 97%, transparent)),
      repeating-linear-gradient(0deg, transparent 0 47px, color-mix(in srgb, var(--line) 28%, transparent) 48px);
  }
  .round-crosses { flex: 0 0 auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(208px, 1fr)); gap: 3px 12px; max-height: 92px; overflow: auto; padding-top: 5px; border-top: 1px dashed var(--line); }
  .cross { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: 5px; align-items: center; font-size: 0.64rem; }
  .cross span { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .cross span:last-child { text-align: right; }
  .cross i { color: var(--muted); font: 0.58rem var(--mono); font-style: normal; }
  .entry-text { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .path-note { padding: 4px 2px; }
  .editable-round { position: relative; flex: 0 0 390px; min-width: 390px; max-width: 390px; display: flex; flex-direction: column; gap: 14px; padding: 0; border: 0; background: transparent; transition: transform 150ms ease; }
  .editable-round::before { content: ''; position: absolute; z-index: 0; top: 76px; bottom: 76px; left: -65px; width: 2px; background: color-mix(in srgb, var(--accent) 52%, var(--line)); }
  .editable-round.drop-active { transform: translateY(-3px); }
  .editable-round.invalid .round-editor-header { border-color: var(--accent-2); }
  .round-editor-header { position: relative; z-index: 0; flex: 0 0 auto; display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; gap: 9px; align-items: center; min-height: 48px; margin-bottom: 30px; padding: 7px 10px; border: 1px solid color-mix(in srgb, var(--accent) 34%, var(--line)); border-radius: 10px; background: color-mix(in srgb, var(--panel-2) 96%, transparent); }
  .round-number { color: var(--accent); font-size: 0.7rem; }
  .round-name { min-width: 0; padding: 7px 9px; border: 0; border-bottom: 1px solid transparent; border-radius: 0; color: var(--text); background: transparent; font-size: 1.08rem; font-weight: 700; }
  .round-name:hover, .round-name:focus { border-bottom-color: var(--accent); outline: none; }
  .round-count { padding: 2px 5px; border-radius: 99px; color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); font: 0.64rem var(--mono); }
  .round-count.bad { color: var(--accent-2); background: color-mix(in srgb, var(--accent-2) 12%, transparent); }
  /* `safe center` y no `center`: centrado a secas, una columna con más llaves
     que altura se desborda hacia arriba y tapa las reglas de la ronda. */
  .round-entries { flex: 1 1 auto; display: grid; grid-template-columns: 1fr; align-content: safe center; min-height: 220px; overflow: visible; }
  .key-list { position: relative; z-index: 2; gap: calc(18px + var(--round-depth) * 34px); padding-top: calc(20px + var(--round-depth) * 22px); padding-bottom: calc(var(--round-depth) * 22px); }
  .bracket-key { position: relative; z-index: 2; display: grid; gap: 8px; padding: 12px; border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--line)); border-radius: 10px; background: color-mix(in srgb, var(--panel) 96%, transparent); box-shadow: 0 10px 28px rgb(0 0 0 / 20%); }
  .bracket-key::before { content: ''; position: absolute; top: 50%; left: -65px; width: 64px; height: 2px; background: color-mix(in srgb, var(--accent) 70%, var(--line)); }
  .bracket-key::after { content: ''; position: absolute; top: 50%; right: -65px; width: 64px; height: 2px; background: color-mix(in srgb, var(--accent) 70%, var(--line)); }
  .bracket-key.incomplete { border-style: dashed; border-color: var(--accent-2); }
  .key-title { display: flex; align-items: center; color: var(--muted); font: 700 0.62rem var(--mono); text-transform: uppercase; letter-spacing: 0.5px; }
  .key-mode, .key-settings { display: flex; align-items: center; gap: 3px; }
  .key-mode button, .key-settings button { min-width: 0; padding: 5px 8px; border: 1px solid var(--line); border-radius: 5px; color: var(--muted); background: transparent; font: 0.68rem var(--mono); }
  .key-mode button.active, .key-settings button.active { color: #07120d; border-color: var(--accent); background: var(--accent); }
  .key-settings { flex-wrap: wrap; padding: 4px 0 5px; color: var(--muted); font-size: 0.72rem; }
  .key-settings span:not(:first-child) { margin-left: 5px; }
  .key-port { border-radius: 7px; transition: outline-color 120ms ease, transform 120ms ease; }
  .key-port.drop-active { outline: 2px solid var(--accent-2); outline-offset: 1px; transform: translateX(2px); }
  .key-slot { min-height: 56px; display: flex; align-items: center; padding: 12px 14px; border: 1px solid var(--line); border-radius: 9px; background: var(--panel-2); color: var(--muted); font-size: 0.86rem; }
  .key-slot.entry-token { display: grid; }
  .key-slot.incoming { border-left: 3px solid var(--accent); }
  .key-slot.missing { justify-content: center; border-style: dashed; border-color: var(--accent-2); color: var(--accent-2); }
  /* Las salidas son el cableado del cuadro, no un pie de nota: se ven con la
     llave cerrada y tienen tamaño de botón, no de etiqueta. */
  .key-outputs { display: grid; gap: 4px; padding: 6px 9px 7px; border-top: 1px dotted var(--line); }
  .bracket-key.expanded > .key-outputs { margin: 0 -12px -12px; padding: 7px 12px 10px; }
  .key-output-group { position: relative; display: flex; align-items: center; gap: 3px; }
  .key-output { flex: 1 1 auto; min-width: 0; padding: 4px 9px; text-align: left; border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--line)); border-radius: 99px; color: var(--muted); background: var(--panel-2); font: 0.66rem var(--mono); cursor: grab; }
  .key-output.routed { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, var(--panel-2)); color: var(--text); }
  /* Un perdedor sin conectar está *disponible*, no deshabilitado: antes iba a
     opacidad 0.55 y se leía como una opción apagada. */
  .key-output.optional { border-style: dashed; border-color: color-mix(in srgb, var(--accent-2) 48%, var(--line)); color: var(--accent-2); }
  .key-output.unresolved { color: var(--accent-2); border-color: var(--accent-2); cursor: default; }
  .key-output-more { width: 21px; height: 21px; display: grid; place-items: center; border: 1px solid var(--line); border-radius: 99px; background: var(--panel-2); color: var(--muted); font-size: 0.72rem; line-height: 1; cursor: pointer; }
  .key-output-more:hover, .key-output-more[aria-expanded='true'] { border-color: var(--accent); color: var(--text); }
  .output-menu { position: absolute; z-index: 30; top: calc(100% + 5px); right: 0; min-width: 210px; max-height: 250px; overflow-y: auto; display: grid; gap: 2px; padding: 7px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); box-shadow: 0 14px 34px rgb(0 0 0 / 34%); text-align: left; }
  .output-menu p { margin: 0 0 3px; }
  .output-menu button { padding: 5px 7px; border: 0; border-radius: 7px; background: transparent; color: var(--text); font-size: 0.73rem; text-align: left; cursor: pointer; }
  .output-menu button:hover { background: var(--panel-2); }
  .output-menu button.danger { color: var(--accent-2); }
  .round-entries > .round-drop-hint { grid-column: 1 / -1; }
  /* Una ronda a la que solo llegan ganadores no tiene fichas que
     alinear arriba: su mensaje se queda en medio de la columna en vez
     de dejar un vacío de media altura debajo. */
  .round-entries:has(> .round-drop-hint) { align-content: safe center; }
  .entry-token { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 4px; align-items: center; padding: 4px 6px; border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--line)); border-left: 3px solid var(--accent); border-radius: 7px; background: var(--panel); font-size: 0.7rem; cursor: grab; animation: entrant-arrives 200ms ease-out both; }
  .entry-token.wildcard { border-color: color-mix(in srgb, var(--accent-2) 42%, var(--line)); border-left-color: var(--accent-2); }
  .grip { color: var(--muted); }
  .entry-arrows { display: flex; gap: 1px; }
  .entry-arrows button { width: 17px; height: 19px; padding: 0; border: 1px solid var(--line); border-radius: 4px; color: var(--muted); background: var(--panel-2); font-size: 0.65rem; }
  .entry-arrows button:disabled { opacity: 0.2; }
  .round-drop-hint { display: grid; min-height: 50px; place-items: center; border: 1px dashed var(--line); border-radius: 7px; color: var(--muted); font-size: 0.68rem; }
  .pulse-dot { display: inline-block; width: 6px; height: 6px; margin-right: 4px; border-radius: 50%; background: var(--accent); animation: live-pulse 1.2s ease-in-out infinite; }
  /* Las reglas de la ronda, justo bajo su nombre: se leen como suyas y no
     como un pie de página a la altura que toque. */
  .round-rules { flex: 0 0 auto; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 7px; align-items: center; margin: -10px 0 10px; padding: 0 0 8px; border-bottom: 1px dotted var(--line); }
  .round-rules .phase-choices { flex-wrap: wrap; justify-content: flex-end; margin: 0; gap: 3px; }
  .round-rules .phase-choices button { min-width: max-content; padding: 2px 5px; font-size: 0.64rem; }
  .animated-route { display: none; }
  .champion-box { position: relative; flex: 0 0 180px; align-self: center; display: grid; place-content: center; justify-items: center; gap: 8px; min-height: 220px; padding: 18px; border: 1px solid color-mix(in srgb, var(--accent-2) 65%, var(--line)); border-radius: 90px 90px 18px 18px; background: radial-gradient(circle at 50% 35%, color-mix(in srgb, var(--accent-2) 24%, var(--panel)), var(--panel-2) 68%); box-shadow: 0 0 42px color-mix(in srgb, var(--accent-2) 17%, transparent); }
  .champion-box::before { content: ''; position: absolute; top: 50%; left: -73px; width: 72px; height: 2px; background: var(--accent-2); }
  .champion-box span { color: var(--accent-2); font: 800 0.72rem var(--mono); letter-spacing: 1.4px; }
  .champion-box strong { display: grid; width: 82px; height: 82px; place-items: center; border: 2px solid var(--accent-2); border-radius: 50%; color: var(--accent-2); font-size: 2.7rem; background: color-mix(in srgb, var(--accent-2) 9%, var(--panel)); }
  .champion-box small { color: var(--muted); }
  .bracket-roadmap .round-crosses { display: none; }
  .bracket-roadmap .bracket-key::before { left: -34px; width: 33px; }
  .bracket-roadmap .bracket-key::after { right: -34px; width: 33px; }
  .bracket-roadmap .champion-box::before { left: -35px; width: 34px; }
  /* La primera ronda no recibe a nadie: su cable entraría desde el borde. */
  .bracket-roadmap .editable-round.first-round .bracket-key::before { display: none; }
  .engine-preview { max-height: 34px; overflow: auto; color: var(--muted); font-size: 0.7rem; }
  .engine-preview[open] { max-height: 320px; }
  .engine-preview summary { cursor: pointer; }

  /* Vista del cuadro: la edición fina vive dentro de la llave que el usuario
     abra, pero los mandos de la competición (formato, rondas, estado del
     camino) se quedan a la vista. Antes se ocultaban con `display: none` y el
     editor quedaba sin forma de cambiar el formato ni de quitar una ronda. */
  .editable-round::before { display: none; }
  .bracket-roadmap {
    gap: 34px;
    padding: 18px 24px 28px;
    border-color: var(--line);
    background: var(--panel);
  }
  .editable-round {
    flex-basis: 330px;
    min-width: 330px;
    max-width: 330px;
  }
  .round-editor-header {
    min-height: 38px;
    margin-bottom: 18px;
    padding: 2px 0 8px;
    grid-template-columns: auto minmax(0, 1fr) auto auto;
    border: 0;
    border-bottom: 1px solid var(--line);
    border-radius: 0;
    background: transparent;
  }
  .round-name { font-size: 0.9rem; }
  .key-list { gap: calc(18px + var(--round-depth) * 20px); padding-top: 4px; }
  .bracket-key {
    gap: 0;
    padding: 0;
    border-color: var(--line);
    border-radius: 8px;
    background: var(--panel-2);
    box-shadow: none;
    /* `overflow: hidden` recortaba el menú de destinos de las salidas. */
    overflow: visible;
  }
  .bracket-key.expanded { gap: 9px; }
  /* Con el menú abierto la tarjeta sube de plano: todas las llaves comparten
     z-index 2, así que la de abajo tapaba la lista de destinos. */
  .bracket-key:has(.output-menu) { z-index: 40; }
  .key-head { display: flex; align-items: center; gap: 7px; padding: 6px 10px; border-bottom: 1px solid var(--line); border-radius: 7px 7px 0 0; background: color-mix(in srgb, var(--accent) 7%, transparent); }
  .key-head b { color: var(--text); font: 700 0.64rem var(--mono); letter-spacing: 0.5px; }
  .key-badge { overflow: hidden; color: var(--muted); font: 0.63rem var(--mono); white-space: nowrap; text-overflow: ellipsis; }
  .bracket-key.incomplete { border-color: var(--line); border-style: solid; }
  .bracket-key.expanded { padding: 12px; border-color: color-mix(in srgb, var(--accent) 48%, var(--line)); }
  .key-summary {
    position: relative;
    width: 100%;
    display: grid;
    gap: 0;
    padding: 0;
    border: 0;
    border-radius: inherit;
    color: var(--text);
    background: transparent;
    text-align: left;
  }
  .summary-team {
    min-height: 42px;
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr);
    gap: 8px;
    align-items: center;
    padding: 7px 10px;
    border-bottom: 1px solid var(--line);
  }
  .summary-team:last-of-type { border-bottom: 0; }
  .summary-team.more strong { color: var(--muted); font-weight: 400; }
  .summary-team small { color: var(--muted); font: 0.64rem var(--mono); }
  .summary-team strong { overflow: hidden; font-size: 0.78rem; font-weight: 600; white-space: nowrap; text-overflow: ellipsis; }
  .summary-toggle { margin-left: auto; color: var(--muted); font: 1rem var(--mono); }
  .bracket-key.expanded .key-summary { margin: -12px -12px 2px; width: calc(100% + 24px); border-bottom: 1px solid var(--line); border-radius: 0; }
  .champion-box {
    flex-basis: 130px;
    min-height: 150px;
    padding: 12px;
    border-color: var(--line);
    border-radius: 8px;
    background: var(--panel-2);
    box-shadow: none;
  }
  .champion-box strong { width: 54px; height: 54px; border-width: 1px; font-size: 1.7rem; }
  .postseason-pool-bottom {
    display: grid;
    gap: 10px;
    max-height: 270px;
    padding: 12px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--panel-2);
    overflow: auto;
  }
  .postseason-pool-bottom > header { display: flex; justify-content: space-between; gap: 16px; align-items: end; }
  .postseason-pool-bottom > header > div { display: grid; }
  .postseason-pool-bottom > header small { color: var(--muted); }
  .bottom-pool-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; align-items: start; }
  .bottom-division { display: grid; gap: 6px; padding: 9px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
  .bottom-division > strong { font-size: 0.76rem; }
  .bottom-division > div { display: grid; grid-template-columns: repeat(auto-fill, minmax(82px, 1fr)); gap: 5px; }
  .bottom-division button { min-width: 0; display: grid; gap: 1px; padding: 6px 7px; border: 1px solid var(--line); border-radius: 6px; color: var(--text); background: var(--panel-2); text-align: left; cursor: grab; }
  .bottom-division button span { font: 700 0.7rem var(--mono); }
  .bottom-division button small { overflow: hidden; color: var(--muted); font-size: 0.61rem; white-space: nowrap; text-overflow: ellipsis; }
  .bottom-division button.placed { border-color: color-mix(in srgb, var(--accent) 48%, var(--line)); background: color-mix(in srgb, var(--accent) 8%, var(--panel-2)); }
  .bottom-division.general > strong { color: var(--accent-2); }
  /* Las fichas de entrada la pedían desde que existe el tablero, pero el
     fotograma vivía en otro componente y el CSS de Svelte va por componente,
     así que nunca llegaba: la ficha aparecía de golpe. */
  @keyframes entrant-arrives { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: translateX(0); } }
  @keyframes view-enters { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes data-refresh { from { opacity: 0.45; } to { opacity: 1; } }
  @keyframes live-pulse { 50% { opacity: 0.45; transform: scale(0.75); } }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 980px) {
    .league-workbench { height: auto; min-height: 690px; max-height: none; }
    .workbench-header { grid-template-columns: 1fr auto; }
    .live-metrics { grid-column: 1 / -1; grid-row: 2; justify-content: flex-start; }
    .schedule-toolbar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .settings-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .tablero { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .postseason-editor { overflow: auto; }
    .kanban { min-height: 380px; }
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
    .tablero { grid-template-columns: minmax(0, 1fr); }
    .schedule-toolbar,
    .schedule-data-grid,
    .settings-grid { grid-template-columns: 1fr; }
    .schedule-data-grid { overflow: auto; }
    .postseason-toolbar { flex-direction: column; gap: 6px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .live-metrics .live::before,
    .loader-ring,
    .view-panel,
    .settings-grid,
    .schedule-result { animation: none; }
  }
</style>
