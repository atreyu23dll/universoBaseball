<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import type {
    Draft,
    EditorDivision,
    EditorGate,
    GenerationPreview,
    SchedulePreview as SchedulePreviewData,
    GeoContext,
    GeoEntity,
    GeoSearchResult,
    GeoStatus,
    MobilityRules,
    PairingPolicy,
    Place,
    Preview
  } from '$lib/api/types';
  import {
    CONFIDENCE_LABEL,
    DRAFT_STATE_LABEL,
    GEO_CONFIDENCE_LABEL,
    GROUP_ASSIGNMENT_LABEL,
    ISSUE_CODE_LABEL,
    GEO_KIND_LABEL,
    GOVERNANCE_LABEL,
    MODALITY_LABEL,
    VENUE_USAGE_LABEL,
    formatMoney,
    formatNumber,
    INSTITUTION_LABEL,
    VENUE_LABEL
  } from '$lib/format';
  import ConfidenceTag from '$lib/components/ConfidenceTag.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';
  import SchedulePreview from '$lib/components/SchedulePreview.svelte';
  import StructureEditor from '$lib/components/StructureEditor.svelte';

  /** De la lista de competiciones aquí solo hacen falta el id y el nombre. */
  type CompetitionOption = { id: string; name: string };

  const universeId = $derived($page.params.id);

  const STEPS = [
    'Identidad',
    'Territorio',
    'Modalidad',
    'Categoría',
    'Participantes',
    'Formato de liga',
    'Relaciones',
    'Previsualización'
  ];

  let step = $state(1);
  let places = $state<Place[]>([]);
  let competitions = $state<CompetitionOption[]>([]);
  let error = $state<unknown>(null);
  let working = $state(false);
  let linkWarning = $state('');
  let createdEditionId = $state('');

  // El asistente trabaja sobre un borrador guardado y una propuesta inmutable.
  // Confirmar exige la huella de la intención: así no se puede crear un mundo
  // distinto del que se vio en pantalla.
  let draft = $state<Draft | null>(null);
  let preview = $state<Preview | null>(null);
  let savingDraft = $state(false);
  const blocking = $derived(preview?.issues.filter((i) => i.severity === 'blocking') ?? []);
  const warnings = $derived(preview?.issues.filter((i) => i.severity === 'warning') ?? []);
  const previewIsCurrent = $derived(
    preview !== null && draft !== null && preview.intent_fingerprint === draft.intent_fingerprint
  );

  // --- Paso 1: identidad y clase de competición ---
  let name = $state('Liga Municipal de Ciudad Juárez');
  let kind = $state('municipal_league');
  let seed = $state('18723');

  // --- Paso 2: territorio y jurisdicción ---
  // El territorio se resuelve contra el gazetteer mundial: el usuario busca un
  // lugar y elige una entidad concreta. Lo que se guarda es su identificador,
  // no el texto que escribió.
  let scopeLevel = $state('municipal');
  let selectedPlaces = $state<string[]>([]);
  let geoStatus = $state<GeoStatus | null>(null);
  let geoQuery = $state('');
  let geoCountry = $state('');
  let geoResults = $state<GeoEntity[]>([]);
  let geoNote = $state('');
  let geoSearching = $state(false);
  let chosen = $state<GeoEntity[]>([]);
  let chosenContext = $state<Record<string, GeoContext>>({});
  let territoryMode = $state<'administrative_area' | 'radius'>('administrative_area');
  let radiusKm = $state(50);

  // --- Paso 3: modalidad de participación ---
  // ÚNICA pregunta de naturaleza institucional del asistente. No hay —ni puede
  // haber— controles de presupuesto, propiedad, personal o estadios: eso lo
  // decide cada institución según su entorno.
  let modality = $state('amateur_organized');

  // --- Paso 4: categoría y elegibilidad ---
  let minimumAge = $state(18);
  let hasMaximumAge = $state(false);
  let maximumAge = $state(40);
  let ageCutoff = $state('season_start');
  let cutoffMonthDay = $state('01-01');
  let keepsCategory = $state(true);
  let residencyRequired = $state(false);
  const involvesMinors = $derived(minimumAge < 18);

  // --- Paso 5: participantes y admisión ---
  let clubCount = $state(12);
  let talentPool = $state('shared_geographic');
  let minimumActiveRoster = $state(14);
  let foreignLimitEnabled = $state(false);
  let foreignLimit = $state(5);

  // --- Paso 6: formato de liga, calendario y reglamento ---
  //
  // Los grupos no son una pregunta sobre los clubes —el motor decide quién va a
  // cada división— sino sobre la competición: cuántas divisiones hay, con qué
  // criterio se reparten, cuántas veces se juega dentro y fuera, y cómo se
  // clasifica.
  // Estructura del campeonato, tal como la deja el editor: una tabla única de
  // partida, y a partir de ahí lo que el usuario arrastre. El número de
  // divisiones y los clasificados se derivan de este mismo tablero.
  let divisions = $state<EditorDivision[]>([
    { key: 'd1', label: 'Tabla general', slots: 12, intra_cycles: 2, inter_cycles: 0 }
  ]);
  // Una puerta por plaza: así cada una lleva su ronda de entrada y su orden
  // dentro de ella, que es el cruce que el tablero dibuja.
  let gates = $state<EditorGate[]>(
    [1, 2, 3, 4].map((position, index) => ({
      division: 'd1',
      positions: [position],
      route: 'seed' as const,
      target_round: 0,
      order: index
    }))
  );
  let groupAssignment = $state('geographic');
  let gamesPerSeries = $state(1);
  let daysBetweenSeries = $state(0);
  let offseasonDays = $state(14);
  let restDays = $state<number[]>([0]);

  // El reglamento deportivo forma parte del mismo lienzo: lo que se decide
  // aquí se refleja en la tabla, el calendario y el cuadro sin cambiar de paso.
  let rosterSize = $state(26);
  let designatedHitter = $state(true);
  let extraInnings = $state(true);
  let mercyEnabled = $state(false);
  let mercyRunDiff = $state(12);
  let standingsPrimary = $state('win_percentage');
  let tiebreakers = $state<string[]>(['head_to_head', 'run_differential']);
  let playoffFormat = $state('best_of_series');
  // Las rondas las pone el usuario: su número ya no se deduce de las plazas,
  // porque un cuadro puede incorporar clubes en cualquier ronda.
  let roundLengths = $state<number[]>([3, 5]);
  let roundLabels = $state<string[]>(['Semifinales', 'Final']);
  let roundPairings = $state<PairingPolicy[]>(['high_low', 'high_low']);
  let licenceRequired = $state(false);
  let safetyCertRequired = $state(false);
  let amateurStatusRequired = $state(false);
  let minimumVenueCapacityEnabled = $state(false);
  let minimumVenueCapacity = $state(1000);
  let compensationRule = $state('');
  let entryFeeEnabled = $state(false);
  let entryFee = $state(0);

  // --- Paso 7: relaciones competitivas ---
  let relationshipMode = $state('independent');
  let linkPosition = $state<'below' | 'above'>('below');
  let linkRelation = $state('promotion_relegation');
  let linkPartnerId = $state('');
  let linkSlots = $state(2);
  let linkLowerMethod = $state('top_standings');
  let linkMinCapacity = $state('');
  let linkMaxDebt = $state('');
  let linkFailurePolicy = $state('substitute');
  let linkFromSeason = $state('');
  let partnerRules = $state<MobilityRules | null>(null);

  const cityPlaces = $derived(places.filter((p) => p.kind === 'city'));
  const regionPlaces = $derived(places.filter((p) => p.kind === 'region'));
  const countryPlaces = $derived(places.filter((p) => p.kind === 'country'));
  const availablePlaces = $derived(
    scopeLevel === 'municipal'
      ? cityPlaces
      : scopeLevel === 'regional'
        ? regionPlaces
        : scopeLevel === 'national'
          ? countryPlaces
          : [...countryPlaces, ...cityPlaces]
  );
  /** Moneda de la jurisdicción elegida: sale del territorio, no de un ajuste. */
  const resolvedCurrency = $derived(
    chosen[0]?.currency ?? places.find((p) => p.key === selectedPlaces[0])?.currency ?? null
  );
  /** ¿Hay territorio suficiente para continuar? */
  const hasTerritory = $derived(chosen.length > 0 || selectedPlaces.length > 0);
  /** Avisos de lo que no se sabe del territorio elegido. */
  const territoryWarnings = $derived(
    chosen.flatMap((entity) => chosenContext[entity.id]?.warnings ?? [])
  );

  async function searchGeography(event?: SubmitEvent) {
    event?.preventDefault();
    geoNote = '';
    if (geoQuery.trim().length < 2) {
      geoNote = 'Escribe al menos dos caracteres.';
      return;
    }
    geoSearching = true;
    try {
      const params = new URLSearchParams({ q: geoQuery.trim(), limit: '10' });
      if (geoCountry.trim()) params.set('country', geoCountry.trim().toUpperCase());
      const result = await api.get<GeoSearchResult>(`/geography/search?${params}`);
      geoResults = result.items;
      geoNote = result.note;
    } catch (err) {
      geoResults = [];
      geoNote = err instanceof Error ? err.message : 'la búsqueda falló';
    } finally {
      geoSearching = false;
    }
  }

  async function chooseEntity(entity: GeoEntity) {
    if (chosen.some((e) => e.id === entity.id)) return;
    chosen = [...chosen, entity];
    // Al elegir se consulta qué se sabe del territorio y qué no: es lo que
    // permite decir «aquí no hay datos económicos» antes de generar nada.
    try {
      chosenContext = {
        ...chosenContext,
        [entity.id]: await api.get<GeoContext>(`/geography/entities/${entity.id}/context`)
      };
    } catch {
      /* el contexto es informativo: su ausencia no bloquea */
    }
  }

  function dropEntity(id: string) {
    chosen = chosen.filter((e) => e.id !== id);
  }
  /**
   * Cuántos clasifican: las plazas que el tablero colocó en alguna ronda.
   * No hay un selector de plazas de playoff, y por eso no puede contradecir a
   * la estructura: es el mismo número mirado una sola vez.
   */
  const gateQualifiers = $derived(
    gates.reduce((total, gate) => total + gate.positions.length, 0)
  );

  /**
   * No es una decisión adicional: el contrato todavía requiere una cifra de
   * referencia para la temporada, pero ahora sale del tablero. En una tabla
   * única coincide exactamente; si hay divisiones asimétricas es el promedio
   * de los clubes, mientras la vista enseña el rango real de cada división.
   */
  const gamesTarget = $derived.by(() => {
    const gamesByDivision = divisions.map((division) => {
      const internos = Math.max(0, division.slots - 1) * division.intra_cycles;
      const externos = divisions
        .filter((other) => other.key !== division.key)
        .reduce(
          (total, other) =>
            total + other.slots * Math.max(division.inter_cycles, other.inter_cycles),
          0
        );
      return (internos + externos) * gamesPerSeries;
    });
    const average = gamesByDivision.length
      ? Math.round(gamesByDivision.reduce((total, games) => total + games, 0) / gamesByDivision.length)
      : 2;
    return Math.max(2, Math.min(250, average));
  });

  /** Último cálculo del motor, para que el editor marque sus desajustes. */
  let previewResult = $state<SchedulePreviewData | null>(null);
  const structureIssues = $derived(previewResult?.issues ?? []);
  /** Lo que el motor dice del calendario cuando no se puede construir. */
  const scheduleError = $derived(
    previewResult && !previewResult.ok ? previewResult.error : null
  );

  /** Las fases tal como las entiende el reglamento. */
  function buildStages() {
    const regular = {
      // Las claves coinciden con las que usa la base para la fase de una
      // edición, así que no hay que traducir nada al generar.
      key: 'regular_season',
      label: 'Temporada regular',
      format: 'table',
      divisions: divisions.map((d) => ({
        key: d.key,
        label: d.label,
        slots: d.slots,
        intra_cycles: d.intra_cycles,
        inter_cycles: divisions.length > 1 ? d.inter_cycles : 0
      })),
      gates:
        playoffFormat === 'none'
          ? []
          : gates.map((g) => ({
              division: g.division,
              positions: g.positions,
              route: g.route,
              ...(g.target_round !== undefined ? { target_round: g.target_round } : {}),
              ...(g.order !== undefined ? { order: g.order } : {}),
              ...(g.label ? { label: g.label } : {})
            }))
    };
    if (playoffFormat === 'none' || gateQualifiers < 2) return [regular];
    return [
      regular,
      {
        key: 'playoffs',
        label: 'Postemporada',
        format: 'bracket',
        series_lengths: playoffRoundLengths
      }
    ];
  }

  /**
   * El bloque `playoffs` del reglamento, derivado del tablero.
   *
   * Las plazas no se declaran: son las que el tablero colocó. Las rondas
   * tampoco se deducen de las plazas, y por eso el reglamento va con
   * `seeding: 'staged'`: el cuadro es el dibujado, con sus nombres y su
   * política de cruces, y el motor no infiere pases directos por potencia de
   * dos.
   */
  function buildPlayoffs() {
    if (playoffFormat === 'none' || gateQualifiers < 2) {
      return { slots: 0, format: 'none', round_lengths: [] };
    }
    return {
      slots: gateQualifiers,
      format: playoffFormat,
      seeding: 'staged',
      round_lengths: playoffRoundLengths,
      round_labels: roundLabels.slice(0, roundCount),
      round_pairings: Array.from(
        { length: roundCount },
        (_, index) => roundPairings[index] || 'high_low'
      )
    };
  }

  /** Lo que se manda a la vista del calendario. Un solo sitio donde se arma. */
  const previewPayload = $derived({
    club_count: clubCount,
    season: {
      games_per_club_target: gamesTarget,
      games_per_series: gamesPerSeries,
      days_between_series: daysBetweenSeries,
      rest_days_weekday: restDays
    },
    structure: { stages: buildStages() },
    playoffs: buildPlayoffs()
  });

  // Si cambia el número de equipos, las plazas se ajustan en la división más
  // grande: el editor nunca se queda descuadrado por detrás.
  $effect(() => {
    const total = divisions.reduce((suma, d) => suma + d.slots, 0);
    if (total === clubCount || divisions.length === 0) return;
    const diferencia = clubCount - total;
    const indice = divisions.reduce(
      (mejor, d, i) => (d.slots > divisions[mejor].slots ? i : mejor),
      0
    );
    const ajustada = [...divisions];
    ajustada[indice] = {
      ...ajustada[indice],
      slots: Math.max(0, ajustada[indice].slots + diferencia)
    };
    divisions = ajustada;
  });
  /** Rondas del cuadro: las que el usuario puso en el tablero. */
  const roundCount = $derived(roundLengths.length);
  /** Una eliminatoria es siempre a un partido, también en el motor y la vista. */
  const playoffRoundLengths = $derived(
    playoffFormat === 'single_elimination'
      ? Array.from({ length: roundCount }, () => 1)
      : [...roundLengths]
  );
  // Los nombres y las políticas acompañan a las rondas una a una: el
  // reglamento rechaza una lista que no corresponda, y con razón.
  $effect(() => {
    if (roundLabels.length !== roundCount) {
      roundLabels = Array.from(
        { length: roundCount },
        (_, index) => roundLabels[index] || `Ronda ${index + 1}`
      );
    }
    if (roundPairings.length !== roundCount) {
      roundPairings = Array.from(
        { length: roundCount },
        (_, index) => roundPairings[index] || 'high_low'
      );
    }
  });
  const partner = $derived(competitions.find((c) => c.id === linkPartnerId) ?? null);
  const isHierarchy = $derived(
    relationshipMode === 'dependent' && linkRelation === 'promotion_relegation'
  );
  const upperName = $derived(linkPosition === 'below' ? (partner?.name ?? '—') : name);
  const lowerName = $derived(linkPosition === 'below' ? name : (partner?.name ?? '—'));
  const existingQuota = $derived(
    linkPosition === 'below' && partnerRules?.has_hierarchy ? partnerRules.exchange_slots : null
  );

  const MODALITY_HELP: Record<string, string> = {
    llanera:
      'Llanera o recreativa informal. Admite equipos de barrio, grupos comunitarios, asociaciones y también clubes con mejor financiación, mientras cumplan la admisión. No presupone pobreza ni ausencia de patrocinio.',
    amateur_organized:
      'Amateur organizada. Prioriza registros y prácticas de amateurismo. Un club solvente no se convierte en profesional por tener recursos.',
    school_formative:
      'Escolar o formativa. La adscripción a un centro puede ser requisito de elegibilidad y con menores se exigen salvaguardas. No obliga a que cada club sea una escuela con patrimonio propio.',
    semi_professional:
      'Semiprofesional. Conviven dedicaciones y compensaciones distintas según contrato y contexto. No obliga a estadio propio ni a un modelo único de organización.',
    professional:
      'Profesional. Puede exigir licencia y contratos, pero los recursos de sus clubes varían mucho: ni riqueza ilimitada ni el mismo modelo jurídico para todos.'
  };

  async function loadPartnerRules() {
    partnerRules = null;
    if (!linkPartnerId) return;
    try {
      partnerRules = await api.get<MobilityRules>(`/competitions/${linkPartnerId}/mobility`);
      if (partnerRules.has_hierarchy && partnerRules.exchange_slots && linkPosition === 'below') {
        linkSlots = partnerRules.exchange_slots;
      }
    } catch {
      partnerRules = null;
    }
  }

  /** Reglamento de la competición. Aquí no hay un solo campo sobre los clubes. */
  function buildRuleset() {
    return {
      name,
      kind,
      participation_modality: modality,
      // Siempre independiente en el reglamento: la dependencia la crea la
      // relación que se registra justo después de crearla.
      relationship_mode: 'independent',
      scope: {
        level: scopeLevel,
        ...(chosen.length
          ? {
              entity_ids: chosen.map((e) => e.id),
              mode: territoryMode,
              ...(territoryMode === 'radius' ? { radius_km: radiusKm } : {})
            }
          : { place_keys: selectedPlaces }),
        ...(chosen[0]?.country_iso2 ? { country_code: chosen[0].country_iso2 } : {})
      },
      eligibility: {
        minimum_age: minimumAge,
        maximum_age: hasMaximumAge ? maximumAge : null,
        age_cutoff: ageCutoff,
        ...(ageCutoff === 'fixed_date' ? { cutoff_month_day: cutoffMonthDay } : {}),
        keeps_category_through_season: keepsCategory,
        minor_safeguarding: involvesMinors,
        residency_required: residencyRequired
      },
      admission: {
        amateur_status_required: amateurStatusRequired,
        facility_safety_certification_required: safetyCertRequired,
        licence_required: licenceRequired,
        minimum_venue_capacity: minimumVenueCapacityEnabled ? minimumVenueCapacity : null,
        minimum_active_roster: minimumActiveRoster
      },
      financial_regulations: {
        ...(compensationRule ? { compensation_rule: compensationRule } : {}),
        ...(entryFeeEnabled ? { entry_fee: entryFee } : {})
      },
      season: {
        games_per_club_target: gamesTarget,
        games_per_series: gamesPerSeries,
        days_between_series: daysBetweenSeries,
        offseason_days: offseasonDays,
        roster_size: rosterSize,
        rest_days_weekday: restDays,
        designated_hitter: designatedHitter,
        extra_innings: extraInnings,
        ...(mercyEnabled ? { mercy_rule_run_diff: mercyRunDiff } : {})
      },
      structure: { stages: buildStages(), assignment: groupAssignment },
      standings: { primary: standingsPrimary, tiebreakers },
      // Las plazas las fijan las puertas del editor: dos números que pudieran
      // contradecirse no existen, y el reglamento rechaza el que no cuadre.
      playoffs: buildPlayoffs(),
      generation: {
        club_count: clubCount,
        talent_pool: talentPool,
        ...(foreignLimitEnabled ? { foreign_player_limit: foreignLimit } : {}),
        seed: seed.trim() === '' ? null : Number(seed)
      }
    };
  }

  function buildRelationship() {
    const body: Record<string, unknown> = { relation_kind: linkRelation };
    if (linkRelation !== 'promotion_relegation') return body;
    body.exchange_slots = linkSlots;
    body.lower_selection = { method: linkLowerMethod };
    const requirements: Record<string, number> = {};
    if (linkMinCapacity.trim() !== '') requirements.min_venue_capacity = Number(linkMinCapacity);
    if (linkMaxDebt.trim() !== '') requirements.max_debt_to_budget = Number(linkMaxDebt);
    if (Object.keys(requirements).length) {
      body.requirements = requirements;
      body.on_requirement_failure = linkFailurePolicy;
    }
    if (linkFromSeason.trim() !== '') body.effective_from_season = Number(linkFromSeason);
    return body;
  }

  /** Guarda la intención en el borrador. Sin crear nada en el mundo. */
  async function saveDraft(): Promise<Draft | null> {
    savingDraft = true;
    try {
      const intent = buildRuleset();
      draft = draft
        ? await api.patch<Draft>(`/competitions/drafts/${draft.id}`, { intent })
        : await api.post<Draft>(`/universes/${universeId}/competitions/drafts`, { intent });
      return draft;
    } catch (err) {
      error = err;
      return null;
    } finally {
      savingDraft = false;
    }
  }

  async function runPreview() {
    working = true;
    error = null;
    try {
      const guardado = await saveDraft();
      if (!guardado) return;
      preview = await api.post<Preview>(`/universes/${universeId}/competitions/previews`, {
        intent: buildRuleset(),
        draft_id: guardado.id
      });
      step = 8;
    } catch (err) {
      error = err;
      preview = null;
    } finally {
      working = false;
    }
  }

  function reroll() {
    seed = String(Math.floor(Math.random() * 1_000_000));
    void runPreview();
  }

  async function confirm() {
    if (!preview || !draft) return;
    working = true;
    error = null;
    linkWarning = '';
    try {
      // La huella es lo que demuestra que se crea lo previsualizado. Si el
      // borrador cambió, el servidor responde conflicto en vez de crear otra
      // cosa en silencio.
      const created = await api.post<{ competition_id: string; created: boolean }>(
        '/competitions/commit',
        { preview_id: preview.preview_id, intent_fingerprint: preview.intent_fingerprint },
        { 'Idempotency-Key': `${draft.id}:${preview.intent_fingerprint.slice(0, 16)}` }
      );
      const competitionId = created.competition_id;
      if (relationshipMode === 'dependent' && linkPartnerId) {
        const [upper, lower] =
          linkPosition === 'below'
            ? [linkPartnerId, competitionId]
            : [competitionId, linkPartnerId];
        try {
          await api.post(`/competitions/${upper}/relationships`, {
            target_competition_id: lower,
            ...buildRelationship()
          });
        } catch (err) {
          linkWarning = err instanceof Error ? err.message : 'no se pudo crear el vínculo';
        }
      }
      const edition = await api.post<{ edition_id: string }>(
        `/competitions/${competitionId}/generate`
      );
      if (linkWarning) {
        createdEditionId = edition.edition_id;
        return;
      }
      window.location.href = `/ediciones/${edition.edition_id}`;
    } catch (err) {
      error = err;
    } finally {
      working = false;
    }
  }

  function togglePlace(key: string) {
    selectedPlaces = selectedPlaces.includes(key)
      ? selectedPlaces.filter((k) => k !== key)
      : [...selectedPlaces, key];
  }

  onMount(async () => {
    try {
      const [geography, existing] = await Promise.all([
        api.get<{ items: Place[] }>(`/universes/${universeId}/geography`),
        api.get<{ items: CompetitionOption[] }>(`/universes/${universeId}/competitions`)
      ]);
      places = geography.items;
      competitions = existing.items;
      try {
        geoStatus = await api.get<GeoStatus>('/geography/status');
      } catch {
        geoStatus = null;
      }
    } catch (err) {
      error = err;
    }
  });

