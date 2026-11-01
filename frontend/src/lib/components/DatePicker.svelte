<script lang="ts">
  interface Props { value?: string }
  let { value = $bindable('') }: Props = $props();

  const MONTHS = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const WEEKDAYS = ['L','M','X','J','V','S','D'];
  const today = new Date();
  let viewYear = $state(today.getFullYear());
  let viewMonth = $state(today.getMonth());

  $effect(() => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return;
    const [year, month] = value.split('-').map(Number);
    viewYear = year;
    viewMonth = month - 1;
  });

  const selectedDay = $derived(/^\d{4}-\d{2}-\d{2}$/.test(value) ? Number(value.slice(8, 10)) : null);
  const leading = $derived((new Date(Date.UTC(viewYear, viewMonth, 1)).getUTCDay() + 6) % 7);
  const daysInMonth = $derived(new Date(Date.UTC(viewYear, viewMonth + 1, 0)).getUTCDate());
  const cells = $derived([...Array(leading).fill(null), ...Array.from({length:daysInMonth},(_,i)=>i+1)]);

  function selectDay(day:number) {
    const month=String(viewMonth+1).padStart(2,'0');
    value=`${String(viewYear).padStart(4,'0')}-${month}-${String(day).padStart(2,'0')}`;
  }

  function moveMonth(delta:number) {
    const next=new Date(Date.UTC(viewYear,viewMonth+delta,1));
    viewYear=next.getUTCFullYear(); viewMonth=next.getUTCMonth();
  }

  function setYear(event:Event) {
    const year=Number((event.currentTarget as HTMLInputElement).value);
    if (Number.isInteger(year) && year>=1900 && year<=2999) viewYear=year;
  }
</script>

<div class="date-picker" aria-label="Selector de fecha">
  <div class="calendar-head">
    <button type="button" class="nav" onclick={()=>moveMonth(-1)} aria-label="Mes anterior">‹</button>
    <select aria-label="Mes" bind:value={viewMonth}>
      {#each MONTHS as month,index}<option value={index}>{month}</option>{/each}
    </select>
    <label class="year"><span>Año</span><input aria-label="Año" type="number" min="1900" max="2999" value={viewYear} oninput={setYear}/></label>
    <button type="button" class="nav" onclick={()=>moveMonth(1)} aria-label="Mes siguiente">›</button>
  </div>
  <div class="weekdays">{#each WEEKDAYS as day}<span>{day}</span>{/each}</div>
  <div class="days">
    {#each cells as day}
      {#if day===null}<span></span>{:else}<button type="button" class:selected={selectedDay===day && Number(value.slice(0,4))===viewYear && Number(value.slice(5,7))===viewMonth+1} onclick={()=>selectDay(day)}>{day}</button>{/if}
    {/each}
  </div>
</div>

<style>
  .date-picker{padding:10px;border:1px solid var(--line);border-radius:12px;background:linear-gradient(145deg,var(--panel-2),var(--panel-3))}.calendar-head{display:grid;grid-template-columns:34px 1fr 92px 34px;gap:6px;align-items:end}.calendar-head select,.calendar-head input{height:34px;padding:5px 8px;border-radius:8px}.nav{height:34px;padding:0;font-size:22px}.year{margin:0}.year span{display:block;font-size:9px;line-height:10px}.weekdays,.days{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}.weekdays{margin:10px 0 4px}.weekdays span{text-align:center;color:var(--muted);font:9px var(--mono)}.days button,.days span{aspect-ratio:1;min-width:0}.days button{display:grid;place-items:center;padding:0;color:var(--text);border:1px solid transparent;border-radius:8px;background:transparent;font-size:11px}.days button:hover{transform:none;border-color:var(--accent);background:var(--accent-soft);box-shadow:none}.days button.selected{color:#171020;background:var(--accent-2);font-weight:900}
</style>
