<!--
  Un número del reglamento mostrado como una decisión, no como una caja de
  formulario. Mantiene el valor numérico que espera la API, pero permite verlo
  y cambiarlo con botones grandes, utilizables tanto con ratón como teclado.
-->
<script lang="ts">
  interface Props {
    label: string;
    value?: number;
    min?: number;
    max?: number;
    step?: number;
    prefix?: string;
    suffix?: string;
    help?: string;
  }

  let {
    label,
    value = $bindable(0),
    min = Number.NEGATIVE_INFINITY,
    max = Number.POSITIVE_INFINITY,
    step = 1,
    prefix = '',
    suffix = '',
    help = ''
  }: Props = $props();

  function change(delta: number) {
    value = Math.min(max, Math.max(min, value + delta));
  }

  function display(value: number) {
    return value.toLocaleString('es-MX');
  }
</script>

<div class="adjuster">
  <div class="adjuster-copy">
    <span class="small muted">{label}</span>
    {#if help}<span class="adjuster-help small muted">{help}</span>{/if}
  </div>
  <div class="adjuster-controls" role="group" aria-label={label}>
    <button
      type="button"
      class="button ghost adjuster-button"
      onclick={() => change(-step)}
      disabled={value <= min}
      aria-label={`Reducir ${label}`}
    >−</button>
    <output class="adjuster-value" aria-live="polite">{prefix}{display(value)}{suffix}</output>
    <button
      type="button"
      class="button ghost adjuster-button"
      onclick={() => change(step)}
      disabled={value >= max}
      aria-label={`Aumentar ${label}`}
    >+</button>
  </div>
</div>

<style>
  .adjuster {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 9px 10px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--panel-2);
  }
  .adjuster-copy {
    min-width: 0;
    display: grid;
    gap: 2px;
  }
  .adjuster-help {
    line-height: 1.25;
  }
  .adjuster-controls {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: none;
  }
  .adjuster-button {
    width: 32px;
    height: 32px;
    padding: 0;
    font-size: 18px;
    line-height: 1;
  }
  .adjuster-value {
    min-width: 52px;
    padding: 4px 2px;
    font-family: var(--mono);
    font-weight: 700;
    font-size: 0.9rem;
    text-align: center;
    color: var(--accent);
  }
  @media (max-width: 520px) {
    .adjuster { align-items: flex-start; flex-direction: column; }
    .adjuster-controls { width: 100%; justify-content: flex-end; }
  }
</style>