</script>

{#if step !== 6}
  <h1>Crear competición</h1>
  <p class="muted small">
    Esto es lo único que hace falta definir: <strong>las condiciones de la
    competición</strong>. Los clubes, su forma de organizarse, quién los financia,
    qué instalaciones usan y a quién pagan los genera y administra el motor según
    el entorno de cada uno. El asistente no te va a preguntar por ninguna de esas
    cosas.
  </p>
{/if}

<ErrorNotice {error} />

<div class="row steps">
  {#each STEPS as label, index}
    <button
      class={step === index + 1 ? 'tag accent' : 'tag'}
      onclick={() => (step = index + 1)}
      type="button"
    >{index + 1}. {label}</button>
  {/each}
</div>

{#if step === 1}
  <div class="panel">
    <h2>Paso 1 — Identidad y clase de competición</h2>
    <div class="grid two">
      <div class="field">
        <label for="nombre">Nombre de la competición</label>
        <input id="nombre" bind:value={name} />
      </div>
      <div class="field">
        <label for="tipo">Clase</label>
        <select id="tipo" bind:value={kind}>
          <option value="municipal_league">Liga municipal</option>
          <option value="regional_league">Liga regional</option>
          <option value="national_league">Liga nacional</option>
          <option value="domestic_league">Liga doméstica</option>
          <option value="international_club_league">Liga internacional de clubes</option>
          <option value="youth_league">Liga juvenil</option>
          <option value="reserve_league">Liga filial</option>
        </select>
      </div>
      <div class="field">
        <label for="participantes">Tipo de participante</label>
        <select id="participantes" disabled>
          <option value="clubs">Clubes</option>
        </select>
        <p class="small muted" style="margin:6px 0 0">
          Las competiciones de selecciones nacionales son Etapa 3 y todavía no
          están implementadas; el motor las rechaza en vez de disfrazarlas de
          liga de clubes.
        </p>
      </div>
      <div class="field">
        <label for="semilla">Semilla de generación</label>
        <input id="semilla" bind:value={seed} inputmode="numeric" />
        <p class="small muted" style="margin:6px 0 0">
          Misma semilla y mismas reglas, mismo mundo. Podrás regenerar antes de
          confirmar.
        </p>
      </div>
    </div>
    <button onclick={() => (step = 2)}>Continuar</button>
  </div>
{:else if step === 2}
  <div class="panel">
    <h2>Paso 2 — Territorio y jurisdicción</h2>
    <p class="small muted">
      Busca cualquier localidad, región o país del mundo. Lo que se guarda es la
      <strong>entidad geográfica resuelta</strong>, no el texto que escribas: así
      el territorio tiene identidad, fuente y moneda propias.
    </p>

    {#if geoStatus && !geoStatus.imported}
      <div class="notice">
        <strong>No hay gazetteer importado.</strong> {geoStatus.note}
        Mientras no lo esté, solo puedes usar los lugares curados de abajo.
      </div>
    {/if}

    <form onsubmit={searchGeography} class="buscador">
      <div class="field grow">
        <label for="geo-q">Buscar un lugar</label>
        <input
          id="geo-q"
          bind:value={geoQuery}
          placeholder="Kampala, Ciudad Juárez, Tokyo, Hermosillo…"
          autocomplete="off"
        />
      </div>
      <div class="field">
        <label for="geo-pais">País (ISO, opcional)</label>
        <input id="geo-pais" bind:value={geoCountry} maxlength="2" placeholder="MX" />
      </div>
      <button type="submit" disabled={geoSearching}>
        {geoSearching ? 'Buscando…' : 'Buscar'}
      </button>
    </form>

    {#if geoNote}<p class="small muted">{geoNote}</p>{/if}

    {#if geoResults.length}
      <table>
        <thead>
          <tr>
            <th>Lugar</th><th>Tipo</th><th>Jerarquía</th>
            <th class="num">Población</th><th>Moneda</th><th></th>
          </tr>
        </thead>
        <tbody>
          {#each geoResults as entity (entity.id)}
            <tr>
              <td>
                {entity.name}
                <div class="small muted">{entity.country_name} · {entity.source}:{entity.source_id}</div>
              </td>
              <td class="small">{GEO_KIND_LABEL[entity.kind] ?? entity.kind}</td>
              <td class="small muted">{entity.admin_path ?? '—'}</td>
              <td class="num">{entity.population ? formatNumber(entity.population) : '—'}</td>
              <td class="small">
                {#if entity.currency}{entity.currency}{:else}<span class="muted">sin datos</span>{/if}
              </td>
              <td>
                <button
                  class="ghost small"
                  type="button"
                  onclick={() => chooseEntity(entity)}
                  disabled={chosen.some((e) => e.id === entity.id)}
                >Elegir</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if geoStatus}<p class="small muted">Datos de {geoStatus.attribution}.</p>{/if}
    {/if}

    {#if chosen.length}
      <h3 style="margin-top:18px">Territorio de la competición</h3>
      {#each chosen as entity (entity.id)}
        <div class="row-block">
          <div class="spread">
            <div>
              <strong>{entity.name}</strong>
              <span class="tag">{GEO_KIND_LABEL[entity.kind] ?? entity.kind}</span>
              {#if entity.status !== 'verified'}<span class="tag warn">resolución incompleta</span>{/if}
              <div class="small muted">
                {entity.admin_path ?? entity.country_name}
                {#if entity.population} · {formatNumber(entity.population)} hab.{/if}
                {#if entity.currency} · moneda {entity.currency}{/if}
              </div>
            </div>
            <button class="ghost small" type="button" onclick={() => dropEntity(entity.id)}>
              Quitar
            </button>
          </div>
          {#if chosenContext[entity.id]}
            {@const ctx = chosenContext[entity.id]}
            <div class="small" style="margin-top:8px">
              <span class="tag">
                población: {GEO_CONFIDENCE_LABEL[ctx.population.confidence] ?? ctx.population.confidence}
              </span>
              <span class="tag">
                índices: {GEO_CONFIDENCE_LABEL[ctx.indices.confidence] ?? ctx.indices.confidence}
              </span>
              <span class={ctx.boundary.available ? 'tag accent' : 'tag warn'}>
                {ctx.boundary.available ? 'con límite administrativo' : 'sin polígono publicado'}
              </span>
            </div>
            {#each ctx.warnings as warning}
              <p class="small warn-text">{warning}</p>
            {/each}
          {/if}
        </div>
      {/each}

      <div class="grid two" style="margin-top:12px">
        <div class="field">
          <label for="modo">Delimitación</label>
          <select id="modo" bind:value={territoryMode}>
            <option value="administrative_area">Las unidades elegidas</option>
            <option value="radius">Radio desde la primera</option>
          </select>
          {#if territoryMode === 'radius'}
            <p class="small muted" style="margin:6px 0 0">
              Alternativa declarada cuando no hay polígono administrativo: es una
              aproximación en línea recta, no respeta fronteras, y se dice.
            </p>
          {/if}
        </div>
        {#if territoryMode === 'radius'}
          <div class="field">
            <label for="radio">Radio en kilómetros</label>
            <input id="radio" type="number" min="1" max="1500" bind:value={radiusKm} />
          </div>
        {/if}
      </div>
    {/if}

    <details style="margin-top:18px">
      <summary class="small muted">
        Lugares curados de este universo ({availablePlaces.length}) — índices calibrados a mano
      </summary>
      <div class="field">
        <label for="alcance">Alcance territorial</label>
        <select id="alcance" bind:value={scopeLevel} onchange={() => (selectedPlaces = [])}>
          <option value="municipal">Municipal</option>
          <option value="regional">Regional</option>
          <option value="national">Nacional</option>
          <option value="multinational">Multinacional</option>
        </select>
      </div>
      {#if availablePlaces.length === 0}
        <p class="small muted">No hay lugares curados de este tipo en el universo.</p>
      {:else}
        <div class="row">
          {#each availablePlaces as place (place.key)}
            <button
              type="button"
              class={selectedPlaces.includes(place.key) ? 'button' : 'button ghost'}
              onclick={() => togglePlace(place.key)}
            >
              {place.name}
              {#if place.profile}
                <span class="small muted"> · {formatNumber(place.profile.population)} hab.</span>
              {/if}
            </button>
          {/each}
        </div>
      {/if}
    </details>

    {#if resolvedCurrency}
      <p class="small muted">
        Moneda de la jurisdicción: <strong>{resolvedCurrency}</strong>. Sale del
        territorio, no de un ajuste del universo.
      </p>
    {/if}
    {#if territoryWarnings.length}
      <div class="notice">
        Lo que el simulador <strong>no</strong> sabe de este territorio y no va a
        inventar: {territoryWarnings.length} advertencia(s) arriba. Se podrá
        generar el mundo, pero los importes que falten saldrán sin determinar.
      </div>
    {/if}

    <div class="row">
      <button class="ghost" onclick={() => (step = 1)}>Atrás</button>
      <button onclick={() => (step = 3)} disabled={!hasTerritory}>Continuar</button>
    </div>
  </div>
{:else if step === 3}
  <div class="panel">
    <h2>Paso 3 — Modalidad de participación</h2>
    <p class="small muted">
      Una sola pregunta, y lo que define son <strong>reglas de participación</strong>:
      qué prácticas y acreditaciones admite la competición.
    </p>
    <div class="field">
      <label for="modalidad">¿Qué modalidad tendrá esta competición?</label>
      <select id="modalidad" bind:value={modality}>
        <option value="llanera">Llanera / recreativa informal</option>
        <option value="amateur_organized">Amateur organizada</option>
        <option value="school_formative">Escolar / formativa</option>
        <option value="semi_professional">Semiprofesional</option>
        <option value="professional">Profesional</option>
      </select>
    </div>
    <div class="notice info">{MODALITY_HELP[modality]}</div>
    <ul class="small muted">
      <li>
        <strong>No</strong> determina el patrimonio de los clubes, su propietario,
        sus salarios, sus instalaciones ni su personal.
      </li>
      <li>
        Dentro de la misma competición pueden convivir instituciones muy
        distintas, y cambiar con los años, mientras cumplan los requisitos.
      </li>
      <li>
        Si necesitas una exigencia real —prohibir salarios, pedir licencia,
        certificar la instalación— se configura en el paso de reglamento, con
        valor normativo.
      </li>
    </ul>
    <div class="row">
      <button class="ghost" onclick={() => (step = 2)}>Atrás</button>
      <button onclick={() => (step = 4)}>Continuar</button>
    </div>
  </div>
{:else if step === 4}
  <div class="panel">
    <h2>Paso 4 — Categoría y elegibilidad</h2>
    <div class="grid two">
      <div>
        <div class="field">
          <label for="edad-min">Edad mínima</label>
          <input id="edad-min" type="number" min="4" max="75" bind:value={minimumAge} />
        </div>
        <div class="field">
          <label class="row" style="gap:8px">
            <input type="checkbox" bind:checked={hasMaximumAge} style="width:auto" />
            <span>Hay edad máxima</span>
          </label>
          {#if hasMaximumAge}
            <input type="number" min="4" max="99" bind:value={maximumAge} />
          {:else}
            <p class="small muted" style="margin:6px 0 0">Sin tope: una liga de 40+ no lo necesita.</p>
          {/if}
        </div>
      </div>
      <div>
        <div class="field">
          <label for="corte">Corte de edad</label>
          <select id="corte" bind:value={ageCutoff}>
            <option value="season_start">Al inicio de la temporada</option>
            <option value="calendar_year">Año natural (1 de enero)</option>
            <option value="fixed_date">Fecha fija del reglamento</option>
          </select>
        </div>
        {#if ageCutoff === 'fixed_date'}
          <div class="field">
            <label for="corte-fecha">Fecha de corte (MM-DD)</label>
            <input id="corte-fecha" bind:value={cutoffMonthDay} placeholder="04-30" />
          </div>
        {/if}
        <div class="field">
          <label class="row" style="gap:8px">
            <input type="checkbox" bind:checked={keepsCategory} style="width:auto" />
            <span>Quien cumple años tras el corte termina la temporada en su categoría</span>
          </label>
        </div>
        <div class="field">
          <label class="row" style="gap:8px">
            <input type="checkbox" bind:checked={residencyRequired} style="width:auto" />
            <span>Exigir residencia en el territorio</span>
          </label>
        </div>
      </div>
    </div>

    {#if involvesMinors}
      <div class="notice">
        Competición con menores: la <strong>salvaguarda es obligatoria</strong> y se
        activa sola. El motor añadirá a las cuentas de cada club el seguro y la
        atención médica que eso implica. Elegir «infantil» no equivale por sí solo
        a una autorización de seguridad.
      </div>
    {/if}
    <p class="small muted">
      La edad es una condición de inscripción, no una liga aparte: crear una
      categoría 8–12 <strong>no</strong> crea otra de 13–17, y quien supera la edad
      sigue existiendo en el universo.
    </p>

    <div class="row">
      <button class="ghost" onclick={() => (step = 3)}>Atrás</button>
      <button onclick={() => (step = 5)}>Continuar</button>
    </div>
  </div>
{:else if step === 5}
  <div class="panel">
    <h2>Paso 5 — Participantes y admisión</h2>
    <div class="grid two">
      <div>
        <div class="field">
          <label for="clubes">Número objetivo de clubes</label>
          <input id="clubes" type="number" min="2" max="64" bind:value={clubCount} />
          <p class="small muted" style="margin:6px 0 0">
            Si el territorio no los sostiene, la previsualización lo advierte. El
            motor no inventa instituciones a la fuerza.
          </p>
        </div>
        <div class="field">
          <label for="roster-min">Mínimo de inscritos activos por equipo</label>
          <input id="roster-min" type="number" min="6" max="40" bind:value={minimumActiveRoster} />
        </div>
      </div>
      <div>
        <div class="field">
          <label for="talento">Procedencia admitida de los jugadores</label>
          <select id="talento" bind:value={talentPool}>
            <option value="shared_geographic">Del territorio de la competición</option>
            <option value="local_only">Solo de la localidad</option>
            <option value="open_international">Abierta, sin restricción de origen</option>
          </select>
          <p class="small muted" style="margin:6px 0 0">
            Es una regla de elegibilidad, no un selector de calidad: el talento
            vive en un mercado compartido con las demás competiciones.
          </p>
        </div>
        <div class="field">
          <label class="row" style="gap:8px">
            <input type="checkbox" bind:checked={foreignLimitEnabled} style="width:auto" />
            <span>Limitar extranjeros por equipo</span>
          </label>
          {#if foreignLimitEnabled}
            <input type="number" min="0" max="40" bind:value={foreignLimit} />
          {/if}
        </div>
      </div>
    </div>
    <div class="row">
      <button class="ghost" onclick={() => (step = 4)}>Atrás</button>
      <button onclick={() => (step = 6)}>Continuar</button>
    </div>
  </div>
{:else if step === 6}
  <StructureEditor
    clubCount={clubCount}
    bind:divisions
    bind:gates
    issues={scheduleError ? [scheduleError, ...structureIssues] : structureIssues}
    bracket={previewResult?.playoffs ?? null}
    preview={previewResult}
    currencyPrefix={resolvedCurrency ? `${resolvedCurrency} ` : '$'}
    bind:groupAssignment
    bind:gamesPerSeries
    bind:daysBetweenSeries
    bind:offseasonDays
    bind:restDays
    bind:playoffFormat
    bind:roundLengths
    bind:roundLabels
    bind:roundPairings
    bind:rosterSize
    bind:designatedHitter
    bind:extraInnings
    bind:mercyEnabled
    bind:mercyRunDiff
    bind:standingsPrimary
    bind:tiebreakers
    bind:licenceRequired
    bind:safetyCertRequired
    bind:amateurStatusRequired
    bind:minimumVenueCapacityEnabled
    bind:minimumVenueCapacity
    bind:compensationRule
    bind:entryFeeEnabled
    bind:entryFee
    onback={() => (step = 5)}
    oncontinue={() => (step = 7)}
  />

  <SchedulePreview
    payload={previewPayload}
    onresult={(resultado) => (previewResult = resultado)}
    view="headless"
  />
{:else if step === 7}
  <div class="panel">
    <h2>Paso 7 — Relaciones competitivas</h2>
    <div class="notice info">
      El valor por omisión es <strong>independiente</strong>. Crear esta liga
      <strong>no</strong> genera ninguna división inferior, filial ni categoría
      juvenil: aquí solo puedes vincularla con competiciones que ya existen.
    </div>

    <div class="row" style="margin-bottom:14px">
      <button
        class={relationshipMode === 'independent' ? 'button' : 'button ghost'}
        onclick={() => (relationshipMode = 'independent')}
      >Independiente</button>
      <button
        class={relationshipMode === 'dependent' ? 'button' : 'button ghost'}
        onclick={() => (relationshipMode = 'dependent')}
        disabled={competitions.length === 0}
      >Vinculada a otra competición</button>
    </div>

    {#if relationshipMode === 'independent'}
      <p class="small muted">
        Existe por sí sola: genera sus clubes, juega su temporada y corona a su
        campeón sin ascender ni descender con nadie. Siempre podrás vincularla
        después desde el grafo de competiciones.
      </p>
    {:else if competitions.length === 0}
      <p class="small muted">No hay ninguna otra competición con la que vincularla.</p>
    {:else}
      <div class="grid two">
        <div>
          <div class="field">
            <label for="posicion">Esta liga queda…</label>
            <select id="posicion" bind:value={linkPosition} onchange={() => void loadPartnerRules()}>
              <option value="below">por debajo de otra competición</option>
              <option value="above">por encima de otra competición</option>
            </select>
          </div>
          <div class="field">
            <label for="pareja">Competición</label>
            <select id="pareja" bind:value={linkPartnerId} onchange={() => void loadPartnerRules()}>
              <option value="">—</option>
              {#each competitions as competition (competition.id)}
                <option value={competition.id}>{competition.name}</option>
              {/each}
            </select>
          </div>
          <div class="field">
            <label for="naturaleza">Naturaleza exacta del vínculo</label>
            <select id="naturaleza" bind:value={linkRelation}>
              <option value="promotion_relegation">División: ascenso y descenso de clubes</option>
              <option value="affiliate">Filial: mueve jugadores, no clubes</option>
              <option value="youth">Juvenil: mueve jugadores, no clubes</option>
              <option value="development">Programa de desarrollo</option>
            </select>
          </div>
        </div>

        {#if isHierarchy}
          <fieldset>
            <legend>Plazas de movilidad</legend>
            <div class="field">
              <label for="plazas-mov">Plazas de intercambio (total de la superior)</label>
              <input id="plazas-mov" type="number" min="1" max="12" bind:value={linkSlots} />
              {#if existingQuota}
                <p class="small muted" style="margin:6px 0 0">
                  «{partner?.name}» ya intercambia <strong>{existingQuota}</strong> plazas
                  en total con sus alimentadoras. Es un total que se reparte, no una
                  cuota por rama: se adopta ese mismo número.
                </p>
              {/if}
            </div>
            <div class="field">
              <label for="criterio-ascenso">Quién asciende de la inferior</label>
              <select id="criterio-ascenso" bind:value={linkLowerMethod}>
                <option value="top_standings">Los mejores de la tabla</option>
                <option value="playoff_champion">El campeón primero, luego por tabla</option>
              </select>
            </div>
            <div class="field">
              <label for="aforo-min">Aforo mínimo para ascender (opcional)</label>
              <input id="aforo-min" bind:value={linkMinCapacity} inputmode="numeric" placeholder="sin requisito" />
            </div>
            <div class="field">
              <label for="deuda-max">Deuda máxima, en veces su presupuesto (opcional)</label>
              <input id="deuda-max" bind:value={linkMaxDebt} inputmode="decimal" placeholder="sin requisito" />
            </div>
            {#if linkMinCapacity.trim() !== '' || linkMaxDebt.trim() !== ''}
              <div class="field">
                <label for="politica">Si el club que debería ascender no cumple</label>
                <select id="politica" bind:value={linkFailurePolicy}>
                  <option value="substitute">Asciende el siguiente que sí cumpla</option>
                  <option value="block">La plaza queda vacía (y nadie baja por ella)</option>
                  <option value="exception">Asciende por excepción, y queda registrado</option>
                </select>
              </div>
            {/if}
            <div class="field">
              <label for="desde">En vigor desde la temporada (opcional)</label>
              <input id="desde" bind:value={linkFromSeason} inputmode="numeric" placeholder="la próxima" />
            </div>
          </fieldset>
        {/if}
      </div>

      {#if linkPartnerId}
        <div class="notice">
          {#if isHierarchy}
            Al cerrar cada temporada, <strong>{linkSlots}</strong> club(es) ascenderán
            de «{lowerName}» a «{upperName}» y otros {linkSlots} descenderán en
            sentido contrario, conservando su identidad.
          {:else}
            Vínculo de desarrollo entre «{name}» y «{partner?.name}»: moverá
            jugadores. Ningún club cambiará de categoría.
          {/if}
        </div>
      {/if}
    {/if}

    <div class="row">
      <button class="ghost" onclick={() => (step = 6)}>Atrás</button>
      <button
        onclick={runPreview}
        disabled={working || (relationshipMode === 'dependent' && !linkPartnerId)}
      >
        {working ? 'Generando…' : 'Previsualizar con esta semilla'}
      </button>
    </div>
  </div>
{:else if step === 8 && preview}
  <div class="panel">
    <div class="spread">
      <h2>Paso 8 — Previsualización, viabilidad y confirmación</h2>
      <div class="row">
        <button class="ghost" onclick={() => (step = 6)}>Modificar competición</button>
        <button class="ghost" onclick={reroll} disabled={working}>Regenerar propuesta</button>
        <button
          onclick={confirm}
          disabled={working || createdEditionId !== '' || blocking.length > 0 || !previewIsCurrent}
        >
          {working ? 'Creando el mundo…' : 'Crear competición'}
        </button>
      </div>
    </div>
    <p class="small muted">
      Esta propuesta está <strong>guardada pero no creada</strong>: el mundo no se
      ha tocado. Puedes validarla o regenerarla, pero no editar club por club:
      esas decisiones son de cada institución.
    </p>
    <p class="small muted mono">
      propuesta {preview.preview_id.slice(0, 8)} · huella
      {preview.intent_fingerprint.slice(0, 16)}… · motor {preview.engine_version} ·
      semilla {preview.seed}
      {#if draft}· borrador {DRAFT_STATE_LABEL[draft.state] ?? draft.state}{/if}
    </p>

    {#if !previewIsCurrent}
      <div class="notice">
        Has cambiado algo después de generar esta propuesta, así que ya no
        describe lo que crearías. <strong>Vuelve a previsualizar</strong>: el
        servidor rechaza confirmar una propuesta obsoleta.
      </div>
    {/if}

    {#if blocking.length}
      <div class="notice">
        <strong>No se puede crear todavía.</strong>
        <ul class="small">
          {#each blocking as issue}
            <li>
              <span class="tag warn">{ISSUE_CODE_LABEL[issue.code] ?? issue.code}</span>
              {issue.message}
              {#each issue.suggestions as suggestion}<div class="muted">· {suggestion}</div>{/each}
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    {#if linkWarning}
      <div class="notice">
        La competición <strong>se creó</strong> y su mundo también, pero el vínculo
        no: {linkWarning}. Queda independiente; puedes vincularla desde el
        <a href={`/universos/${universeId}/grafo`}>grafo de competiciones</a>.
        {#if createdEditionId}
          <a href={`/ediciones/${createdEditionId}`}>Ver la edición generada</a>.
        {/if}
      </div>
    {/if}

    {#each warnings as issue}
      <div class="notice">
        <span class="tag">{ISSUE_CODE_LABEL[issue.code] ?? issue.code}</span>
        {issue.message}
      </div>
    {/each}

    <div class="grid three" style="margin:16px 0">
      <div class="stat">
        <div class="value">{MODALITY_LABEL[preview.context.participation_modality] ?? preview.context.participation_modality}</div>
        <div class="label">
          modalidad · compensación {preview.context.compensation_rule}
        </div>
      </div>
      <div class="stat">
        <div class="value">
          {#if preview.context.currency}
            {formatMoney(preview.context.budget_range.median, preview.context.currency)}
          {:else}
            sin determinar
          {/if}
        </div>
        <div class="label">
          presupuesto mediano
          {#if preview.context.currency}
            · de {formatMoney(preview.context.budget_range.min, preview.context.currency)}
            a {formatMoney(preview.context.budget_range.max, preview.context.currency)}
          {:else}
            · esta jurisdicción no tiene datos económicos
          {/if}
        </div>
      </div>
      <div class="stat">
        <div class="value">{preview.context.schedule.games}</div>
        <div class="label">
          partidos · {preview.context.schedule.games_per_club} por club
          {#if preview.context.schedule.adjusted}(pediste {preview.context.schedule.requested_games_per_club}){/if}
        </div>
      </div>
    </div>

    {#if preview.context.reference_monthly_cost}
      <p class="small muted">
        Nivel de recursos resultante: <strong>{preview.context.resource_tier}</strong>
        (índice {preview.context.effective_level}). Los importes están en
        {preview.context.currency} y se pueden leer como múltiplos del coste
        mensual de referencia de la jurisdicción
        ({formatMoney(preview.context.reference_monthly_cost, preview.context.currency ?? 'MXN')}),
        que es una estimación declarada, no una cifra oficial.
      </p>
    {/if}

    {#if preview.context.structure}
      <h3>Divisiones</h3>
      <p class="small muted">
        {preview.context.structure.count} divisiones repartidas
        {GROUP_ASSIGNMENT_LABEL[preview.context.structure.assignment ?? ''] ??
          preview.context.structure.assignment}:
        {#each preview.context.structure.groups as grupo, i}{i > 0 ? ' · ' : ''}<strong
            >{grupo.label}</strong
          > ({grupo.clubs} clubes){/each}.
        {#if preview.context.schedule.intra_group_games}
          Del calendario, {preview.context.schedule.intra_group_games} partidos son
          dentro de la división y {preview.context.schedule.inter_group_games} contra
          las otras.
        {/if}
      </p>
    {/if}

    <h3>Instituciones que el motor propone</h3>
    <p class="small muted">
      Ninguna de estas características se eligió en el formulario: cada club
      negoció con su entorno por separado.
    </p>
    <table>
      <thead>
        <tr>
          <th>Club</th>
          <th>Zona</th>
          {#if preview.context.structure}<th>División</th>{/if}
          <th>Gobierno</th>
          <th>Sede</th>
          <th class="num">Aforo</th>
          <th class="num">Presupuesto</th>
          <th>Cuentas</th>
        </tr>
      </thead>
      <tbody>
        {#each preview.proposed_clubs as club}
          <tr>
            <td>
              <span class="row" style="gap:8px">
                <span style={`display:inline-block;width:10px;height:10px;border-radius:2px;background:${club.primary_color};border:1px solid ${club.secondary_color}`}></span>
                {club.name}
              </span>
            </td>
            <td class="small">{club.place}</td>
            {#if preview.context.structure}
              <td class="small">
                {club.group}
                {#if club.group_reason}
                  <div class="muted">{club.group_reason}</div>
                {/if}
              </td>
            {/if}
            <td class="small">
              {GOVERNANCE_LABEL[club.governance ?? ''] ?? club.governance ?? '—'}
              {#if club.has_owner === false}<span class="tag">sin propietario</span>{/if}
            </td>
            <td class="small">{VENUE_USAGE_LABEL[club.venue_usage ?? ''] ?? club.venue_usage ?? '—'}</td>
            <td class="num">{formatNumber(club.capacity)}</td>
            <td class="num">
              {#if club.financial_assessment?.currency}
                {formatMoney(club.annual_budget, club.financial_assessment.currency)}
              {:else}
                <span class="muted">sin determinar</span>
              {/if}
            </td>
            <td class="small">
              {#if club.financial_assessment}
                <details>
                  <summary>
                    {club.financial_assessment.components.length} partidas ·
                    {club.financial_assessment.confidence}
                  </summary>
                  <ul class="desglose">
                    {#each club.financial_assessment.components as component}
                      <li>
                        <strong>{component.label}</strong>
                        {#if component.amount && club.financial_assessment.currency}
                          · {formatMoney(component.amount, club.financial_assessment.currency)}
                        {:else}
                          · <span class="muted">sin cifra</span>
                        {/if}
                        <span class={component.kind === 'revenue' ? 'tag accent' : 'tag'}>
                          {component.kind === 'revenue' ? 'ingreso' : 'gasto'}
                        </span>
                        {#if component.mandatory}<span class="tag warn">obligatorio</span>{/if}
                        <div class="muted">{component.basis}</div>
                      </li>
                    {/each}
                  </ul>
                  {#each club.financial_assessment.risks as risk}
                    <p class="small">{risk}</p>
                  {/each}
                </details>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    <h3 style="margin-top:20px">Mercados admisibles</h3>
    <table>
      <thead>
        <tr>
          <th>Mercado</th>
          <th class="num">Población</th>
          <th class="num">Economía</th>
          <th class="num">Cultura beisbolística</th>
          <th class="num">Oportunidad de formación</th>
          <th>Procedencia</th>
        </tr>
      </thead>
      <tbody>
        {#each preview.context.markets as market (market.place_key)}
          <tr>
            <td>{market.name}</td>
            <td class="num">{formatNumber(market.population)}</td>
            <td class="num">{market.economy_index.toFixed(2)}</td>
            <td class="num">{market.culture_index.toFixed(2)}</td>
            <td class="num">{market.training_opportunity.toFixed(2)}</td>
            <td><ConfidenceTag confidence={market.confidence} /></td>
          </tr>
        {/each}
      </tbody>
    </table>

    <p class="small muted">
      {formatNumber(preview.context.people_generated)} personas en la población deportiva,
      de las cuales {formatNumber(preview.context.free_agents)} quedarían sin equipo.
      Semilla <span class="mono">{preview.seed}</span>, reglamento
      <span class="mono">{preview.ruleset_checksum.slice(0, 12)}</span>.
    </p>

    <h3 style="margin-top:20px">De dónde salen estos números</h3>
    {#each preview.context.provenance as record}
      <div style="margin-bottom:10px">
        <div class="small muted mono">{record.procedure}</div>
        {#each record.notes.slice(0, 6) as note}
          <div class="small">
            <strong>{note.field}</strong> = <span class="mono">{String(note.value)}</span>
            <span class="tag" style="margin-left:6px">{CONFIDENCE_LABEL[note.confidence] ?? note.confidence}</span>
            <div class="muted">{note.derivation}</div>
          </div>
        {/each}
        {#each record.assumptions as assumption}
          <div class="small" style="color:var(--accent-2)">Supuesto: {assumption}</div>
        {/each}
      </div>
    {/each}
  </div>
{/if}

<style>
  .steps {
    flex-wrap: wrap;
    margin-bottom: 18px;
  }
  .steps button {
    border: 0;
    cursor: pointer;
  }
  ul.desglose {
    margin: 8px 0 0;
    padding-left: 16px;
  }
  ul.desglose li {
    margin-bottom: 8px;
  }
  form.buscador {
    display: flex;
    gap: 10px;
    align-items: flex-end;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }
  form.buscador .grow {
    flex: 1 1 260px;
  }
  .row-block {
    padding: 10px 0;
    border-bottom: 1px solid var(--line);
  }
  .warn-text {
    color: var(--accent-2);
  }
  button.small {
    padding: 2px 8px;
    font-size: 0.85em;
  }
</style>
