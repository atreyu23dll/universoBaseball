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

<div class="hero">
  <div class="kicker">Tus mundos deportivos</div>
  <h1>El béisbol no tiene<br />un solo universo.</h1>
  <p>Cada mundo tiene su propio calendario, geografía y legado. Entra a uno para seguir sus ligas o crea una nueva historia desde cero.</p>
</div>

<ErrorNotice {error} />

<div class="section-title">
  <div><h2>Universos guardados</h2><p class="small">Selecciona un universo para explorar sus ligas.</p></div>
</div>

<div class="card-grid">
    {#if loading}
      {#each Array(3) as _}<div class="entity-card" style="opacity:.45"><div class="icon-box">◈</div><h2>Cargando…</h2></div>{/each}
    {:else if universes.length === 0}
      <div class="empty-state">Todavía no hay universos. Crea el primero para comenzar.</div>
    {:else}
      {#each universes as universe (universe.id)}
        <a class="entity-card" href={`/universos/${universe.id}`}>
          <div class="spread"><div class="icon-box">◈</div>{#if universe.busy}<span class="tag warn">En simulación</span>{/if}</div>
          <h2>{universe.name}</h2>
          <div class="small muted">Temporada en {formatDate(universe.world_date)} · semilla <span class="mono">{universe.master_seed}</span></div>
          <div class="card-meta">
            <div><strong>{universe.competitions}</strong><span>Ligas</span></div>
            <div><strong>{formatNumber(universe.clubs)}</strong><span>Clubes</span></div>
            <div><strong>{formatNumber(universe.games_played)}</strong><span>Partidos</span></div>
          </div>
          <button class="danger small" style="position:absolute;right:16px;bottom:16px;z-index:2" onclick={(event) => { event.preventDefault(); remove(universe); }}>Borrar</button>
        </a>
      {/each}
    {/if}
  <div class="entity-card action-card">
    <div class="icon-box">＋</div><h2>Nuevo universo</h2>
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
    </form>
  </div>
</div>
