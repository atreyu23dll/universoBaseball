<script lang="ts">
  let { date, busy = false, job = null, onadvance }: { date:string; busy?:boolean; job?:any; onadvance:(days:number,untilSeasonEnd?:boolean)=>void } = $props();
  const parsed=$derived(new Date(`${date}T12:00:00`));
  const weekday=$derived(new Intl.DateTimeFormat('es-MX',{weekday:'long'}).format(parsed));
  const day=$derived(new Intl.DateTimeFormat('es-MX',{day:'2-digit'}).format(parsed));
  const month=$derived(new Intl.DateTimeFormat('es-MX',{month:'long'}).format(parsed));
  const year=$derived(new Intl.DateTimeFormat('es-MX',{year:'numeric'}).format(parsed));
  const progress=$derived(job?.progress?.days_requested ? Math.min((job.progress.days_done/job.progress.days_requested)*100,100) : 0);
</script>

<section class="world-clock">
  <div class="date-block"><span class="current">Fecha actual del universo</span><div class="date"><strong>{day}</strong><div><span>{month}</span><b>{year}</b></div></div><div class="weekday">{weekday}</div></div>
  <div class="time-controls"><span class="control-label">Mover el tiempo</span><div class="time-grid"><button onclick={()=>onadvance(1)} disabled={busy}><strong>+1</strong><span>día</span></button><button onclick={()=>onadvance(7)} disabled={busy}><strong>+7</strong><span>días</span></button><button onclick={()=>onadvance(30)} disabled={busy}><strong>+30</strong><span>días</span></button><button class="season" onclick={()=>onadvance(1,true)} disabled={busy}><strong>↦</strong><span>Fin de temporada</span></button></div>
    {#if busy||job?.status==='running'}<div class="simulation"><div class="spread"><span>Simulando el mundo…</span><strong>{job?.progress?.days_done??0}/{job?.progress?.days_requested??'—'} días</strong></div><div class="progress"><i style={`width:${progress}%`}></i></div><small>{job?.progress?.games_played??0} partidos procesados. Puedes cerrar esta pestaña.</small></div>{/if}
  </div>
</section>

<style>
  .world-clock{display:grid;grid-template-columns:230px 1fr;gap:20px;padding:18px;background:linear-gradient(135deg,var(--panel-2),var(--panel));border:1px solid var(--line);border-radius:12px}.date-block{padding-right:20px;border-right:1px solid var(--line)}.current,.control-label{display:block;color:var(--accent-2);font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.12em}.date{display:flex;align-items:center;gap:10px;margin:5px 0 0}.date>strong{font:800 45px/1 var(--mono);letter-spacing:-.07em}.date div span,.date div b{display:block;text-transform:capitalize}.date div span{font-weight:700;font-size:16px}.date div b{color:var(--muted);font-size:12px}.weekday{color:var(--muted);font-size:11px;text-transform:capitalize;margin-top:3px}.time-grid{display:grid;grid-template-columns:repeat(3,minmax(75px,1fr)) minmax(145px,1.5fr);gap:7px;margin-top:8px}.time-grid button{display:flex;align-items:baseline;justify-content:center;gap:5px;background:var(--panel-3);border:1px solid var(--line);box-shadow:none}.time-grid button:hover{border-color:var(--accent);box-shadow:none}.time-grid button strong{font:800 15px var(--mono)}.time-grid button span{font-size:10px}.time-grid .season{background:var(--accent-soft)}.simulation{margin-top:12px;font-size:10px;color:var(--muted)}.progress{height:4px;margin:6px 0;background:var(--panel-3);border-radius:4px;overflow:hidden}.progress i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-2));transition:width .3s ease}@media(max-width:700px){.world-clock{grid-template-columns:1fr}.date-block{border-right:0;border-bottom:1px solid var(--line);padding:0 0 12px}.time-grid{grid-template-columns:repeat(3,1fr)}.time-grid .season{grid-column:1/-1}}
</style>
