<script lang="ts">
  let { chart }: { chart: any } = $props();
  const roots = $derived(chart?.units?.filter((unit:any) => !unit.parent_id) ?? []);
  function childrenOf(id:string) { return chart?.units?.filter((unit:any) => unit.parent_id === id) ?? []; }
</script>

{#if roots.length}
  <div class="org-chart">
    {#each roots as root}
      <section class="org-root">
        <div class="org-node primary"><span>Dirección institucional</span><strong>{root.name}</strong></div>
        {#each root.positions ?? [] as position}<div class="position-line"><span>{position.title}</span><strong>{position.occupants?.[0]?.name ?? 'Vacante'}</strong></div>{/each}
        <div class="branches">
          {#each childrenOf(root.id) as unit}
            <article class="branch">
              <div class="org-node"><span>{unit.family_label ?? 'Unidad'}</span><strong>{unit.name}</strong></div>
              {#each unit.positions ?? [] as position}
                <div class="position-card"><div><strong>{position.title}</strong>{#if position.shared}<span class="tag">compartido</span>{/if}</div>{#if position.occupants?.length}{#each position.occupants as person}<a href={`/personas/${person.person_id}`}>{person.name}</a>{/each}{:else}<span class="vacant">Puesto vacante</span>{/if}</div>
              {/each}
            </article>
          {/each}
        </div>
      </section>
    {/each}
  </div>
{:else}<div class="empty-state">El club todavía no tiene un organigrama registrado.</div>{/if}

<style>
  .org-chart{overflow-x:auto;padding:4px 0 18px}.org-root{min-width:650px;text-align:center}.org-node{display:inline-flex;flex-direction:column;gap:2px;min-width:190px;padding:11px 16px;background:var(--panel-2);border:1px solid var(--line);border-radius:10px}.org-node.primary{border-color:var(--accent);box-shadow:0 0 0 3px rgba(155,108,255,.08)}.org-node span{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.1em}.position-line{display:inline-flex;gap:8px;margin:8px 4px 0;padding:6px 9px;background:var(--panel);border-radius:7px;font-size:11px}.position-line span{color:var(--muted)}.branches{position:relative;display:flex;justify-content:center;align-items:flex-start;gap:12px;padding-top:30px}.branches:before{content:'';position:absolute;top:14px;left:15%;right:15%;height:1px;background:var(--line)}.branch{position:relative;flex:1;max-width:280px}.branch:before{content:'';position:absolute;top:-16px;left:50%;height:16px;border-left:1px solid var(--line)}.position-card{display:flex;flex-direction:column;gap:3px;text-align:left;margin-top:7px;padding:9px;background:var(--panel);border:1px solid var(--line);border-radius:8px;font-size:11px}.position-card>div{display:flex;justify-content:space-between;gap:5px}.position-card a{font-size:11px}.vacant{color:var(--danger);font-size:10px}
</style>
