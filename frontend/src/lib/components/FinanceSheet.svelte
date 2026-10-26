<script lang="ts">
  import { formatMoney } from '$lib/format';
  let { finances, ledgers = [] }: { finances:any; ledgers?:any[] } = $props();
  const currency = $derived(finances.currency ?? 'MXN');
  const assessment = $derived(finances.assessment);
  const revenues = $derived(assessment?.components?.filter((item:any)=>item.kind==='revenue') ?? []);
  const expenses = $derived(assessment?.components?.filter((item:any)=>item.kind==='expense') ?? []);
</script>
<section class="statement">
  <header class="statement-head"><div><span>Estado financiero proyectado</span><h2>Operación anual</h2></div><div class="currency">Moneda<br/><strong>{currency}</strong></div></header>
  <div class="balance-strip"><div><span>Caja</span><strong>{formatMoney(finances.cash,currency)}</strong></div><div><span>Deuda</span><strong class:negative={Number(finances.debt)>0}>{formatMoney(finances.debt,currency)}</strong></div><div><span>Presupuesto</span><strong>{formatMoney(finances.annual_budget,currency)}</strong></div></div>
  {#if assessment}
    <div class="ledger-columns">
      <div><h3>Ingresos</h3>{#each revenues as item}<div class="ledger-row"><span>{item.label}<small>{item.basis}</small></span><strong>{item.amount ? formatMoney(item.amount,currency) : '—'}</strong></div>{/each}<div class="ledger-total"><span>Total ingresos</span><strong>{formatMoney(assessment.revenue??0,currency)}</strong></div></div>
      <div><h3>Gastos</h3>{#each expenses as item}<div class="ledger-row"><span>{item.label}<small>{item.basis}</small></span><strong>{item.amount ? formatMoney(item.amount,currency) : '—'}</strong></div>{/each}<div class="ledger-total"><span>Total gastos</span><strong>{formatMoney(assessment.expenses??0,currency)}</strong></div></div>
    </div>
    <div class="net"><span>Resultado proyectado</span><strong>{formatMoney((Number(assessment.revenue??0)-Number(assessment.expenses??0)),currency)}</strong></div>
  {/if}
  {#if ledgers.length}<details><summary>Consultar cierres de temporadas anteriores</summary>{#each ledgers as ledger}<div class="past"><strong>Temporada {ledger.season}</strong><span>Cobrado {formatMoney(ledger.collected,ledger.currency??currency)}</span><span>Pagado {formatMoney(ledger.paid,ledger.currency??currency)}</span><strong>{formatMoney(ledger.result,ledger.currency??currency)}</strong></div>{/each}</details>{/if}
</section>
<style>
  .statement{background:#f5f1e8;color:#201b27;border-radius:10px;padding:22px;box-shadow:0 18px 45px rgba(0,0,0,.2)}.statement-head{display:flex;justify-content:space-between;align-items:start;border-bottom:2px solid #201b27;padding-bottom:12px}.statement-head span,.currency{font:700 9px var(--mono);text-transform:uppercase;letter-spacing:.12em;color:#6f6677}.statement-head h2{font:700 22px Georgia,serif;margin:3px 0 0}.currency{text-align:right}.balance-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding:14px 0;border-bottom:1px solid #cfc7bb}.balance-strip span,.balance-strip strong{display:block}.balance-strip span{font-size:9px;text-transform:uppercase;color:#766d7b}.balance-strip strong{font:700 15px var(--mono);margin-top:3px}.negative{color:#a02d45}.ledger-columns{display:grid;grid-template-columns:1fr 1fr;gap:30px;padding-top:20px}.ledger-columns h3{color:#201b27;border-bottom:1px solid #cfc7bb;padding-bottom:7px}.ledger-row,.ledger-total,.past{display:flex;justify-content:space-between;gap:18px;padding:8px 0;border-bottom:1px dotted #cfc7bb;font-size:11px}.ledger-row small{display:block;color:#7a7180;margin-top:2px;max-width:300px}.ledger-row strong,.ledger-total strong{font-family:var(--mono);white-space:nowrap}.ledger-total{border-top:1px solid #201b27;border-bottom:0;font-weight:800}.net{display:flex;justify-content:space-between;margin-top:20px;padding:12px;background:#e7dfcf;font:700 14px var(--mono)}details{margin-top:18px}summary{cursor:pointer;font-size:11px;font-weight:700}.past{display:grid;grid-template-columns:1fr repeat(3,auto)}@media(max-width:700px){.ledger-columns{grid-template-columns:1fr}.balance-strip{grid-template-columns:1fr}.past{grid-template-columns:1fr 1fr}}
</style>
