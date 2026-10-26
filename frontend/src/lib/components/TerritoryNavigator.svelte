<!--
  Navegador territorial del creador de competiciones.

  El recorrido lo manda el alcance de la competición, y el globo es la forma de
  recorrerlo: se gira el mundo, se pulsa un país, y el nivel siguiente aparece
  como puntos sobre ese país. Lo que nunca pasa es mezclar niveles —una liga
  municipal no puede acabar fijada a un estado— ni fijar texto libre: cada clic
  se resuelve contra el gazetteer y lo que se guarda es su identificador.

  El globo es una ayuda visual, no el único camino: el buscador y la lista que
  lo acompaña hacen la misma selección con el teclado, y siguen ahí si WebGL
  no arranca.
-->
<script lang="ts">
  import { api, RequestFailed } from '$lib/api/client';
  import type { GeoEntity, GeoLocalityLayer, GeoRegionLayer, GeoSearchResult } from '$lib/api/types';
  import { formatNumber, GEO_KIND_LABEL } from '$lib/format';
  import WorldGlobe, { type GlobePlace } from './WorldGlobe.svelte';

  export type TerritoryScope = 'municipal' | 'regional' | 'national' | 'multinational';

  type NavigatorStep = 'country' | 'region' | 'municipality';

  interface Props {
    scopeLevel: TerritoryScope;
    chosen: GeoEntity[];
    disabled?: boolean;
    onchoose: (entity: GeoEntity) => void | Promise<void>;
    onrestart: () => void;
    onscopechange: (level: TerritoryScope) => void;
  }

  let { scopeLevel, chosen, disabled = false, onchoose, onrestart, onscopechange }: Props = $props();

  /** País de paso: en una liga municipal o regional no es el territorio. */
  let country = $state<GeoEntity | null>(null);
  let region = $state<GeoEntity | null>(null);
  let query = $state('');
  let results = $state<GeoEntity[]>([]);
  let note = $state('');
  let searching = $state(false);
  let resolving = $state(false);
  /** Puntos del nivel en curso: provincias de un país o localidades de una provincia. */
  let layer = $state<GeoEntity[]>([]);
  let layerNote = $state('');
  let loadingLayer = $state(false);
  let previousScope = $state<TerritoryScope | null>(null);

  const isMunicipal = $derived(scopeLevel === 'municipal');
  const isInternational = $derived(scopeLevel === 'multinational');
  /** Alcances donde se van sumando territorios en vez de sustituirse: países
   *  en una liga internacional, estados o provincias en una regional. */
  const takesMany = $derived(scopeLevel === 'multinational' || scopeLevel === 'regional');
  /** Municipal y regional entran por el país, pero no lo fijan. */
  const needsRegion = $derived(scopeLevel === 'municipal' || scopeLevel === 'regional');

  const activeStep = $derived<NavigatorStep>(
    !needsRegion || !country ? 'country' : !isMunicipal || !region ? 'region' : 'municipality'
  );
  const globeLayer = $derived(
    activeStep === 'country' ? 'countries' : activeStep === 'region' ? 'regions' : 'localities'
  );

  /** Los países se eligen pulsando su polígono; los demás niveles, por punto. */
  const places = $derived.by<GlobePlace[]>(() => {
    if (activeStep === 'country') return [];
    const unique = new Map<string, GeoEntity>();
    for (const entity of layer) unique.set(entity.id, entity);
    for (const entity of results) unique.set(entity.id, entity);
    return [...unique.values()].map((entity) => ({
      id: entity.id,
      name: entity.name,
      lat: entity.map_lat ?? entity.lat,
      lng: entity.map_lon ?? entity.lon,
      state: chosen.some((item) => item.id === entity.id) ? 'chosen' : 'selectable'
    }));
  });

  const chosenIso2 = $derived(
    chosen.filter((entity) => entity.kind === 'country').map((entity) => entity.country_iso2)
  );
  const focusIso2 = $derived(
    needsRegion
      ? // Si se vuelve a entrar al paso con un territorio ya fijado, el globo
        // enseña su país aunque el recorrido empiece otra vez de cero.
        (country?.country_iso2 ?? chosen[0]?.country_iso2 ?? null)
      : scopeLevel === 'national'
        ? (chosen[0]?.country_iso2 ?? null)
        : // Internacional: la cámara se queda en el mundo para seguir eligiendo.
          null
  );
  const focusPlace = $derived(
    region ? { lat: region.map_lat ?? region.lat, lng: region.map_lon ?? region.lon } : null
  );

  /** La lista de al lado: lo buscado si hay búsqueda, el nivel en curso si no. */
  const deck = $derived(results.length ? results : activeStep === 'country' ? [] : layer);
  const showingSearch = $derived(results.length > 0);

  const target = $derived(
    activeStep === 'country'
      ? isInternational
        ? 'los países participantes'
        : needsRegion
          ? 'el país donde está el territorio'
          : 'el país'
      : activeStep === 'region'
        ? isMunicipal
          ? 'el estado o provincia'
          : 'los estados o provincias'
        : 'el municipio o localidad'
  );
  const helper = $derived(
    activeStep === 'country'
      ? isInternational
        ? 'Pulsa dos o más países en el globo para dibujar una liga internacional de clubes.'
        : needsRegion
          ? 'Gira el globo y pulsa un país: sus divisiones aparecerán como puntos. El país no queda fijado como territorio.'
          : 'Gira el globo y pulsa el país que organiza la competición.'
      : activeStep === 'region'
        ? isMunicipal
          ? `Pulsa una provincia de ${country?.name ?? 'ese país'} para ver sus localidades.`
          : `Pulsa uno o varios estados de ${country?.name ?? 'ese país'}: una liga regional puede abarcar más de uno. Aquí no aparecen localidades.`
        : `Pulsa la localidad dentro de ${region?.name ?? 'la provincia'}; no se mezclan localidades de otras provincias.`
  );

  function message(error: unknown): string {
    if (error instanceof RequestFailed) return error.message;
    return error instanceof Error ? error.message : 'no se pudo consultar el gazetteer';
  }

  function clearSearch() {
    query = '';
    results = [];
    note = '';
  }

  function changeScope(level: TerritoryScope) {
    country = null;
    region = null;
    layer = [];
    layerNote = '';
    clearSearch();
    onscopechange(level);
  }

  // Un cambio de alcance desde fuera —el tipo de competición del paso 1— tiene
  // que vaciar el recorrido: sus niveles ya no son los mismos.
  $effect(() => {
    if (previousScope === null) {
      previousScope = scopeLevel;
      return;
    }
    if (scopeLevel === previousScope) return;
    previousScope = scopeLevel;
    country = null;
    region = null;
    layer = [];
    layerNote = '';
    clearSearch();
  });

  async function loadRegions(iso2: string) {
    loadingLayer = true;
    layer = [];
    layerNote = '';
    try {
      const response = await api.get<GeoRegionLayer>(`/geography/countries/${iso2}/regions`);
      layer = response.items;
      layerNote = response.items.length
        ? `${response.items.length} divisiones de primer nivel en el gazetteer.`
        : 'El gazetteer importado no trae divisiones de primer nivel de este país.';
    } catch (error) {
      layerNote = message(error);
    } finally {
      loadingLayer = false;
    }
  }

  async function loadLocalities(entity: GeoEntity) {
    loadingLayer = true;
    layer = [];
    layerNote = '';
    try {
      const response = await api.get<GeoLocalityLayer>(
        `/geography/regions/${entity.id}/localities`
      );
      layer = response.items;
      layerNote = response.note;
    } catch (error) {
      layerNote = message(error);
    } finally {
      loadingLayer = false;
    }
  }

  /** Entrar en un país: pasa a ser el contexto, no el territorio elegido. */
  async function enterCountry(entity: GeoEntity) {
    country = entity;
    region = null;
    clearSearch();
    await loadRegions(entity.country_iso2);
  }

  /** Un clic en el globo llega como ISO: la identidad estable del polígono. */
  async function pickCountryByIso(iso2: string, name: string) {
    if (disabled || resolving) return;
    note = '';
    resolving = true;
    try {
      const entity = await api.get<GeoEntity>(`/geography/countries/${iso2}`);
      await select(entity);
    } catch (error) {
      note = `${name} (${iso2}): ${message(error)}`;
    } finally {
      resolving = false;
    }
  }

  function pickPlace(id: string) {
    const entity = [...layer, ...results].find((candidate) => candidate.id === id);
    if (entity) void select(entity);
  }

  function reportUnresolved(name: string) {
    note = `${name} no tiene código ISO 3166-1 en el atlas, así que no se puede resolver como territorio del gazetteer.`;
  }

  async function select(entity: GeoEntity) {
    if (disabled) return;
    if (activeStep === 'country' && needsRegion) {
      await enterCountry(entity);
      return;
    }
    if (activeStep === 'region' && isMunicipal) {
      region = entity;
      clearSearch();
      await loadLocalities(entity);
      return;
    }
    await onchoose(entity);
    // Donde se suman territorios la lista se queda abierta, para elegir el
    // siguiente sin repetir la búsqueda.
    if (!takesMany) clearSearch();
  }

  /** Volver a un nivel anterior del recorrido deshace lo que colgaba de él. */
  async function restartAt(step: NavigatorStep) {
    if (disabled) return;
    clearSearch();
    onrestart();
    if (step === 'country') {
      country = null;
      region = null;
      layer = [];
      layerNote = '';
      return;
    }
    region = null;
    if (country) await loadRegions(country.country_iso2);
  }

  async function search(event?: SubmitEvent) {
    event?.preventDefault();
    note = '';
    if (query.trim().length < 2) {
      note = 'Escribe al menos dos caracteres para buscar un territorio.';
      return;
    }
    searching = true;
    try {
      const params = new URLSearchParams({ q: query.trim(), limit: isInternational ? '16' : '10' });
      if (activeStep === 'country') {
        params.set('kind', 'country');
      } else if (activeStep === 'region') {
        params.set('kind', 'region');
        params.set('admin_level', '1');
        if (country) params.set('country', country.country_iso2);
      } else {
        params.set('kind', 'city');
        params.set('country', country?.country_iso2 ?? '');
        if (region) params.set('region_id', region.id);
      }
      const response = await api.get<GeoSearchResult>(`/geography/search?${params}`);
      results = response.items;
      note = response.note;
    } catch (error) {
      results = [];
      note = message(error);
    } finally {
      searching = false;
    }
  }

  function locationLabel(entity: GeoEntity) {
    return entity.admin_path ?? entity.country_name;
  }
