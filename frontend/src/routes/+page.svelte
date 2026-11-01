<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';
  import type { UniverseSummary } from '$lib/api/types';
  import { formatDate, formatNumber } from '$lib/format';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';
  import DatePicker from '$lib/components/DatePicker.svelte';

  let universes = $state<UniverseSummary[]>([]);
  let loading = $state(true);
  let error = $state<unknown>(null);
  let creating = $state(false);

  // Los datos de identidad los escribe el usuario. No precargamos ejemplos
  // que haya que seleccionar y borrar antes de empezar.
  let name = $state('');
  let worldDate = $state('');
  let seed = $state<string>('');
  const readableWorldDate = $derived(
    worldDate
      ? new Intl.DateTimeFormat('es-MX', {
          weekday: 'short', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'
        }).format(new Date(`${worldDate}T00:00:00Z`))
      : 'Ninguna fecha seleccionada'
  );

  function chooseToday() {
    const now = new Date();
    const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
    worldDate = local.toISOString().slice(0, 10);
  }

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
    if (!/^\d{4}-\d{2}-\d{2}$/.test(worldDate)) {
      error = new Error('Elige una fecha inicial válida en el calendario.');
      return;
    }
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
        <DatePicker bind:value={worldDate}/>
        <input id="fecha" class="date-value" value={worldDate} required aria-hidden="true" tabindex="-1" />
        <p class="chosen-date">{readableWorldDate}</p>
        <div class="date-actions">
          <button type="button" class="ghost" onclick={chooseToday}>Usar hoy</button>
          {#if worldDate}<button type="button" class="ghost" onclick={() => (worldDate = '')}>Limpiar</button>{/if}
        </div>
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

<style>
  .date-value{position:absolute;width:1px;height:1px;padding:0;opacity:0;pointer-events:none}.chosen-date{margin:6px 0 0;color:var(--muted);font-size:11px}.chosen-date::first-letter{text-transform:uppercase}
  .date-actions{display:flex;gap:6px;margin-top:6px}.date-actions button{padding:5px 9px;font-size:10px}
</style>
