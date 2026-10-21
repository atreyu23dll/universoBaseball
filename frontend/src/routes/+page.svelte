<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';
  import type { UniverseSummary } from '$lib/api/types';
  import { formatDate, formatNumber } from '$lib/format';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  let universes = $state<UniverseSummary[]>([]);
  let loading = $state(true);
  let error = $state<unknown>(null);
  let creating = $state(false);

  let name = $state('México Alternativo');
  let worldDate = $state('2042-03-20');
  let seed = $state<string>('18723');

  async function load() {
    loading = true;
    try {
      const page = await api.get<{ items: UniverseSummary[] }>('/universes');
      universes = page.items;
      error = null;
    } catch (err) {
      error = err;
    } finally {
      loading = false;
    }
  }

  async function create(event: SubmitEvent) {
    event.preventDefault();
    creating = true;
    error = null;
    try {
      const created = await api.post<{ id: string }>('/universes', {
        name,
        world_date: worldDate,
        master_seed: seed.trim() === '' ? null : Number(seed)
      });
      window.location.href = `/universos/${created.id}`;
    } catch (err) {
      error = err;
    } finally {
      creating = false;
    }
  }

  async function remove(universe: UniverseSummary) {
    if (!confirm(`¿Borrar «${universe.name}» y todo su contenido? No se puede deshacer.`)) return;
    try {
      await api.del(`/universes/${universe.id}`);
      await load();
    } catch (err) {
      error = err;
    }
  }

  onMount(load);
</script>

<div class="spread" style="margin-bottom:18px">
  <div>
    <h1>Universos</h1>
    <p class="muted" style="margin:0">
      Cada universo es una partida aislada con su propia semilla, su fecha y su geografía.
    </p>
  </div>
</div>

<ErrorNotice {error} />

<div class="grid sidebar">
  <div class="panel">
    <h2>Universos guardados</h2>
    {#if loading}
      <p class="muted">Cargando…</p>
    {:else if universes.length === 0}
      <p class="muted">
        Todavía no hay ninguno. Crea el primero con el formulario de la derecha.
      </p>
    {:else}
      <table>
        <thead>
          <tr>
            <th>Universo</th>
            <th>Fecha del mundo</th>
            <th class="num">Competiciones</th>
            <th class="num">Clubes</th>
            <th class="num">Personas</th>
            <th class="num">Partidos</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each universes as universe (universe.id)}
            <tr>
              <td>
                <a href={`/universos/${universe.id}`}>{universe.name}</a>
                {#if universe.busy}<span class="tag warn">simulando</span>{/if}
                <div class="small muted mono">semilla {universe.master_seed}</div>
              </td>
              <td>{formatDate(universe.world_date)}</td>
              <td class="num">{universe.competitions}</td>
              <td class="num">{formatNumber(universe.clubs)}</td>
              <td class="num">{formatNumber(universe.people)}</td>
              <td class="num">{formatNumber(universe.games_played)}</td>
              <td style="text-align:right">
                <button class="danger small" onclick={() => remove(universe)}>Borrar</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  <div class="panel">
    <h2>Nuevo universo</h2>
    <form onsubmit={create}>
      <div class="field">
        <label for="nombre">Nombre</label>
        <input id="nombre" bind:value={name} required minlength="2" />
      </div>
      <div class="field">
        <label for="fecha">Fecha inicial del mundo</label>
        <input id="fecha" type="date" bind:value={worldDate} required />
      </div>
      <div class="field">
        <label for="semilla">Semilla maestra (vacío = aleatoria)</label>
        <input id="semilla" bind:value={seed} inputmode="numeric" />
      </div>
      <button type="submit" disabled={creating}>
        {creating ? 'Creando…' : 'Crear universo'}
      </button>
      <p class="small muted" style="margin-top:12px">
        La misma semilla con las mismas reglas produce el mismo mundo. No se crea
        ninguna liga: eso lo decides después.
      </p>
    </form>
  </div>
</div>
