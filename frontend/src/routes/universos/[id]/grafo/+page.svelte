<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import { KIND_LABEL, SCOPE_LABEL } from '$lib/format';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const universeId = $derived($page.params.id);
  let graph = $state<any>(null);
  let error = $state<unknown>(null);

  // Alta de relación jerárquica entre dos competiciones que YA existen.
  let upperId = $state('');
  let lowerId = $state('');
  let slots = $state(2);
  let message = $state('');

  async function load() {
    try {
      graph = await api.get<any>(`/universes/${universeId}/competition-graph`);
      error = null;
    } catch (err) {
      error = err;
    }
  }

  async function link(event: SubmitEvent) {
    event.preventDefault();
    message = '';
    try {
      const response = await api.post<{ warning: string }>(
        `/competitions/${upperId}/relationships`,
        {
          target_competition_id: lowerId,
          relation_kind: 'promotion_relegation',
          exchange_slots: slots,
          lower_selection: { method: 'top_standings', count: slots },
          upper_selection: { method: 'bottom_standings', count: slots }
        }
      );
      message = response.warning;
      await load();
    } catch (err) {
      error = err;
    }
  }

  const nameOf = (id: string) => graph?.nodes.find((n: any) => n.id === id)?.name ?? id;

  onMount(load);
</script>

<div class="spread" style="margin-bottom:14px">
  <h1>Grafo de competiciones</h1>
  <a class="button ghost" href={`/universos/${universeId}`}>Volver al panel</a>
</div>

<ErrorNotice {error} />
{#if message}<div class="notice">{message}</div>{/if}

{#if graph}
  <div class="notice info">{graph.note}</div>

  <div class="grid two">
    <div class="panel">
      <h2>Competiciones</h2>
      <table>
        <thead><tr><th>Nombre</th><th>Tipo</th><th>Alcance</th><th>Relación</th></tr></thead>
        <tbody>
          {#each graph.nodes as node (node.id)}
            <tr>
              <td>{node.name}</td>
              <td class="small">{KIND_LABEL[node.kind] ?? node.kind}</td>
              <td class="small">{SCOPE_LABEL[node.scope_level] ?? node.scope_level}</td>
              <td>
                <span class={node.independent ? 'tag accent' : 'tag warn'}>
                  {node.independent ? 'independiente' : 'dependiente'}
                </span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h2>Vincular ascenso y descenso</h2>
      <p class="small muted">
        Solo entre competiciones que ya existen. Las plazas se definen una vez,
        en la relación, y las dos ligas muestran la misma regla.
      </p>
      <form onsubmit={link}>
        <div class="field">
          <label for="superior">Competición superior</label>
          <select id="superior" bind:value={upperId} required>
            <option value="">—</option>
            {#each graph.nodes as node (node.id)}<option value={node.id}>{node.name}</option>{/each}
          </select>
        </div>
        <div class="field">
          <label for="inferior">Competición inferior</label>
          <select id="inferior" bind:value={lowerId} required>
            <option value="">—</option>
            {#each graph.nodes as node (node.id)}<option value={node.id}>{node.name}</option>{/each}
          </select>
        </div>
        <div class="field">
          <label for="plazas">Plazas de intercambio</label>
          <input id="plazas" type="number" min="1" max="12" bind:value={slots} />
        </div>
        <button type="submit" disabled={!upperId || !lowerId}>Crear relación</button>
      </form>
    </div>
  </div>

  <div class="grid two">
    <div class="panel">
      <h3>Aristas jerárquicas (ascenso y descenso)</h3>
      {#if graph.hierarchy_edges.length === 0}
        <p class="small muted">Ninguna. Las ligas son independientes.</p>
      {:else}
        {#each graph.hierarchy_edges as edge (edge.id)}
          <div class="small" style="padding:8px 0;border-bottom:1px solid var(--line)">
            <strong>{nameOf(edge.upper)}</strong> ↕ <strong>{nameOf(edge.lower)}</strong>
            · {edge.exchange_slots} plazas
            <span class="tag warn">motor no implementado</span>
          </div>
        {/each}
      {/if}
    </div>
    <div class="panel">
      <h3>Aristas de clasificación (copas)</h3>
      {#if graph.qualification_edges.length === 0}
        <p class="small muted">Ninguna ruta de cupos definida.</p>
      {:else}
        {#each graph.qualification_edges as edge (edge.id)}
          <div class="small" style="padding:8px 0;border-bottom:1px solid var(--line)">
            {nameOf(edge.source)} → {nameOf(edge.target)} · {edge.slot_rule} ({edge.slots})
            <span class="tag">no crea jerarquía</span>
          </div>
        {/each}
      {/if}
    </div>
  </div>
{:else if !error}
  <p class="muted">Cargando grafo…</p>
{/if}
