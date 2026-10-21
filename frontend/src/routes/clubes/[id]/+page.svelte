<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import { CONFIDENCE_LABEL, formatMoney, formatNumber, INSTITUTION_LABEL, VENUE_LABEL } from '$lib/format';
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
          <div class="small">{competition.name} <span class="tag">{competition.membership_kind}</span></div>
        {/each}
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
