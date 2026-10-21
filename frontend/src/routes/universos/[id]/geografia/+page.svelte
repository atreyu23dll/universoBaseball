<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import type { Place } from '$lib/api/types';
  import { formatNumber } from '$lib/format';
  import ConfidenceTag from '$lib/components/ConfidenceTag.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const universeId = $derived($page.params.id);
  let places = $state<Place[]>([]);
  let note = $state('');
  let error = $state<unknown>(null);

  onMount(async () => {
    try {
      const response = await api.get<{ items: Place[]; note: string }>(
        `/universes/${universeId}/geography`
      );
      places = response.items;
      note = response.note;
    } catch (err) {
      error = err;
    }
  });

  const KIND_LABEL: Record<string, string> = {
    country: 'país',
    region: 'estado o región',
    city: 'ciudad',
    district: 'subzona'
  };
</script>

<div class="spread" style="margin-bottom:14px">
  <h1>Geografía del universo</h1>
  <a class="button ghost" href={`/universos/${universeId}`}>Volver al panel</a>
</div>

<ErrorNotice {error} />

<div class="notice info">
  {note}
  <br />
  Todavía no hay mapa cartográfico: la geografía se consulta como lista. Es una
  limitación conocida, no un dato que falte.
</div>

<div class="panel">
  <table>
    <thead>
      <tr>
        <th>Lugar</th><th>Tipo</th><th>Pertenece a</th>
        <th class="num">Población</th><th class="num">Año</th>
        <th class="num">Economía</th><th class="num">Cultura</th>
        <th class="num">Infraestructura</th><th class="num">Clubes</th><th>Procedencia</th>
      </tr>
    </thead>
    <tbody>
      {#each places as place (place.key)}
        <tr>
          <td>
            {place.name}
            <div class="small muted mono">{place.key} · {place.lat.toFixed(3)}, {place.lon.toFixed(3)}</div>
          </td>
          <td class="small">{KIND_LABEL[place.kind] ?? place.kind}</td>
          <td class="small muted mono">{place.parent_key ?? '—'}</td>
          <td class="num">{place.profile ? formatNumber(place.profile.population) : '—'}</td>
          <td class="num small">{place.profile?.ref_year ?? '—'}</td>
          <td class="num">{place.profile?.economy_index.toFixed(2) ?? '—'}</td>
          <td class="num">{place.profile?.baseball_culture_index.toFixed(2) ?? '—'}</td>
          <td class="num">{place.profile?.infrastructure_index.toFixed(2) ?? '—'}</td>
          <td class="num">{place.clubs}</td>
          <td>
            <ConfidenceTag confidence={place.confidence} sources={place.sources} />
            {#if place.profile && place.profile.confidence !== place.confidence}
              <ConfidenceTag confidence={place.profile.confidence} sources={place.profile.sources} />
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
