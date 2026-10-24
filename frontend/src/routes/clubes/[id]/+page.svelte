<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import {
    CHANGE_FIELD_LABEL,
    COMPONENT_LABEL,
    CONFIDENCE_LABEL,
    FINANCIAL_CONFIDENCE_LABEL,
    GOVERNANCE_LABEL,
    OUTCOME_LABEL,
    RESOURCE_TIER_LABEL,
    VENUE_USAGE_LABEL,
    formatMoney,
    formatNumber,
    INSTITUTION_LABEL,
    VENUE_LABEL
  } from '$lib/format';
  import ConfidenceTag from '$lib/components/ConfidenceTag.svelte';
  import Crest from '$lib/components/Crest.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const clubId = $derived($page.params.id);
  let club = $state<any>(null);
  let error = $state<unknown>(null);

  onMount(async () => {
    try {
      club = await api.get<any>(`/clubs/${clubId}`);
    } catch (err) {
      error = err;
    }
  });
</script>

<ErrorNotice {error} />

{#if club}
  <div class="row" style="gap:16px;margin-bottom:16px;align-items:flex-start">
    <Crest primary={club.primary_color} secondary={club.secondary_color}
           shape={club.crest_shape} motif={club.crest_motif} size={64} title={club.name} />
    <div>
      <h1 style="margin-bottom:2px">{club.name}</h1>
      <p class="muted small" style="margin:0">
        {INSTITUTION_LABEL[club.institutional_type] ?? club.institutional_type}
        · fundado en {club.foundation_year}
        · {club.home_place?.name}
        {#if club.home_place}<ConfidenceTag confidence={club.home_place.confidence} sources={club.home_place.sources} />{/if}
      </p>
      <p class="small" style="margin:6px 0 0">{club.history_note}</p>
      {#if club.status === 'folded'}
        <p class="small" style="margin:6px 0 0;color:var(--accent-2)">
          <span class="tag warn">desaparecido</span>
          Este club dejó de competir. Su ficha y su historia se conservan: no se
          borra nada de lo que hizo.
        </p>
      {/if}
    </div>
  </div>

  <div class="grid three" style="margin-bottom:18px">
    <div class="stat">
      <div class="value">{formatMoney(club.finances.annual_budget, club.finances.currency)}</div>
      <div class="label">presupuesto anual</div>
    </div>
    <div class="stat">
      <div class="value">{formatMoney(club.finances.debt, club.finances.currency)}</div>
      <div class="label">deuda · caja {formatMoney(club.finances.cash, club.finances.currency)}</div>
    </div>
    <div class="stat">
      <div class="value">{formatNumber(club.fan_base)}</div>
      <div class="label">base social estimada</div>
    </div>
  </div>

  <div class="grid sidebar">
    <div class="panel">
      <h2>Plantilla ({club.roster.length})</h2>
      <table>
        <thead>
          <tr><th>Jugador</th><th class="num">Edad</th><th>Pos</th><th>Rol</th><th>B/L</th><th class="num">Proyección</th></tr>
        </thead>
        <tbody>
          {#each club.roster as player (player.id)}
            <tr>
              <td><a href={`/personas/${player.id}`}>{player.name}</a></td>
              <td class="num">{player.age}</td>
              <td>{player.primary_position}</td>
              <td class="small muted">{player.pitcher_role ?? ''}</td>
              <td class="small">{player.bats}/{player.throws}</td>
              <td class="num">{player.scouted_potential.toFixed(2)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="small muted">
        La columna de proyección es lo que creen los informes del club, con su
        error. No es el potencial real del jugador: el motor lo guarda aparte y
        la interfaz no lo muestra.
      </p>
    </div>

    <div>
      {#if club.venue}
        <div class="panel">
          <h2>{club.venue.name}</h2>
          <p class="small muted" style="margin-top:0">
            {VENUE_LABEL[club.venue.type] ?? club.venue.type}
            · aforo {formatNumber(club.venue.capacity)}
            · {club.venue.elevation_m} m de altitud
            {#if club.venue.has_roof}· techado{/if}
            <br /><span class="tag fictional">recinto ficticio</span>
          </p>
          <svg viewBox="0 0 200 180" width="100%" height="200" role="img" aria-label="Vista del terreno">
            <!-- Vista 2D del terreno a escala desde las dimensiones reales -->
            <path
              d={`M100 165 L${100 - club.venue.dimensions.left_field_m * 0.62} ${165 - club.venue.dimensions.left_field_m * 0.62} Q100 ${165 - club.venue.dimensions.center_field_m * 1.08} ${100 + club.venue.dimensions.right_field_m * 0.62} ${165 - club.venue.dimensions.right_field_m * 0.62} Z`}
              fill="#1d3326" stroke={club.primary_color} stroke-width="2" />
            <path d="M100 165 L128 137 L100 109 L72 137 Z" fill="#3a2a1d" stroke="#5a4433" />
            <circle cx="100" cy="137" r="3" fill="#caa06a" />
            <text x="6" y="150" fill="#8b98a8" font-size="9">{club.venue.dimensions.left_field_m} m</text>
            <text x="86" y="26" fill="#8b98a8" font-size="9">{club.venue.dimensions.center_field_m} m</text>
            <text x="150" y="150" fill="#8b98a8" font-size="9">{club.venue.dimensions.right_field_m} m</text>
          </svg>
          <p class="small muted">
            Barda de {club.venue.dimensions.wall_height_m} m, orientación
            {club.venue.dimensions.orientation_deg}°, mantenimiento
            {(club.venue.maintenance * 100).toFixed(0)} %. Estas medidas afectan
            de verdad a los jonrones y los batazos de extrabase.
          </p>
        </div>
      {/if}

      {#if club.organization}
        <div class="panel">
          <h2>Cómo se organiza</h2>
          <p class="small muted">
            Lo decidió el club según su entorno. No se eligió en ningún formulario.
          </p>
          <table>
            <tbody>
              <tr>
                <td>Gobierno</td>
                <td>{GOVERNANCE_LABEL[club.organization.governance] ?? club.organization.governance}</td>
              </tr>
              <tr>
                <td>Propiedad</td>
                <td>{club.organization.has_owner ? 'tiene propietario' : 'sin propietario individual'}</td>
              </tr>
              <tr>
                <td>Sede</td>
                <td>{VENUE_USAGE_LABEL[club.organization.venue_agreement] ?? club.organization.venue_agreement}</td>
              </tr>
              <tr>
                <td>Alcance comunitario</td>
                <td class="num">{club.organization.community_reach?.toFixed(2)}</td>
              </tr>
            </tbody>
          </table>
          {#if club.organization.roles?.length}
            <h3 style="margin-top:12px">Responsabilidades</h3>
            <table>
              <tbody>
                {#each club.organization.roles as role}
                  <tr>
                    <td class="small">{role.role.replaceAll('_', ' ')}</td>
                    <td class="small">
                      {#if role.vacant}
                        <span class="tag warn">sin cubrir</span>
                      {:else if role.paid}
                        <span class="tag accent">remunerado</span>
                      {:else}
                        <span class="tag">voluntario</span>
                      {/if}
                      {#if role.doubles_with}
                        <span class="muted">la misma persona que {role.doubles_with.replaceAll('_', ' ')}</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>
      {/if}

      {#if club.finances.assessment}
        <div class="panel">
          <h2>De dónde sale su dinero</h2>
          {#if club.finances.assessment.confidence === 'insufficient_data'}
            <div class="notice">
              No hay datos económicos locales suficientes para cuantificar este
              club. Los importes quedan sin determinar a propósito, en vez de
              inventarse.
            </div>
          {:else}
            <div class="grid three">
              <div class="stat">
                <div class="value">{formatMoney(club.finances.assessment.revenue ?? 0, club.finances.currency ?? 'MXN')}</div>
                <div class="label">ingresos previstos de la temporada</div>
              </div>
              <div class="stat">
                <div class="value">{formatMoney(club.finances.assessment.expenses ?? 0, club.finances.currency ?? 'MXN')}</div>
                <div class="label">gasto previsto · el «presupuesto»</div>
              </div>
              <div class="stat">
                <div class="value">{club.finances.assessment.months_of_reference_cost?.toFixed(1)}</div>
                <div class="label">
                  meses de gasto doméstico de su jurisdicción ·
                  {RESOURCE_TIER_LABEL[club.finances.assessment.tier ?? ''] ?? club.finances.assessment.tier}
                </div>
              </div>
            </div>
            <table>
              <thead>
                <tr><th>Partida</th><th class="num">Importe</th><th>Por qué</th></tr>
              </thead>
              <tbody>
                {#each club.finances.assessment.components as component}
                  <tr>
                    <td class="small">
                      {component.label}
                      <span class={component.kind === 'revenue' ? 'tag accent' : 'tag'}>
                        {COMPONENT_LABEL[component.kind] ?? component.kind}
                      </span>
                      {#if component.mandatory}<span class="tag warn">obligatorio</span>{/if}
                    </td>
                    <td class="num">
                      {#if component.amount}
                        {formatMoney(component.amount, club.finances.currency ?? 'MXN')}
                      {:else}
                        <span class="muted">sin cifra</span>
                      {/if}
                    </td>
                    <td class="small muted">{component.basis}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
          {#each club.finances.assessment.risks as risk}
            <p class="small" style="color:var(--accent-2)">{risk}</p>
          {/each}
          {#each club.finances.assessment.notes as note}
            <p class="small muted">{note}</p>
          {/each}
          <p class="small muted">
            Confianza: {FINANCIAL_CONFIDENCE_LABEL[club.finances.assessment.confidence] ?? club.finances.assessment.confidence}.
            {#each club.finances.assessment.sources as source}<br />{source}{/each}
          </p>
        </div>
      {/if}

      {#if (club.season_ledgers ?? []).length}
        <div class="panel">
          <h2>Lo que de verdad cobró y pagó</h2>
          <p class="small muted" style="margin-top:0">
            El panel de arriba es la previsión de la temporada. Esto es la
            liquidación: un patrocinio prometido que no se cobró figura con lo
            que se esperaba al lado, y un partido que no se jugó no vendió
            entradas.
          </p>
          {#each club.season_ledgers as ledger (ledger.season)}
            <details open={ledger === club.season_ledgers[0]}>
              <summary>
                <strong>Temporada {ledger.season}</strong>
                <span class={ledger.outcome === 'healthy' ? 'tag accent' : 'tag warn'}>
                  {OUTCOME_LABEL[ledger.outcome] ?? ledger.outcome}
                </span>
                <span class="small muted">
                  {formatMoney(ledger.result, ledger.currency ?? 'MXN')} de resultado
                </span>
              </summary>
              {#if !ledger.currency}
                <div class="notice">
                  Sin datos económicos de esta jurisdicción no hay nada que
                  liquidar: la temporada se cierra sin cifras, a propósito.
                </div>
              {:else}
                <div class="grid three" style="margin:10px 0">
                  <div class="stat">
                    <div class="value">{formatMoney(ledger.collected, ledger.currency)}</div>
                    <div class="label">cobrado</div>
                  </div>
                  <div class="stat">
                    <div class="value">{formatMoney(ledger.paid, ledger.currency)}</div>
                    <div class="label">pagado</div>
                  </div>
                  <div class="stat">
                    <div class="value">{formatMoney(ledger.cash_end, ledger.currency)}</div>
                    <div class="label">caja al cierre · deuda {formatMoney(ledger.debt_end, ledger.currency)}</div>
                  </div>
                </div>
                <table>
                  <thead>
                    <tr><th>Partida</th><th class="num">Real</th><th class="num">Previsto</th><th>Por qué</th></tr>
                  </thead>
                  <tbody>
                    {#each ledger.entries as entry}
                      <tr>
                        <td class="small">
                          {entry.label}
                          <span class={entry.kind === 'revenue' ? 'tag accent' : 'tag'}>
                            {COMPONENT_LABEL[entry.kind] ?? entry.kind}
                          </span>
                        </td>
                        <td class="num">{formatMoney(entry.amount, ledger.currency)}</td>
                        <td class="num muted">
                          {#if entry.expected}{formatMoney(entry.expected, ledger.currency)}{:else}—{/if}
                        </td>
                        <td class="small muted">{entry.basis}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              {/if}
              {#each ledger.notes as note}
                <p class="small" style="color:var(--accent-2)">{note}</p>
              {/each}
            </details>
          {/each}
        </div>
      {/if}

      {#if (club.institutional_history ?? []).length}
        <div class="panel">
          <h2>Su historia institucional</h2>
          <p class="small muted" style="margin-top:0">
            Cada cambio con su causa. El club no se reinventa de una temporada a
            otra: se mueve despacio, y queda escrito por qué.
          </p>
          {#each club.institutional_history as change}
            <div class="small" style="padding:5px 0;border-bottom:1px solid var(--border)">
              <span class="tag">{change.season}</span>
              <strong>{CHANGE_FIELD_LABEL[change.field] ?? change.field}</strong>
              <span class="muted">{change.before} → {change.after}</span>
              <div class="muted">{change.reason}</div>
            </div>
          {/each}
        </div>
      {/if}

      <div class="panel">
        <h2>Reputación</h2>
        <table>
          <tbody>
            <tr><td>Local</td><td class="num">{club.reputation.local?.toFixed(2)}</td></tr>
            <tr><td>Nacional</td><td class="num">{club.reputation.national?.toFixed(2)}</td></tr>
            <tr><td>Internacional</td><td class="num">{club.reputation.international?.toFixed(2)}</td></tr>
          </tbody>
        </table>
      </div>

      <div class="panel">
        <h2>Competiciones</h2>
        {#each club.competitions as competition}
          <div class="small">
            {competition.name}
            <span class="tag">{competition.membership_kind}</span>
            {#if competition.start_season}
              <span class="tag">desde {competition.start_season}</span>
            {/if}
          </div>
        {/each}
        {#if (club.competition_history ?? []).some((item: any) => !item.current)}
          <h3 style="margin-top:12px">Categorías anteriores</h3>
          {#each club.competition_history.filter((item: any) => !item.current) as item}
            <div class="small muted">
              {item.name} · {item.start_season ?? '—'}–{item.end_season}
            </div>
          {/each}
        {/if}
        {#if (club.mobility ?? []).length}
          <h3 style="margin-top:12px">Ascensos y descensos</h3>
          {#each club.mobility as movement}
            <div class="small" style="padding:4px 0">
              <span class={movement.direction === 'promoted' ? 'tag accent' : 'tag warn'}>
                {movement.direction === 'promoted' ? 'ascenso' : 'descenso'}
              </span>
              temporada {movement.season}
              <div class="muted">{movement.reason}</div>
            </div>
          {/each}
          <p class="small muted">
            El club conserva su identidad, su estadio, su plantilla y sus deudas al
            cambiar de categoría: lo que cambia es su inscripción.
          </p>
        {/if}
        {#if club.titles.length}
          <h3 style="margin-top:12px">Títulos</h3>
          {#each club.titles as title}
            <div class="small">{title.year} · <a href={`/ediciones/${title.edition_id}`}>ver edición</a></div>
          {/each}
        {/if}
      </div>

      {#if club.provenance.length}
        <div class="panel">
          <h2>De dónde salen sus números</h2>
          {#each club.provenance as record}
            <div class="small muted mono">{record.procedure} · semilla {record.seed}</div>
            {#each record.notes as note}
              <div class="small" style="margin:6px 0">
                <strong>{note.field}</strong>
                <span class="tag" style="margin-left:4px">{CONFIDENCE_LABEL[note.confidence] ?? note.confidence}</span>
                <div class="muted">{note.derivation}</div>
              </div>
            {/each}
            {#each record.assumptions as assumption}
              <div class="small" style="color:var(--accent-2)">Supuesto: {assumption}</div>
            {/each}
          {/each}
        </div>
      {/if}
    </div>
  </div>
{:else if !error}
  <p class="muted">Cargando club…</p>
{/if}
