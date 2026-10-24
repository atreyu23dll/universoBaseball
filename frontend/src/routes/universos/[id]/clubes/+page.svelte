<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import { formatMoney, formatNumber, INSTITUTION_LABEL, VENUE_LABEL } from '$lib/format';
  import ConfidenceTag from '$lib/components/ConfidenceTag.svelte';
  import Crest from '$lib/components/Crest.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const universeId = $derived($page.params.id);
  let clubs = $state<any[]>([]);
  let error = $state<unknown>(null);
  let query = $state('');

  const filtered = $derived(
    clubs.filter((club) => club.name.toLowerCase().includes(query.toLowerCase()))
  );

  onMount(async () => {
    try {
      const response = await api.get<{ items: any[] }>(`/universes/${universeId}/clubs`);
      clubs = response.items;
    } catch (err) {
      error = err;
    }
  });
</script>

<div class="spread" style="margin-bottom:14px">
  <h1>Clubes</h1>
  <a class="button ghost" href={`/universos/${universeId}`}>Volver al panel</a>
</div>

<ErrorNotice {error} />

<div class="panel">
  <div class="field" style="max-width:360px">
    <label for="buscar">Buscar</label>
    <input id="buscar" bind:value={query} placeholder="nombre del club" />
  </div>
  <table>
    <thead>
      <tr>
        <th>Club</th><th>Compite en</th><th>Institución</th><th>Zona</th>
        <th class="num">Presupuesto</th><th class="num">Recursos</th>
        <th>Instalación</th><th class="num">Aforo</th><th class="num">Afición</th>
      </tr>
    </thead>
    <tbody>
      {#each filtered as club (club.id)}
        <tr>
          <td>
            <span class="row" style="gap:8px">
              <Crest primary={club.primary_color} secondary={club.secondary_color}
                     shape={club.crest_shape} motif={club.crest_motif} size={20} />
              <a href={`/clubes/${club.id}`}>{club.name}</a>
            </span>
          </td>
          <td class="small">
            {#if club.competition_name}{club.competition_name}{:else}<span class="muted">sin competición</span>{/if}
          </td>
          <td class="small">{INSTITUTION_LABEL[club.institutional_type] ?? club.institutional_type}</td>
          <td class="small">
            {club.home_place}
            {#if club.home_place_confidence}<ConfidenceTag confidence={club.home_place_confidence} />{/if}
          </td>
          <td class="num">{formatMoney(club.annual_budget, club.currency)}</td>
          <td class="num">{club.resource_multiplier.toFixed(2)}×</td>
          <td class="small">{club.venue?.name} <span class="muted">({VENUE_LABEL[club.venue?.type] ?? club.venue?.type})</span></td>
          <td class="num">{formatNumber(club.venue?.capacity)}</td>
          <td class="num">{formatNumber(club.fan_base)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  <p class="small muted">
    La columna de recursos es el multiplicador de desigualdad que la generación
    asignó a cada club. Importa, pero no decide: influye en el orden del draft,
    no en el resultado.
  </p>
</div>
