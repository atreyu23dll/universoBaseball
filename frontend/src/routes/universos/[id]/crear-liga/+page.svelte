<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import type { GenerationPreview, Place } from '$lib/api/types';
  import { CONFIDENCE_LABEL, formatMoney, formatNumber, INSTITUTION_LABEL, TIER_LABEL, VENUE_LABEL } from '$lib/format';
  import ConfidenceTag from '$lib/components/ConfidenceTag.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const universeId = $derived($page.params.id);

  let step = $state(1);
  let places = $state<Place[]>([]);
  let preview = $state<GenerationPreview | null>(null);
  let error = $state<unknown>(null);
  let working = $state(false);

  // --- Paso A: identidad y ámbito ---
  let name = $state('Liga Municipal de Ciudad Juárez');
  let kind = $state('municipal_league');
  let scopeLevel = $state('municipal');
  let selectedPlaces = $state<string[]>(['MX-CJS']);
  let professionalization = $state('contextual_auto');
  let economy = $state('contextual_auto');

  // --- Paso B: relación con otras competiciones ---
  // El valor por omisión es INDEPENDIENTE y la interfaz no ofrece crear ligas
  // inferiores desde aquí: una competición nueva no arrastra ninguna otra.
  let relationshipMode = $state('independent');

  // --- Paso C: formato ---
  let clubCount = $state(12);
  let gamesTarget = $state(44);
  let rosterSize = $state(26);
  let restDays = $state<number[]>([0]);
  let standingsPrimary = $state('win_percentage');
  let tiebreakers = $state<string[]>(['head_to_head', 'run_differential']);
  let playoffSlots = $state(4);
  let playoffFormat = $state('best_of_series');
  let roundLengths = $state('3,5');
  let designatedHitter = $state(true);
  let seed = $state('18723');

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

  /** Rondas necesarias para el bracket: 4 plazas → 2 rondas, 8 → 3. */
  const expectedRounds = $derived(playoffSlots >= 2 ? Math.log2(playoffSlots) : 0);

  function buildRuleset() {
    const lengths = roundLengths
      .split(',')
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isFinite(value) && value > 0);
    return {
      name,
      kind,
      relationship_mode: relationshipMode,
      scope: {
        level: scopeLevel,
        country_code: 'MX',
        place_keys: selectedPlaces
      },
      season: {
        games_per_club_target: gamesTarget,
        roster_size: rosterSize,
        rest_days_weekday: restDays,
        designated_hitter: designatedHitter
      },
      standings: { primary: standingsPrimary, tiebreakers },
      playoffs:
        playoffFormat === 'none'
          ? { slots: 0, format: 'none', round_lengths: [] }
          : { slots: playoffSlots, format: playoffFormat, round_lengths: lengths },
      generation: {
        club_count: clubCount,
        professionalization,
        economy,
        seed: seed.trim() === '' ? null : Number(seed)
      }
    };
  }

  async function runPreview() {
    working = true;
    error = null;
    try {
      preview = await api.post<GenerationPreview>(
        `/universes/${universeId}/competitions/preview`,
        buildRuleset()
      );
      step = 4;
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
    working = true;
    error = null;
    try {
      const created = await api.post<{ id: string }>(
        `/universes/${universeId}/competitions`,
        buildRuleset()
      );
      const edition = await api.post<{ edition_id: string }>(
        `/competitions/${created.id}/generate`
      );
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

  function toggleTiebreaker(value: string) {
    tiebreakers = tiebreakers.includes(value)
      ? tiebreakers.filter((t) => t !== value)
      : [...tiebreakers, value];
  }

  function toggleRestDay(day: number) {
    restDays = restDays.includes(day) ? restDays.filter((d) => d !== day) : [...restDays, day];
  }

  onMount(async () => {
    try {
      const response = await api.get<{ items: Place[] }>(`/universes/${universeId}/geography`);
      places = response.items;
    } catch (err) {
      error = err;
    }
  });

  const weekdays = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
</script>

<h1>Crear competición</h1>
<p class="muted small">
  Esto es lo único que hace falta definir. Clubes, jugadores, estadios,
  presupuestos y calendario los genera el motor a partir de estas reglas.
</p>

<ErrorNotice {error} />

<div class="row" style="margin-bottom:18px">
  {#each ['Identidad y ámbito', 'Relación', 'Formato y reglamento', 'Previsualización'] as label, index}
    <span class={step === index + 1 ? 'tag accent' : 'tag'}>{index + 1}. {label}</span>
  {/each}
</div>

{#if step === 1}
  <div class="panel">
    <h2>Paso A — Identidad y ámbito</h2>
    <div class="grid two">
      <div>
        <div class="field">
          <label for="nombre">Nombre de la competición</label>
          <input id="nombre" bind:value={name} />
        </div>
        <div class="field">
          <label for="tipo">Tipo</label>
          <select id="tipo" bind:value={kind}>
            <option value="municipal_league">Liga municipal</option>
            <option value="regional_league">Liga regional</option>
            <option value="national_league">Liga nacional</option>
            <option value="domestic_league">Liga doméstica</option>
            <option value="international_club_league">Liga internacional de clubes</option>
          </select>
        </div>
        <div class="field">
          <label for="alcance">Alcance territorial</label>
          <select id="alcance" bind:value={scopeLevel} onchange={() => (selectedPlaces = [])}>
            <option value="municipal">Municipal</option>
            <option value="regional">Regional</option>
            <option value="national">Nacional</option>
            <option value="multinational">Multinacional</option>
          </select>
          <p class="small muted" style="margin:6px 0 0">
            El alcance no impone el grado de profesionalización: son dos
            parámetros independientes.
          </p>
        </div>
      </div>
      <div>
        <div class="field">
          <label for="prof">Profesionalización</label>
          <select id="prof" bind:value={professionalization}>
            <option value="contextual_auto">Automática por contexto (recomendado)</option>
            <option value="amateur">Amateur</option>
            <option value="semi_professional">Semiprofesional</option>
            <option value="professional">Profesional</option>
            <option value="elite">Élite</option>
          </select>
        </div>
        <div class="field">
          <label for="econ">Intensidad económica</label>
          <select id="econ" bind:value={economy}>
            <option value="contextual_auto">Automática por contexto</option>
            <option value="amateur">Baja</option>
            <option value="semi_professional">Media</option>
            <option value="professional">Alta</option>
            <option value="elite">Muy alta</option>
          </select>
        </div>
        <div class="field">
          <label for="semilla">Semilla de generación</label>
          <input id="semilla" bind:value={seed} inputmode="numeric" />
        </div>
      </div>
    </div>

    <fieldset>
      <legend>Territorio</legend>
      {#if availablePlaces.length === 0}
        <p class="small muted">No hay lugares de este tipo en el universo.</p>
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
        <p class="small muted" style="margin:10px 0 0">
          Las poblaciones son estimaciones de orden de magnitud con año
          declarado, no un censo. Sirven para escalar el mercado.
        </p>
      {/if}
    </fieldset>

    <button onclick={() => (step = 2)} disabled={selectedPlaces.length === 0}>Continuar</button>
  </div>
{:else if step === 2}
  <div class="panel">
    <h2>Paso B — Relación con otras competiciones</h2>
    <div class="notice info">
      El valor por omisión es <strong>independiente</strong>, y lo seguirá siendo
      hasta que crees un vínculo explícito. Crear esta liga
      <strong>no</strong> genera ninguna división inferior, filial ni categoría
      juvenil.
    </div>
    <div class="field">
      <label for="relacion">Naturaleza</label>
      <select id="relacion" bind:value={relationshipMode}>
        <option value="independent">Independiente</option>
      </select>
    </div>
    <p class="small muted">
      La opción «dependiente» se configura después, desde el grafo de
      competiciones, vinculando dos ligas que ya existen: así la relación es la
      única autoridad de sus plazas de ascenso y descenso.
      <strong>Aviso:</strong> el intercambio de clubes al cerrar temporada es
      Etapa 2 y todavía no está implementado.
    </p>
    <div class="row">
      <button class="ghost" onclick={() => (step = 1)}>Atrás</button>
      <button onclick={() => (step = 3)}>Continuar</button>
    </div>
  </div>
{:else if step === 3}
  <div class="panel">
    <h2>Paso C — Formato competitivo y reglamento</h2>
    <div class="grid two">
      <fieldset>
        <legend>Estructura y calendario</legend>
        <div class="field">
          <label for="clubes">Número de clubes</label>
          <input id="clubes" type="number" min="2" max="64" bind:value={clubCount} />
        </div>
        <div class="field">
          <label for="partidos">Partidos por club (objetivo)</label>
          <input id="partidos" type="number" min="2" max="250" bind:value={gamesTarget} />
          <p class="small muted" style="margin:6px 0 0">
            Si el objetivo no cuadra en jornadas completas, la previsualización lo
            avisa y propone los valores exactos. No se ajusta en silencio.
          </p>
        </div>
        <div class="field">
          <label for="roster">Tamaño de plantilla</label>
          <input id="roster" type="number" min="14" max="40" bind:value={rosterSize} />
        </div>
        <div class="field" role="group" aria-labelledby="descanso-leyenda">
          <span class="small muted" id="descanso-leyenda">Días de descanso semanal</span>
          <div class="row">
            {#each weekdays as day, index}
              <button
                type="button"
                class={restDays.includes(index) ? 'button' : 'button ghost'}
                onclick={() => toggleRestDay(index)}
              >{day}</button>
            {/each}
          </div>
        </div>
        <div class="field">
          <label class="row" style="gap:8px">
            <input type="checkbox" bind:checked={designatedHitter} style="width:auto" />
            <span>Bateador designado</span>
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Clasificación y postemporada</legend>
        <div class="field">
          <label for="criterio">Criterio principal</label>
          <select id="criterio" bind:value={standingsPrimary}>
            <option value="win_percentage">Porcentaje de victorias</option>
            <option value="wins">Victorias absolutas</option>
            <option value="points">Sistema de puntos</option>
          </select>
        </div>
        <div class="field" role="group" aria-labelledby="desempate-leyenda">
          <span class="small muted" id="desempate-leyenda">Desempates, en orden</span>
          <div class="row">
            {#each [['head_to_head', 'enfrentamiento directo'], ['run_differential', 'diferencia de carreras'], ['runs_for', 'carreras a favor'], ['fewest_runs_against', 'menos carreras en contra'], ['coin_flip', 'sorteo reproducible']] as [value, label]}
              <button
                type="button"
                class={tiebreakers.includes(value) ? 'button' : 'button ghost'}
                onclick={() => toggleTiebreaker(value)}
              >{label}</button>
            {/each}
          </div>
        </div>
        <div class="field">
          <label for="formato">Formato de playoffs</label>
          <select id="formato" bind:value={playoffFormat}>
            <option value="best_of_series">Series al mejor de N</option>
            <option value="single_elimination">Eliminación directa</option>
            <option value="none">Sin postemporada (campeón por tabla)</option>
          </select>
        </div>
        {#if playoffFormat !== 'none'}
          <div class="field">
            <label for="plazas">Plazas de playoff (potencia de 2)</label>
            <select id="plazas" bind:value={playoffSlots}>
              <option value={2}>2</option>
              <option value={4}>4</option>
              <option value={8}>8</option>
              <option value={16}>16</option>
            </select>
          </div>
          {#if playoffFormat === 'best_of_series'}
            <div class="field">
              <label for="rondas">Longitud de cada ronda ({expectedRounds} necesarias)</label>
              <input id="rondas" bind:value={roundLengths} placeholder="3,5" />
              <p class="small muted" style="margin:6px 0 0">
                Números impares separados por comas, una por ronda.
              </p>
            </div>
          {/if}
        {/if}
      </fieldset>
    </div>
    <div class="row">
      <button class="ghost" onclick={() => (step = 2)}>Atrás</button>
      <button onclick={runPreview} disabled={working}>
        {working ? 'Generando…' : 'Previsualizar con esta semilla'}
      </button>
    </div>
  </div>
{:else if step === 4 && preview}
  <div class="panel">
    <div class="spread">
      <h2>Paso D — Previsualización</h2>
      <div class="row">
        <button class="ghost" onclick={() => (step = 3)}>Cambiar reglas</button>
        <button class="ghost" onclick={reroll} disabled={working}>Otra semilla</button>
        <button onclick={confirm} disabled={working}>
          {working ? 'Creando el mundo…' : 'Confirmar y generar'}
        </button>
      </div>
    </div>
    <p class="small muted">
      Nada de esto está guardado todavía. Puedes volver a generar cuantas veces
      quieras antes de confirmar.
    </p>

    {#each preview.warnings as warning}
      <div class="notice">{warning}</div>
    {/each}

    <div class="grid three" style="margin:16px 0">
      <div class="stat">
        <div class="value">{TIER_LABEL[preview.context.professionalization_tier] ?? preview.context.professionalization_tier}</div>
        <div class="label">nivel resuelto · índice {preview.context.professionalization_score.toFixed(3)}</div>
      </div>
      <div class="stat">
        <div class="value">{formatMoney(preview.budget_range.median, preview.context.currency)}</div>
        <div class="label">
          presupuesto mediano · de {formatMoney(preview.budget_range.min, preview.context.currency)}
          a {formatMoney(preview.budget_range.max, preview.context.currency)}
        </div>
      </div>
      <div class="stat">
        <div class="value">{preview.schedule.games}</div>
        <div class="label">
          partidos · {preview.schedule.games_per_club} por club
          {#if preview.schedule.adjusted}(pediste {preview.schedule.requested_games_per_club}){/if}
        </div>
      </div>
    </div>

    <h3>Mercados admisibles</h3>
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

    <h3 style="margin-top:20px">Clubes que se generarían</h3>
    <table>
      <thead>
        <tr>
          <th>Club</th>
          <th>Zona</th>
          <th>Institución</th>
          <th class="num">Presupuesto anual</th>
          <th>Instalación</th>
          <th class="num">Aforo</th>
        </tr>
      </thead>
      <tbody>
        {#each preview.clubs as club}
          <tr>
            <td>
              <span class="row" style="gap:8px">
                <span style={`display:inline-block;width:10px;height:10px;border-radius:2px;background:${club.primary_color};border:1px solid ${club.secondary_color}`}></span>
                {club.name}
              </span>
            </td>
            <td class="small">{club.place}</td>
            <td class="small">{INSTITUTION_LABEL[club.institutional_type] ?? club.institutional_type}</td>
            <td class="num">{formatMoney(club.annual_budget, preview.context.currency)}</td>
            <td class="small">{club.venue_name} <span class="muted">({VENUE_LABEL[club.venue_type] ?? club.venue_type})</span></td>
            <td class="num">{formatNumber(club.capacity)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="small muted">
      {formatNumber(preview.people_generated)} personas en la población deportiva,
      de las cuales {formatNumber(preview.free_agents)} quedarían sin equipo.
      Semilla <span class="mono">{preview.seed}</span>, reglamento
      <span class="mono">{preview.ruleset_checksum.slice(0, 12)}</span>.
    </p>

    <h3 style="margin-top:20px">De dónde salen estos números</h3>
    {#each preview.provenance as record}
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
