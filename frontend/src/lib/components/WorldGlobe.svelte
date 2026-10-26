<!--
  Globo terráqueo del selector territorial.

  La geometría de los países es la del atlas mundial de Natural Earth
  (`world-atlas`, dominio público) y se resuelve por su código ISO 3166-1
  numérico, no por su nombre: un clic sobre un polígono le pregunta al backend
  por ese ISO y lo que se fija es la entidad del gazetteer, no la etiqueta del
  mapa. Los tres territorios del atlas sin código —Kosovo, Somalilandia y el
  norte de Chipre— no son seleccionables, y el globo lo dice al pasar por
  encima en vez de inventarles una identidad.

  Las provincias y localidades no se dibujan como contornos, porque no tenemos
  sus polígonos: son puntos sobre la esfera en la coordenada que el backend
  considera representativa (`map_lat`/`map_lon`). Un punto no finge una
  frontera que no está en la fuente.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { GlobeInstance } from 'globe.gl';
  import type { GeometryCollection, Topology } from 'topojson-specification';

  /** Un punto seleccionable de la esfera: una provincia o una localidad. */
  export interface GlobePlace {
    id: string;
    name: string;
    lat: number;
    lng: number;
    /** `chosen`: ya es territorio de la competición; se marca con un anillo. */
    state: 'selectable' | 'chosen';
  }

  export type GlobeLayer = 'countries' | 'regions' | 'localities';

  interface Props {
    layer: GlobeLayer;
    places: GlobePlace[];
    /** País resaltado y encuadrado por la cámara. */
    focusIso2?: string | null;
    /** Países que ya son territorio de la competición. */
    chosenIso2?: string[];
    /** Punto al que acercarse dentro del país: la provincia en curso. */
    focusPlace?: { lat: number; lng: number } | null;
    disabled?: boolean;
    oncountrypick: (iso2: string, name: string) => void;
    onplacepick: (id: string) => void;
    /** Un polígono que el atlas no puede resolver a un ISO 3166-1. */
    onunresolved?: (name: string) => void;
  }

  let {
    layer,
    places,
    focusIso2 = null,
    chosenIso2 = [],
    focusPlace = null,
    disabled = false,
    oncountrypick,
    onplacepick,
    onunresolved
  }: Props = $props();

  /** Paleta del globo: son colores de material WebGL, no de CSS. */
  const SKIN = {
    ocean: '#0b1a22',
    land: '#2a404e',
    landEdge: '#4a6474',
    landHover: '#2f5649',
    focus: '#4b9b7a',
    chosen: '#63bf93',
    atmosphere: '#4b9b7a',
    place: '#d9c25e',
    placeChosen: '#63bf93'
  };

  // La cámara abarca unos 53° de arco por cada unidad de altitud, que se mide
  // en radios del globo sobre la superficie: de ahí sale el encuadre de todo
  // lo que se enseña, del mundo entero a una provincia.
  const WORLD_ALTITUDE = 2.2;
  const ARC_PER_ALTITUDE = 53;
  /** Altitud mínima: por debajo, los controles de órbita frenarían el vuelo. */
  const MIN_ALTITUDE = 0.08;
  /** Aire alrededor de lo encuadrado, para que no quede pegado al borde. */
  const FRAME_MARGIN = 1.3;
  /** Destino cuando hay un punto al que ir pero nada que encuadrar con él. */
  const PLACE_ALTITUDE = 0.2;
  /** Por debajo de esta altitud los puntos muestran su nombre. */
  const LABEL_ALTITUDE = 1.3;
  /**
   * Relieve de cada capa, en radios del globo. Los países se extruyen un poco
   * —más el que está en foco— y los puntos tienen que ir por encima del más
   * alto: si no, la tapa del país en foco los entierra y la provincia aparece
   * vacía de localidades.
   */
  const RELIEF = { land: 0.006, hover: 0.011, focus: 0.015, place: 0.024 };
  /**
   * Cuántos puntos llevan nombre. Una provincia con doscientas localidades no
   * cabe rotulada: se nombran las primeras que llegan —el orden es el de
   * relevancia, población descendente— siempre que no se pisen con otra ya
   * nombrada. El resto se quedan en punto, con su nombre al pasar por encima;
   * la lista que acompaña al globo los tiene todos.
   */
  const MAX_LABELLED = 18;
  /**
   * El hueco que ocupa un rótulo, como fracción del arco visible: ancho y bajo,
   * porque es una línea de texto. Dos nombres que caen dentro del mismo hueco
   * se pisarían, así que solo se queda el primero —el más relevante—.
   */
  const LABEL_BOX = { lat: 0.04, lng: 0.17 };

  /** Lo único que el atlas trae de cada polígono, además de su ISO numérico. */
  type AtlasProperties = { name?: string };

  /** Lo que el atlas sabe de un país, ya encuadrado para la cámara. */
  interface CountryShape {
    iso2: string | null;
    name: string;
    lat: number;
    lng: number;
    altitude: number;
  }

  let host = $state<HTMLDivElement | null>(null);
  let globe: GlobeInstance | null = null;
  let ready = $state(false);
  let failure = $state<string | null>(null);
  let hoveredIso2 = $state<string | null>(null);
  let altitude = $state(WORLD_ALTITUDE);
  /** Altitud del último encuadre: las etiquetas se miden contra ella. */
  let frameAltitude = $state(WORLD_ALTITUDE);
  /** Destino del último vuelo, para no repetirlo en cada cambio de datos. */
  let flownTo = '';
  /** Puntos que llevan nombre; lo lee el constructor de cada marcador. */
  let named = new Set<string>();
  let spinning = $state(true);
  /** El polígono que dibuja el globo → su ficha del atlas. */
  const shapeOf = new WeakMap<object, CountryShape>();
  /** ISO 3166-1 alfa-2 → encuadre, para llevar la cámara a un país. */
  const framesByIso2 = new Map<string, CountryShape>();

  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const flightMs = reducedMotion ? 0 : 900;

  const showLabels = $derived(altitude <= LABEL_ALTITUDE);
  const countriesPickable = $derived(layer === 'countries' && !disabled);

  onMount(() => {
    let destroyed = false;
    let observer: ResizeObserver | null = null;

    (async () => {
      try {
        // Carga diferida: `globe.gl` arrastra three.js y necesita `window`, así
        // que no puede existir durante el renderizado en servidor.
        const [{ default: Globe }, topojson, atlas, isoCodes] = await Promise.all([
          import('globe.gl'),
          import('topojson-client'),
          import('world-atlas/countries-110m.json'),
          import('i18n-iso-countries/codes.json')
        ]);
        if (destroyed || !host) return;

        // ISO numérico → alfa-2, que es como el gazetteer identifica un país.
        const alpha2 = new Map<string, string>(
          (isoCodes.default as string[][]).map((code) => [String(Number(code[2])), code[0]])
        );
        const topology = atlas.default as unknown as Topology;
        const collection = topojson.feature(
          topology,
          topology.objects.countries as GeometryCollection<AtlasProperties>
        );

        const polygons = collection.features.filter((feature) => feature.geometry);
        for (const feature of polygons) {
          const name = String(feature.properties?.name ?? 'territorio sin nombre');
          const numeric = feature.id === undefined ? '' : String(Number(feature.id));
          const shape: CountryShape = {
            iso2: alpha2.get(numeric) ?? null,
            name,
            ...frameOf(coordinatesOf(feature.geometry))
          };
          shapeOf.set(feature, shape);
          if (shape.iso2) framesByIso2.set(shape.iso2, shape);
        }

        const instance = new Globe(host, { animateIn: !reducedMotion })
          .backgroundColor('rgba(0,0,0,0)')
          .showGlobe(true)
          .showGraticules(true)
          .showAtmosphere(true)
          .atmosphereColor(SKIN.atmosphere)
          .atmosphereAltitude(0.16)
          .polygonsData(polygons)
          .polygonCapCurvatureResolution(3)
          .polygonsTransitionDuration(reducedMotion ? 0 : 240)
          .polygonLabel((polygon: object) => {
            const shape = shapeOf.get(polygon);
            if (!shape) return '';
            return shape.iso2 ? shape.name : `${shape.name} · sin ISO 3166-1`;
          })
          .onPolygonHover((polygon: object | null) => {
            hoveredIso2 = (polygon ? shapeOf.get(polygon)?.iso2 : null) ?? null;
          })
          .onPolygonClick((polygon: object) => pickCountry(shapeOf.get(polygon)))
          // Los puntos son nodos HTML sobre el globo, no texto en 3D: el
          // tipo de letra que three.js trae de serie no tiene acentos, y
          // «Ascensión» no se puede escribir «Ascensi?n».
          .htmlElementsData([])
          .htmlLat((place: object) => (place as GlobePlace).lat)
          .htmlLng((place: object) => (place as GlobePlace).lng)
          .htmlAltitude(RELIEF.place)
          .htmlElement((place: object) => marker(place as GlobePlace))
          .htmlElementVisibilityModifier((element: HTMLElement, visible: boolean) => {
            // Lo que cae en la cara oculta del globo no se puede pulsar.
            element.style.opacity = visible ? '1' : '0';
            element.style.pointerEvents = visible ? 'auto' : 'none';
          })
          .htmlTransitionDuration(reducedMotion ? 0 : 180)
          .ringAltitude(RELIEF.place)
          .ringColor(() => SKIN.chosen)
          .ringMaxRadius(2.6)
          .ringPropagationSpeed(1.1)
          .ringRepeatPeriod(1300);

        // El material de la esfera es un `Material` genérico para los tipos,
        // pero el que three-globe crea lleva color: es el mar del globo.
        (instance.globeMaterial() as unknown as { color?: { set(value: string): void } }).color?.set(
          SKIN.ocean
        );

        const controls = instance.controls();
        controls.autoRotateSpeed = 0.35;
        controls.enableDamping = true;
        // El radio del globo es 100: la distancia mínima tiene que dejar bajar
        // hasta la altitud de una provincia, o los controles pelearían con el
        // vuelo de la cámara y lo devolverían hacia arriba.
        controls.minDistance = 105;
        controls.maxDistance = 420;
        // La altitud de la cámara decide si los puntos llevan nombre: a vista
        // de mundo sobran doscientas etiquetas, de cerca hacen falta.
        controls.addEventListener('change', () => {
          const view = instance.pointOfView();
          if (Math.abs(view.altitude - altitude) > 0.02) altitude = view.altitude;
        });

        globe = instance;
        resize();
        observer = new ResizeObserver(resize);
        observer.observe(host);
        ready = true;
      } catch (error) {
        failure =
          error instanceof Error
            ? `No se pudo abrir el globo 3D: ${error.message}`
            : 'No se pudo abrir el globo 3D en este navegador.';
      }
    })();

    return () => {
      destroyed = true;
      observer?.disconnect();
      globe?._destructor();
      globe = null;
      ready = false;
    };
  });

  function resize() {
    if (!globe || !host) return;
    const box = host.getBoundingClientRect();
    if (box.width > 0 && box.height > 0) globe.width(box.width).height(box.height);
  }

  /** Qué puntos llevan nombre: los primeros que no se pisen entre sí. */
  function labelledIds(data: GlobePlace[], arc: number): Set<string> {
    const box = { lat: arc * LABEL_BOX.lat, lng: arc * LABEL_BOX.lng };
    const taken: GlobePlace[] = [];
    const ids = new Set<string>();
    for (const place of data) {
      if (taken.length >= MAX_LABELLED) break;
      const scale = Math.max(0.25, Math.cos((place.lat * Math.PI) / 180));
      const collides = taken.some(
        (other) =>
          Math.abs(other.lat - place.lat) < box.lat &&
          Math.abs((other.lng - place.lng) * scale) < box.lng
      );
      if (collides) continue;
      taken.push(place);
      ids.add(place.id);
    }
    return ids;
  }

  /** El nodo de un punto del globo: su círculo y, si cabe, su nombre. */
  function marker(place: GlobePlace): HTMLElement {
    const element = document.createElement('div');
    element.className = `globe-marker ${place.state}${named.has(place.id) ? ' is-named' : ''}`;
    element.title = place.name;
    const dot = document.createElement('span');
    dot.className = 'marker-dot';
    const name = document.createElement('span');
    name.className = 'marker-name';
    name.textContent = place.name;
    element.append(dot, name);
    element.addEventListener('click', (event) => {
      event.stopPropagation();
      if (!disabled && place.state === 'selectable') onplacepick(place.id);
    });
    return element;
  }

  function pickCountry(shape: CountryShape | undefined) {
    if (!shape || disabled || layer !== 'countries') return;
    if (!shape.iso2) {
      onunresolved?.(shape.name);
      return;
    }
    oncountrypick(shape.iso2, shape.name);
  }

  /**
   * Centro y altitud de cámara que encuadran una nube de coordenadas
   * `[longitud, latitud]`: los vértices de un país o los puntos de una capa.
   *
   * Las longitudes se miden respecto a la primera para que cruzar el
   * antimeridiano no convierta a Fiyi en un territorio de 360°.
   */
  function frameOf(points: Array<[number, number]>): {
    lat: number;
    lng: number;
    altitude: number;
  } {
    if (!points.length) return { lat: 0, lng: 0, altitude: WORLD_ALTITUDE };

    const origin = points[0][0];
    const unwrap = (lon: number) => ((lon - origin + 540) % 360) - 180;
    let minLon = Infinity;
    let maxLon = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;
    for (const [lon, lat] of points) {
      const relative = unwrap(lon);
      if (relative < minLon) minLon = relative;
      if (relative > maxLon) maxLon = relative;
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
    }
    // La longitud se acorta con el coseno de la latitud: a 60° un grado de
    // longitud ocupa la mitad que en el ecuador, y el encuadre lo nota.
    const latitudeScale = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
    const span =
      Math.max(maxLat - minLat, (maxLon - minLon) * Math.max(0.25, latitudeScale)) * FRAME_MARGIN;
    return {
      lat: (minLat + maxLat) / 2,
      lng: ((origin + (minLon + maxLon) / 2 + 540) % 360) - 180,
      altitude: Math.min(WORLD_ALTITUDE, Math.max(MIN_ALTITUDE, span / ARC_PER_ALTITUDE))
    };
  }

  /** Los vértices de una geometría del atlas, a cualquier profundidad. */
  function coordinatesOf(geometry: unknown): Array<[number, number]> {
    const points: Array<[number, number]> = [];
    const walk = (node: unknown) => {
      if (!Array.isArray(node)) return;
      if (typeof node[0] === 'number' && typeof node[1] === 'number') {
        points.push([node[0], node[1]]);
        return;
      }
      for (const child of node) walk(child);
    };
    if (geometry && typeof geometry === 'object' && 'coordinates' in geometry) {
      walk((geometry as { coordinates: unknown }).coordinates);
    }
    return points;
  }

  function flyToWorld() {
    altitude = WORLD_ALTITUDE;
    frameAltitude = WORLD_ALTITUDE;
    flownTo = 'world';
    globe?.pointOfView({ altitude: WORLD_ALTITUDE }, flightMs);
  }

  // --- Sincronización de los datos con el globo, que es imperativo --------- #

  // Polígonos: color y relieve según el país en foco y los ya elegidos.
  $effect(() => {
    if (!ready || !globe) return;
    const focus = focusIso2;
    const picked = chosenIso2;
    const hovered = hoveredIso2;
    const pickable = countriesPickable;
    globe
      .polygonCapColor((polygon: object) => {
        const iso2 = shapeOf.get(polygon)?.iso2 ?? null;
        if (iso2 && picked.includes(iso2)) return SKIN.chosen;
        if (iso2 && iso2 === focus) return SKIN.focus;
        if (pickable && iso2 && iso2 === hovered) return SKIN.landHover;
        return SKIN.land;
      })
      .polygonSideColor(() => SKIN.landEdge)
      .polygonStrokeColor(() => SKIN.landEdge)
      .polygonAltitude((polygon: object) => {
        const iso2 = shapeOf.get(polygon)?.iso2 ?? null;
        if (iso2 && (picked.includes(iso2) || iso2 === focus)) return RELIEF.focus;
        return pickable && iso2 && iso2 === hovered ? RELIEF.hover : RELIEF.land;
      });
  });

  // Puntos: provincias o localidades, con un anillo en las ya elegidas.
  $effect(() => {
    if (!ready || !globe) return;
    const data = places;
    // Los nombres se deciden contra el encuadre, no contra el zoom del
    // usuario: así girar o acercarse no reescribe el mapa a cada fotograma.
    named = showLabels
      ? labelledIds(data, frameAltitude * ARC_PER_ALTITUDE)
      : new Set(data.filter((place) => place.state === 'chosen').map((place) => place.id));
    globe
      .htmlElementsData(data)
      .ringsData(reducedMotion ? [] : data.filter((place) => place.state === 'chosen'))
      .ringLat((place: object) => (place as GlobePlace).lat)
      .ringLng((place: object) => (place as GlobePlace).lng);
  });

  // Cámara: el nivel del recorrido manda sobre el encuadre.
  $effect(() => {
    if (!ready || !globe) return;
    const place = focusPlace;
    const iso2 = focusIso2;
    const points = places;
    const lastPicked = chosenIso2.length ? chosenIso2[chosenIso2.length - 1] : null;
    // Un destino se vuela una vez. La capa llega después del clic, así que el
    // mismo destino se encuadra dos veces: primero el punto, luego sus puntos.
    const destination = place
      ? `place:${place.lat},${place.lng}:${points.length ? 'layer' : 'alone'}`
      : iso2
        ? `country:${iso2}`
        : lastPicked
          ? `picked:${lastPicked}`
          : 'world';
    if (destination === flownTo) return;
    flownTo = destination;

    if (place) {
      // Encuadrar la nube de puntos centra la provincia de verdad: su ciudad
      // más poblada puede estar en una esquina, como Ciudad Juárez en
      // Chihuahua.
      const view =
        points.length > 1
          ? frameOf(points.map((point) => [point.lng, point.lat]))
          : { lat: place.lat, lng: place.lng, altitude: PLACE_ALTITUDE };
      altitude = view.altitude;
      frameAltitude = view.altitude;
      globe.pointOfView(view, flightMs);
      return;
    }
    const shape = iso2 ? framesByIso2.get(iso2) : null;
    if (shape) {
      altitude = shape.altitude;
      frameAltitude = shape.altitude;
      globe.pointOfView({ lat: shape.lat, lng: shape.lng, altitude: shape.altitude }, flightMs);
      return;
    }
    const picked = lastPicked ? framesByIso2.get(lastPicked) : null;
    if (picked) {
      // Gira hacia lo último marcado, pero sin acercarse: en una liga
      // internacional todavía quedan países por elegir.
      const height = Math.max(altitude, 1.4);
      altitude = height;
      frameAltitude = height;
      globe.pointOfView({ lat: picked.lat, lng: picked.lng, altitude: height }, flightMs);
      return;
    }
    flyToWorld();
  });

  // Rotación automática: solo mientras se mira el mundo entero.
  $effect(() => {
    if (!ready || !globe) return;
    globe.controls().autoRotate =
      spinning && !focusIso2 && !focusPlace && !chosenIso2.length && !reducedMotion;
  });

  $effect(() => {
    if (!ready || !globe) return;
    globe.enablePointerInteraction(!disabled);
  });