</script>

<section class="territory-navigator" aria-label="Navegador geográfico">
  <div class="navigator-heading">
    <div>
      <p class="eyebrow">Atlas de competición</p>
      <h2>Delimita dónde se juega</h2>
      <p class="muted small">
        El tipo de liga determina qué puede seleccionarse; nunca se mezclan
        localidades con provincias o países.
      </p>
    </div>
    <div class="scope-rail" aria-label="Alcance territorial">
      <button class:active={scopeLevel === 'municipal'} type="button" onclick={() => changeScope('municipal')} disabled={disabled}>
        <span>⌖</span> Municipal
      </button>
      <button class:active={scopeLevel === 'regional'} type="button" onclick={() => changeScope('regional')} disabled={disabled}>
        <span>◈</span> Regional
      </button>
      <button class:active={scopeLevel === 'national'} type="button" onclick={() => changeScope('national')} disabled={disabled}>
        <span>◉</span> Nacional
      </button>
      <button class:active={scopeLevel === 'multinational'} type="button" onclick={() => changeScope('multinational')} disabled={disabled}>
        <span>◎</span> Internacional
      </button>
    </div>
  </div>

  <div class="atlas-stage">
    <div class="globe-stage">
      <WorldGlobe
        layer={globeLayer}
        {places}
        {focusIso2}
        {chosenIso2}
        {focusPlace}
        disabled={disabled || resolving}
        oncountrypick={pickCountryByIso}
        onplacepick={pickPlace}
        onunresolved={reportUnresolved}
      />
      {#if resolving}<p class="globe-busy">Resolviendo el territorio…</p>{/if}
    </div>

    <div class="journey-panel">
      <div class="journey" aria-label="Recorrido territorial">
        {#if needsRegion}
          <button
            class:done={country}
            class:active={activeStep === 'country'}
            type="button"
            onclick={() => void restartAt('country')}
            disabled={disabled || !country}
          >
            <b>1</b><span>País</span>
            {#if country}<small>{country.name}</small>
            {:else if chosen[0]}<small>{chosen[0].country_name}</small>
            {:else}<small>de paso</small>{/if}
          </button>
          <i aria-hidden="true">→</i>
          <button
            class:done={region}
            class:active={activeStep === 'region'}
            type="button"
            disabled={disabled || !country || !isMunicipal || !region}
            onclick={() => void restartAt('region')}
          >
            <b>2</b><span>{isMunicipal ? 'Provincia' : 'Estado o provincia'}</span>
            {#if region}<small>{region.name}</small>
            {:else if !isMunicipal && chosen.length}<small>{chosen.length} elegido(s)</small>
            {:else}<small>{isMunicipal ? 'de paso' : 'uno o varios'}</small>{/if}
          </button>
          {#if isMunicipal}
            <i aria-hidden="true">→</i>
            <div class:active={activeStep === 'municipality'} class="journey-step">
              <b>3</b><span>Municipio</span><small>el territorio</small>
            </div>
          {/if}
        {:else if isInternational}
          <div class="journey-step active"><b>1</b><span>Países</span><small>elige al menos dos</small></div>
          <i aria-hidden="true">→</i>
          <div class="journey-step"><b>2</b><span>Liga internacional</span><small>clubes de esos territorios</small></div>
        {:else}
          <div class="journey-step active"><b>1</b><span>País</span><small>el territorio</small></div>
        {/if}
      </div>

      <div class="target-copy">
        <p class="eyebrow">Ahora selecciona</p>
        <h3>{target}</h3>
        <p>{helper}</p>
      </div>

      <form class="atlas-search" onsubmit={search}>
        <label for="atlas-query">Buscar {target}</label>
        <div>
          <input
            id="atlas-query"
            bind:value={query}
            placeholder={activeStep === 'country' ? 'México, Japón, Canadá…' : activeStep === 'region' ? 'Chihuahua, Sonora, Jalisco…' : 'Ciudad Juárez, Hermosillo…'}
            autocomplete="off"
            disabled={disabled}
          />
          <button type="submit" disabled={disabled || searching}>{searching ? 'Buscando…' : 'Buscar'}</button>
        </div>
      </form>

      {#if note}<p class="search-note">{note}</p>{/if}

      <div class="deck-head">
        {#if showingSearch}
          <span>Resultados de la búsqueda</span>
          <button class="ghost-link" type="button" onclick={clearSearch}>
            {activeStep === 'country'
              ? 'limpiar la búsqueda'
              : activeStep === 'region'
                ? 'volver al listado de provincias'
                : 'volver al listado de localidades'}
          </button>
        {:else if activeStep === 'region'}
          <span>Provincias de {country?.name ?? ''}</span>
        {:else if activeStep === 'municipality'}
          <span>Localidades de {region?.name ?? ''}</span>
        {:else}
          <span>Pulsa un país en el globo o búscalo por su nombre</span>
        {/if}
      </div>
      {#if !showingSearch && layerNote}<p class="search-note">{layerNote}</p>{/if}

      {#if loadingLayer}
        <p class="search-note">Cargando el nivel…</p>
      {:else if deck.length}
        <div class="place-deck" aria-live="polite">
          {#each deck as entity (entity.id)}
            <button
              type="button"
              class:selected={chosen.some((item) => item.id === entity.id)}
              onclick={() => void select(entity)}
              disabled={disabled || chosen.some((item) => item.id === entity.id)}
            >
              <span class="place-pin" aria-hidden="true">✦</span>
              <span class="place-main"><strong>{entity.name}</strong><small>{locationLabel(entity)}</small></span>
              <span class="place-meta">
                {GEO_KIND_LABEL[entity.kind] ?? entity.kind}{#if entity.population} · {formatNumber(entity.population)} hab.{/if}
              </span>
            </button>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  {#if takesMany && chosen.length}
    <div class="country-picks">
      <span>{isInternational ? 'Países trazados' : 'Territorio de la liga'}: {chosen.length}</span>
      {#each chosen as entity (entity.id)}<b>{entity.name}</b>{/each}
    </div>
  {/if}
</section>

<style>
  .territory-navigator { overflow: hidden; border: 1px solid var(--line); border-radius: 16px; background: linear-gradient(135deg, #0d1820, #112c36 52%, #111821); }
  .navigator-heading { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; padding: 20px; border-bottom: 1px solid color-mix(in srgb, var(--line) 80%, transparent); }
  .navigator-heading h2, .navigator-heading p { margin: 0; } .navigator-heading h2 { margin-bottom: 5px; }
  .eyebrow { margin: 0 0 7px !important; color: var(--accent); font: 700 10px/1 var(--mono); letter-spacing: .12em; }
  .scope-rail { display: flex; flex-wrap: wrap; gap: 5px; padding: 4px; border: 1px solid var(--line); border-radius: 11px; background: #0a141b; }
  .scope-rail button { display: grid; gap: 2px; min-width: 72px; padding: 7px 9px; color: var(--muted); border: 1px solid transparent; background: transparent; font-size: 11px; }
  .scope-rail button span { color: #8fbcc3; font-size: 15px; }
  .scope-rail button:hover, .scope-rail button.active { color: #e6fff4; border-color: #3f827d; background: #164044; }
  .scope-rail button.active span { color: var(--accent); }
  .atlas-stage { display: grid; grid-template-columns: minmax(300px, 1fr) minmax(340px, 1fr); min-height: 420px; }
  .globe-stage { position: relative; align-self: start; height: clamp(380px, 54vh, 560px); border-right: 1px solid var(--line); background: radial-gradient(circle at 50% 42%, #16404a, #0b141a 72%); }
  .globe-busy { position: absolute; inset: auto 0 14px; margin: 0; text-align: center; color: #cdeee7; font-size: 11px; pointer-events: none; }
  .journey-panel { padding: 23px; }
  .journey { display: flex; align-items: center; gap: 7px; }
  .journey > i { color: #4d918b; font-style: normal; }
  .journey-step, .journey button { display: grid; grid-template-columns: auto 1fr; column-gap: 6px; align-items: center; min-width: 0; flex: 1; padding: 9px; text-align: left; color: var(--muted); border: 1px solid var(--line); border-radius: 9px; background: #101f27; }
  .journey button:not(:disabled) { cursor: pointer; }
  .journey b { display: grid; grid-row: span 2; place-items: center; width: 21px; height: 21px; color: #0a151a; border-radius: 50%; background: #517071; font-size: 11px; }
  .journey span { color: inherit; font-size: 12px; font-weight: 700; }
  .journey small { overflow: hidden; color: inherit; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
  .journey .active { color: #dcfff5; border-color: var(--accent); box-shadow: 0 0 0 2px #43caa322; }
  .journey .active b, .journey .done b { background: var(--accent); }
  .journey .done { color: #bce3d8; border-color: #437c70; }
  .target-copy { margin-top: 21px; }
  /* El texto del nivel se escribe en minúscula porque también se usa dentro de
     una frase; aquí encabeza, así que solo sube la primera letra. */
  .target-copy h3 { margin: 0; color: var(--text); font-size: 16px; letter-spacing: 0; text-transform: none; }
  .target-copy h3::first-letter { text-transform: uppercase; }
  .target-copy p:last-child { margin: 5px 0 0; color: var(--muted); font-size: 12px; line-height: 1.45; }
  .atlas-search { margin-top: 16px; }
  .atlas-search label { display: block; margin-bottom: 5px; color: #a8c6c8; font-size: 11px; }
  .atlas-search > div { display: flex; gap: 7px; }
  .atlas-search input { flex: 1; min-width: 0; background: #0b151b; }
  .atlas-search button { padding-inline: 14px; }
  .search-note { margin: 8px 0 0; color: var(--muted); font-size: 11px; line-height: 1.45; }
  .deck-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px; align-items: baseline; margin-top: 14px; color: #a8c6c8; font-size: 11px; }
  .ghost-link { padding: 0; color: var(--accent); background: none; border: 0; font-size: 11px; text-decoration: underline; cursor: pointer; }
  .place-deck { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; max-height: 268px; margin-top: 8px; overflow-y: auto; padding-right: 4px; }
  .place-deck button { display: grid; grid-template-columns: auto 1fr; gap: 3px 7px; min-width: 0; padding: 10px; text-align: left; color: var(--text); background: #13262f; border: 1px solid #31515a; transition: transform .16s ease, border-color .16s ease, background .16s ease; }
  .place-deck button:hover:not(:disabled) { border-color: var(--accent); background: #174048; transform: translateY(-2px); }
  .place-deck button.selected { opacity: .55; }
  .place-pin { grid-row: span 2; color: #f1d46e; }
  .place-main { min-width: 0; }
  .place-main strong, .place-main small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .place-main small, .place-meta { color: var(--muted); font-size: 10px; }
  .place-meta { grid-column: 2; }
  .country-picks { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 12px 20px; color: var(--muted); border-top: 1px solid var(--line); font-size: 12px; }
  .country-picks b { padding: 4px 7px; color: #c9f4ee; border-radius: 999px; background: #1d4b4b; font-size: 11px; }
  @media (prefers-reduced-motion: reduce) { .place-deck button { transition: none; } }
  @media (max-width: 900px) {
    .navigator-heading { display: grid; }
    .atlas-stage { grid-template-columns: 1fr; }
    .globe-stage { height: 340px; border-right: 0; border-bottom: 1px solid var(--line); }
    .place-deck { grid-template-columns: 1fr; }
    /* Los tres pasos en fila no caben: se parten en vez de desbordar. */
    .journey { flex-wrap: wrap; }
    .journey-step, .journey button { flex: 1 1 42%; }
  }
</style>
