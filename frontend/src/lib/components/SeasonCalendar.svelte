<script lang="ts">
  /**
   * El calendario de la temporada, mes a mes.
   *
   * Las cifras del paso de calendario dicen cuántos partidos hay y cuántos
   * días dura la temporada, pero no **cuándo** se juega: si la liga arranca en
   * abril, si se juega los sábados, si tu club descansa dos semanas en junio.
   * Eso solo se ve en un calendario de los de toda la vida, con sus meses y
   * sus días, y por eso aquí hay uno y no otra tabla.
   */
  const DIAS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
  const MESES = [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre'
  ];

  type Juego = { home: string; away: string; group: string; matchup: string };

  interface Props {
    /** Días con partido, en orden, tal como los calcula el motor. */
    calendar?: Array<{ date: string; games: Juego[] }>;
    clubs?: Array<{ key: string; label: string; group: string }>;
    firstDate?: string | null;
    lastDate?: string | null;
    /** Días cerrados de la semana, 0 = lunes. */
    restDays?: number[];
    /** `false` si la temporada tiene más días de los que caben en la vista. */
    complete?: boolean;
  }

  let {
    calendar = [],
    clubs = [],
    firstDate = null,
    lastDate = null,
    restDays = [],
    complete = true
  }: Props = $props();

  const porDia = $derived(new Map(calendar.map((dia) => [dia.date, dia.games])));
  const etiqueta = $derived(new Map(clubs.map((club) => [club.key, club.label])));
  const cerrados = $derived(new Set(restDays));

  /** Una fecha ISO a `Date` **local**: `new Date('2043-04-05')` es UTC y en
   *  husos al oeste se va al día anterior, que corre todo el calendario. */
  function desdeISO(iso: string): Date {
    const [anio, mes, dia] = iso.split('-').map(Number);
    return new Date(anio, mes - 1, dia);
  }

  function aISO(fecha: Date): string {
    const mes = String(fecha.getMonth() + 1).padStart(2, '0');
    const dia = String(fecha.getDate()).padStart(2, '0');
    return `${fecha.getFullYear()}-${mes}-${dia}`;
  }

  /** Lunes = 0, como los días de descanso del reglamento. */
  function columna(fecha: Date): number {
    return (fecha.getDay() + 6) % 7;
  }

  const meses = $derived.by(() => {
    const desde = firstDate ?? calendar[0]?.date ?? null;
    const hasta = lastDate ?? calendar.at(-1)?.date ?? null;
    if (!desde || !hasta) return [];
    const inicio = desdeISO(desde);
    const fin = desdeISO(hasta);
    const salida: Array<{ anio: number; mes: number; celdas: Array<string | null> }> = [];
    const cursor = new Date(inicio.getFullYear(), inicio.getMonth(), 1);
    while (cursor <= fin) {
      const anio = cursor.getFullYear();
      const mes = cursor.getMonth();
      const primero = new Date(anio, mes, 1);
      const dias = new Date(anio, mes + 1, 0).getDate();
      const celdas: Array<string | null> = Array.from({ length: columna(primero) }, () => null);
      for (let dia = 1; dia <= dias; dia += 1) celdas.push(aISO(new Date(anio, mes, dia)));
      salida.push({ anio, mes, celdas });
      cursor.setMonth(mes + 1);
    }
    return salida;
  });

  let elegido = $state<string | null>(null);
  const diaVisible = $derived(elegido ?? calendar[0]?.date ?? null);
  const partidosDelDia = $derived(diaVisible ? (porDia.get(diaVisible) ?? []) : []);

  function enTemporada(iso: string): boolean {
    if (firstDate && iso < firstDate) return false;
    if (lastDate && iso > lastDate) return false;
    return true;
  }

  function texto(iso: string): string {
    const fecha = desdeISO(iso);
    return `${fecha.getDate()} de ${MESES[fecha.getMonth()]} de ${fecha.getFullYear()}`;
  }
</script>