</script>

<div class="world-globe" class:pickable={countriesPickable}>
  <div
    bind:this={host}
    class="globe-host"
    role="application"
    aria-label="Globo terráqueo del selector territorial. Arrastra para girar, acerca con la rueda y pulsa un territorio para elegirlo. La lista que acompaña al globo ofrece la misma selección con el teclado."
  ></div>

  {#if failure}
    <div class="globe-fallback">
      <p><strong>{failure}</strong></p>
      <p>
        El globo es una ayuda visual: el territorio se puede seguir eligiendo
        con el buscador y la lista de resultados.
      </p>
    </div>
  {:else if !ready}
    <p class="globe-loading">Cargando el atlas mundial…</p>
  {/if}

  <span class="globe-layer">
    {layer === 'countries' ? 'PAÍSES' : layer === 'regions' ? 'PROVINCIAS' : 'LOCALIDADES'}
  </span>

  <div class="globe-tools">
    <button
      type="button"
      onclick={flyToWorld}
      disabled={!ready}
      aria-label="Alejar la cámara hasta ver el mundo entero"
      title="Alejar la cámara hasta ver el mundo entero"
    >
      ⊕ Mundo
    </button>
    <button
      class:active={spinning}
      type="button"
      onclick={() => (spinning = !spinning)}
      disabled={!ready || reducedMotion}
      aria-label={spinning ? 'Detener la rotación automática' : 'Girar el globo solo'}
      title={spinning ? 'Detener la rotación automática' : 'Girar el globo solo'}
    >
      {spinning ? 'Ⅱ' : '▶'}
    </button>
  </div>
</div>

<style>
  .world-globe { position: relative; width: 100%; height: 100%; min-height: 340px; }
  /* Absoluto a propósito: si el lienzo contara para la altura del contenedor,
     cada medida del ResizeObserver lo agrandaría un poco más. */
  .globe-host { position: absolute; inset: 0; overflow: hidden; touch-action: none; cursor: grab; }
  .world-globe.pickable .globe-host { cursor: pointer; }
  .globe-host:active { cursor: grabbing; }
  .globe-loading { position: absolute; inset: auto 12px 46px; margin: 0; text-align: center; color: var(--muted); font-size: 11px; pointer-events: none; }
  .globe-fallback { position: absolute; inset: 50% 14px auto; padding: 14px; border: 1px solid var(--line); border-radius: 10px; background: #0d1820f2; color: #dfece6; font-size: 11px; line-height: 1.5; transform: translateY(-50%); }
  .globe-fallback p { margin: 0 0 6px; }
  .globe-fallback p:last-child { margin: 0; color: var(--muted); }
  /* Los marcadores los crea el globo con JavaScript y los cuelga de su propio
     contenedor, así que su estilo tiene que ser global: queda acotado por el
     ancestro, que es este componente. */
  .world-globe :global(.globe-marker) { display: flex; align-items: center; gap: 5px; color: #f3e7b4; font-size: 11px; line-height: 1; white-space: nowrap; transform: translate(-4px, -4px); transition: opacity .18s ease; }
  .world-globe :global(.globe-marker .marker-dot) { width: 8px; height: 8px; flex: none; border: 1.5px solid #fff6cf; border-radius: 50%; background: #d9c25e; box-shadow: 0 0 7px #0009; }
  .world-globe :global(.globe-marker .marker-name) { display: none; padding: 1px 5px; border-radius: 4px; background: #08161ccc; text-shadow: 0 1px 3px #000; }
  .world-globe :global(.globe-marker.is-named .marker-name) { display: inline; }
  .world-globe :global(.globe-marker.selectable) { cursor: pointer; }
  .world-globe :global(.globe-marker.selectable:hover) { color: #fffbe8; z-index: 2; }
  .world-globe :global(.globe-marker.selectable:hover .marker-dot) { background: #fff3a6; transform: scale(1.3); }
  .world-globe :global(.globe-marker.selectable:hover .marker-name) { display: inline; background: #0b2730ee; }
  .world-globe :global(.globe-marker.chosen) { color: #c6f4de; }
  .world-globe :global(.globe-marker.chosen .marker-dot) { width: 11px; height: 11px; border-color: #e3fff4; background: #63bf93; }
  .world-globe :global(.globe-marker.chosen .marker-name) { display: inline; font-weight: 700; }
  .globe-layer { position: absolute; inset: 12px auto auto 12px; color: #c9f4ee; font: 700 10px var(--mono); letter-spacing: .16em; text-shadow: 0 1px 5px #061116; pointer-events: none; }
  .globe-tools { position: absolute; inset: auto 12px 12px auto; display: flex; gap: 6px; }
  .globe-tools button { padding: 5px 9px; color: #bcebe7; border: 1px solid #3b7777; background: #0b222bdd; font-size: 11px; }
  .globe-tools button:hover:not(:disabled), .globe-tools button.active { color: #effffb; border-color: var(--accent); background: #17434a; }
  .globe-tools button:disabled { opacity: .45; }
</style>
