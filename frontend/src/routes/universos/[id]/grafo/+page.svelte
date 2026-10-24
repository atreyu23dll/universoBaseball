<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import { KIND_LABEL, SCOPE_LABEL } from '$lib/format';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';
  import type { MobilityRules, MobilityTransition } from '$lib/api/types';

  const universeId = $derived($page.params.id);
  let graph = $state<any>(null);
  let history = $state<MobilityTransition[]>([]);
  // Regla efectiva por competición superior: lo que ven las dos ligas.
  let rules = $state<Record<string, MobilityRules>>({});
  let error = $state<unknown>(null);
  let message = $state('');

  // Alta de relación entre dos competiciones que YA existen.
  let upperId = $state('');
  let lowerId = $state('');
  let slots = $state(2);
  let relationKind = $state('promotion_relegation');
  let editing = $state<string | null>(null);
  let editSlots = $state(2);
  let editFrom = $state<number | null>(null);

  async function load() {
    try {
      graph = await api.get<any>(`/universes/${universeId}/competition-graph`);
      history = (
        await api.get<{ items: MobilityTransition[] }>(`/universes/${universeId}/mobility-history`)
      ).items;
      // Solo las escaleras de ascenso tienen regla efectiva que consultar: un
      // vínculo filial no intercambia clubes y no tiene cuota.
      const uppers = [
        ...new Set(
          graph.hierarchy_edges
            .filter((e: any) => e.relation_kind === 'promotion_relegation')
            .map((e: any) => e.upper)
        )
      ] as string[];
      const loaded: Record<string, MobilityRules> = {};
      for (const id of uppers) {
        loaded[id] = await api.get<MobilityRules>(`/competitions/${id}/mobility`);
      }
      rules = loaded;
      error = null;
    } catch (err) {
      error = err;
    }
  }

  async function link(event: SubmitEvent) {
    event.preventDefault();
    message = '';
    try {
      const body: Record<string, unknown> = {
        target_competition_id: lowerId,
        relation_kind: relationKind
      };
      if (relationKind === 'promotion_relegation') body.exchange_slots = slots;
      const response = await api.post<{ warning: string }>(
        `/competitions/${upperId}/relationships`,
        body
      );
      message = response.warning;
      await load();
    } catch (err) {
      error = err;
    }
  }

  function startEdit(edge: any) {
    editing = edge.id;
    editSlots = edge.exchange_slots ?? 1;
    editFrom = edge.effective_from_season;
  }

  async function saveEdit(edgeId: string) {
    message = '';
    try {
      const response = await api.patch<{ warnings: string[] }>(`/relationships/${edgeId}`, {
        exchange_slots: editSlots,
        ...(editFrom ? { effective_from_season: editFrom } : {})
      });
      message = response.warnings.join(' ');
      editing = null;
      await load();
    } catch (err) {
      error = err;
    }
  }

  async function unlink(edgeId: string) {
    message = '';
    try {
      const response = await api.del<{ note: string }>(`/relationships/${edgeId}`);
      message = response.note;
      await load();
    } catch (err) {
      error = err;
    }
  }

  const nameOf = (id: string) => graph?.nodes.find((n: any) => n.id === id)?.name ?? id;
  const hierarchyEdges = $derived(
    (graph?.hierarchy_edges ?? []).filter((e: any) => e.relation_kind === 'promotion_relegation')
  );
  const developmentEdges = $derived(
    (graph?.hierarchy_edges ?? []).filter((e: any) => e.relation_kind !== 'promotion_relegation')
  );

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
                {#if node.active === false}<span class="tag">inactiva</span>{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h2>Vincular dos competiciones</h2>
      <p class="small muted">
        Solo entre competiciones que ya existen. En un ascenso y descenso las plazas
        se definen una vez, en la relación, y las dos ligas muestran la misma regla.
        Un vínculo filial o juvenil mueve jugadores, nunca clubes.
      </p>
      <form onsubmit={link}>
        <div class="field">
          <label for="tipo">Tipo de vínculo</label>
          <select id="tipo" bind:value={relationKind}>
            <option value="promotion_relegation">Ascenso y descenso</option>
            <option value="affiliate">Filial</option>
            <option value="youth">Juvenil</option>
            <option value="development">Desarrollo</option>
          </select>
        </div>
        <div class="field">
          <label for="superior">
            {relationKind === 'promotion_relegation' ? 'Competición superior' : 'Competición principal'}
          </label>
          <select id="superior" bind:value={upperId} required>
            <option value="">—</option>
            {#each graph.nodes as node (node.id)}<option value={node.id}>{node.name}</option>{/each}
          </select>
        </div>
        <div class="field">
          <label for="inferior">
            {relationKind === 'promotion_relegation' ? 'Competición inferior' : 'Competición vinculada'}
          </label>
          <select id="inferior" bind:value={lowerId} required>
            <option value="">—</option>
            {#each graph.nodes as node (node.id)}<option value={node.id}>{node.name}</option>{/each}
          </select>
        </div>
        {#if relationKind === 'promotion_relegation'}
          <div class="field">
            <label for="plazas">Plazas de intercambio (total de la superior)</label>
            <input id="plazas" type="number" min="1" max="12" bind:value={slots} />
            <p class="small muted">
              Es un total: con varias ligas alimentadoras se reparte entre ellas, no se
              multiplica por cada una.
            </p>
          </div>
        {/if}
        <button type="submit" disabled={!upperId || !lowerId}>Crear relación</button>
      </form>
    </div>
  </div>

  <div class="panel">
    <h3>Ascenso y descenso</h3>
    {#if hierarchyEdges.length === 0}
      <p class="small muted">
        Ninguna relación jerárquica. Las ligas son independientes y no intercambian clubes.
      </p>
    {:else}
      {#each hierarchyEdges as edge (edge.id)}
        <div class="row-block">
          <div class="spread">
            <div>
              <strong>{nameOf(edge.upper)}</strong> ↕ <strong>{nameOf(edge.lower)}</strong>
              <span class="tag accent">{edge.exchange_slots} plazas en total</span>
              {#if edge.branch_slots !== null && edge.branch_slots !== undefined}
                <span class="tag">{edge.branch_slots} desde esta rama</span>
              {/if}
              {#if edge.effective_from_season}
                <span class="tag">desde la temporada {edge.effective_from_season}</span>
              {/if}
              {#if edge.clubs_moved > 0}
                <span class="tag">{edge.clubs_moved} clubes movidos</span>
              {/if}
            </div>
            <div>
              <button class="ghost small" onclick={() => startEdit(edge)}>Editar plazas</button>
              <button class="ghost small" onclick={() => unlink(edge.id)}>Desvincular</button>
            </div>
          </div>

          {#if editing === edge.id}
            <div class="edit-row">
              <label for={`slots-${edge.id}`}>Plazas</label>
              <input id={`slots-${edge.id}`} type="number" min="1" max="12" bind:value={editSlots} />
              <label for={`from-${edge.id}`}>Desde la temporada</label>
              <input id={`from-${edge.id}`} type="number" min="1900" max="2999" bind:value={editFrom} />
              <button onclick={() => saveEdit(edge.id)}>Guardar</button>
              <button class="ghost" onclick={() => (editing = null)}>Cancelar</button>
            </div>
          {/if}

          {#if rules[edge.upper]?.has_hierarchy}
            <p class="small muted">{rules[edge.upper].note}</p>
            <table>
              <thead>
                <tr><th>Liga inferior</th><th>Plazas</th><th>Criterio de ascenso</th><th>Requisitos</th></tr>
              </thead>
              <tbody>
                {#each rules[edge.upper].branches ?? [] as branch (branch.relationship_id)}
                  <tr>
                    <td>{branch.name}</td>
                    <td>{branch.slots}</td>
                    <td class="small">{branch.lower_selection.method}</td>
                    <td class="small">
                      {#if branch.requirements.min_venue_capacity || branch.requirements.max_debt_to_budget}
                        {#if branch.requirements.min_venue_capacity}
                          aforo ≥ {branch.requirements.min_venue_capacity}
                        {/if}
                        {#if branch.requirements.max_debt_to_budget}
                          · deuda ≤ {branch.requirements.max_debt_to_budget}× presupuesto
                        {/if}
                        <span class="tag">{branch.on_requirement_failure}</span>
                      {:else}
                        <span class="muted">sin requisitos</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
            <p class="small muted">
              Criterio de descenso: {rules[edge.upper].upper_selection?.method}. Se aplica
              en {rules[edge.upper].apply_at === 'season_transition'
                ? 'el cierre de temporada, cuando todas las ligas vinculadas terminan'
                : rules[edge.upper].apply_at}.
            </p>
          {/if}
        </div>
      {/each}
    {/if}
  </div>

  <div class="grid two">
    <div class="panel">
      <h3>Vínculos de desarrollo (filial, juvenil)</h3>
      {#if developmentEdges.length === 0}
        <p class="small muted">Ninguno.</p>
      {:else}
        {#each developmentEdges as edge (edge.id)}
          <div class="small" style="padding:8px 0;border-bottom:1px solid var(--line)">
            {nameOf(edge.upper)} → {nameOf(edge.lower)} · {edge.relation_kind}
            <span class="tag">mueve jugadores, no clubes</span>
            <button class="ghost small" onclick={() => unlink(edge.id)}>Desvincular</button>
          </div>
        {/each}
      {/if}
    </div>
    <div class="panel">
      <h3>Rutas de clasificación (copas)</h3>
      {#if graph.qualification_edges.length === 0}
        <p class="small muted">Ninguna ruta de cupos definida.</p>
      {:else}
        {#each graph.qualification_edges as edge (edge.id)}
          <div class="small" style="padding:8px 0;border-bottom:1px solid var(--line)">
            {nameOf(edge.source)} → {nameOf(edge.target)} · {edge.slot_rule} ({edge.slots})
            <span class="tag">no crea jerarquía</span>
            <span class="tag warn">extracción de cupos: Etapa 3</span>
          </div>
        {/each}
      {/if}
    </div>
  </div>

  <div class="panel">
    <h3>Movimientos aplicados</h3>
    {#if history.length === 0}
      <p class="small muted">
        Todavía no se ha cerrado ninguna temporada con clubes en juego.
      </p>
    {:else}
      {#each history as transition (transition.id)}
        <div class="row-block">
          <strong>Temporada {transition.season}</strong> · {transition.upper.name}
          <span class="tag accent">{transition.promotions} ascensos</span>
          <span class="tag warn">{transition.relegations} descensos</span>
          <span class="small muted">aplicado el {transition.applied_on}</span>
          <table>
            <thead>
              <tr><th>Club</th><th>Movimiento</th><th>Destino</th><th>Motivo</th></tr>
            </thead>
            <tbody>
              {#each transition.plan.movements as movement (movement.club_id)}
                <tr>
                  <td><a href={`/clubes/${movement.club_id}`}>{movement.club_name}</a></td>
                  <td>
                    <span class={movement.direction === 'promoted' ? 'tag accent' : 'tag warn'}>
                      {movement.direction === 'promoted' ? 'asciende' : 'desciende'}
                    </span>
                  </td>
                  <td class="small">{nameOf(movement.to_competition_id)}</td>
                  <td class="small muted">{movement.reason}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#each transition.plan.rejected as rejected (rejected.club_id)}
            <p class="small warn-text">
              {rejected.club_name} no cumplió: {rejected.unmet.join('; ')} ({rejected.policy})
            </p>
          {/each}
          {#each transition.plan.notes as note}
            <p class="small muted">{note}</p>
          {/each}
        </div>
      {/each}
    {/if}
  </div>
{:else if !error}
  <p class="muted">Cargando grafo…</p>
{/if}

<style>
  .row-block {
    padding: 12px 0;
    border-bottom: 1px solid var(--line);
  }
  .row-block:last-child {
    border-bottom: 0;
  }
  .edit-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    margin: 10px 0;
  }
  .edit-row input {
    width: 7rem;
  }
  .warn-text {
    color: var(--warn, #b45309);
  }
  button.small {
    padding: 2px 8px;
    font-size: 0.85em;
  }
</style>