{#if meses.length}
  <div class="season-calendar">
    <div class="months">
      {#each meses as mes (`${mes.anio}-${mes.mes}`)}
        <section class="month" aria-label={`${MESES[mes.mes]} de ${mes.anio}`}>
          <header>
            <strong>{MESES[mes.mes]}</strong>
            <span class="mono small muted">{mes.anio}</span>
          </header>
          <div class="weekdays" aria-hidden="true">
            {#each DIAS as dia, indice}
              <span class:closed={cerrados.has(indice)}>{dia}</span>
            {/each}
          </div>
          <div class="days">
            {#each mes.celdas as iso, indice (indice)}
              {#if iso === null}
                <span class="pad"></span>
              {:else}
                {@const juegos = porDia.get(iso) ?? []}
                <button
                  type="button"
                  class="day"
                  class:has-games={juegos.length > 0}
                  class:off-season={!enTemporada(iso)}
                  class:closed={cerrados.has(columna(desdeISO(iso)))}
                  class:selected={diaVisible === iso}
                  disabled={juegos.length === 0}
                  aria-label={juegos.length
                    ? `${texto(iso)}: ${juegos.length} partido${juegos.length === 1 ? '' : 's'}`
                    : texto(iso)}
                  onclick={() => (elegido = iso)}
                >
                  <b>{desdeISO(iso).getDate()}</b>
                  {#if juegos.length}
                    <i>{juegos.length}</i>
                  {/if}
                </button>
              {/if}
            {/each}
          </div>
        </section>
      {/each}
    </div>

    <aside class="day-detail" aria-live="polite">
      {#if diaVisible}
        <span class="eyebrow">JORNADA</span>
        <strong>{texto(diaVisible)}</strong>
        <p class="small muted">
          {partidosDelDia.length} partido{partidosDelDia.length === 1 ? '' : 's'}. Son los
          cruces que el motor ya tiene calculados; los clubes todavía no existen,
          así que juegan con su número de plaza.
        </p>
        <ul>
          {#each partidosDelDia as juego, indice (indice)}
            <li>
              <span>{etiqueta.get(juego.away) ?? juego.away}</span>
              <i>en</i>
              <span>{etiqueta.get(juego.home) ?? juego.home}</span>
              {#if juego.group}<small class="mono">{juego.group}</small>{/if}
            </li>
          {/each}
        </ul>
      {:else}
        <p class="small muted">Elige un día con partido.</p>
      {/if}
      {#if !complete}
        <p class="small muted truncated">
          La temporada tiene más días de los que caben en esta vista: se muestran
          los primeros. El calendario completo se construye al crear la liga.
        </p>
      {/if}
    </aside>
  </div>
{:else}
  <p class="small muted">El calendario aparece cuando el motor termina de calcularlo.</p>
{/if}

<style>
  .season-calendar {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(210px, 264px);
    gap: 14px;
    align-items: start;
  }
  /* `auto-fit` y no `auto-fill`: con dos meses, las pistas vacías se colapsan
     y los dos se reparten el ancho en vez de amontonarse a la izquierda. El
     tope de cada mes evita que una temporada corta dibuje dos calendarios
     gigantes. */
  .months {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(214px, 1fr));
    justify-items: start;
    gap: 12px;
    max-height: 340px;
    overflow: auto;
    padding-right: 4px;
  }
  .month {
    width: 100%;
    max-width: 320px;
    display: grid;
    gap: 5px;
    padding: 9px 10px 11px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--panel);
  }
  .month header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 6px;
  }
  .month header strong {
    font-size: 0.82rem;
    text-transform: capitalize;
  }
  .weekdays,
  .days {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 2px;
  }
  .weekdays span {
    color: var(--muted);
    font: 700 0.58rem var(--mono);
    text-align: center;
  }
  .weekdays span.closed {
    color: color-mix(in srgb, var(--muted) 55%, transparent);
  }
  .pad {
    min-height: 26px;
  }
  .day {
    position: relative;
    min-height: 26px;
    display: grid;
    place-items: center;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--muted);
    background: transparent;
    font: 0.66rem var(--mono);
    cursor: default;
  }
  /* Un día cerrado por reglamento se lee como hueco de la semana, no como un
     día cualquiera sin partido: es la forma del calendario. */
  .day.closed {
    background: color-mix(in srgb, var(--line) 22%, transparent);
  }
  .day.off-season {
    opacity: 0.35;
  }
  .day.has-games {
    color: var(--text);
    border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
    background: color-mix(in srgb, var(--accent) 13%, transparent);
    cursor: pointer;
  }
  .day.has-games:hover {
    border-color: var(--accent);
  }
  .day.selected {
    border-color: var(--accent-2);
    background: color-mix(in srgb, var(--accent-2) 22%, transparent);
  }
  .day b {
    font-weight: 600;
  }
  .day i {
    position: absolute;
    right: 2px;
    bottom: 1px;
    color: var(--accent);
    font: 700 0.5rem var(--mono);
    font-style: normal;
  }
  .day-detail {
    display: grid;
    gap: 4px;
    align-content: start;
    max-height: 340px;
    overflow: auto;
    padding: 11px 12px;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--panel-2);
  }
  .day-detail p {
    margin: 0;
  }
  .day-detail ul {
    display: grid;
    gap: 3px;
    margin: 4px 0 0;
    padding: 0;
    list-style: none;
  }
  .day-detail li {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 5px;
    padding: 5px 7px;
    border: 1px solid var(--line);
    border-radius: 7px;
    background: var(--panel);
    font-size: 0.74rem;
  }
  .day-detail li i {
    color: var(--muted);
    font-size: 0.66rem;
    font-style: normal;
  }
  .day-detail li small {
    margin-left: auto;
    color: var(--muted);
    font-size: 0.6rem;
  }
  .truncated {
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px dotted var(--line);
  }
  @media (max-width: 980px) {
    .season-calendar {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
