<!--
  El cuadro de postemporada tal como quedaría, con la ruta de cada clasificado.

  «Dos clasificados por división más dos repechajes» son cuatro números sueltos
  en un formulario y un cuadro de seis plazas con dos pases directos en la
  realidad. Esto dibuja lo segundo: de dónde sale cada siembra, quién espera en
  la segunda ronda y cuántas series tiene cada una.

  Las siembras son posiciones, no clubes: en este paso nadie ha jugado todavía.
-->
<script lang="ts">
  import type { BracketPreview } from '$lib/api/types';

  interface Props {
    bracket: BracketPreview | null;
  }
  const { bracket }: Props = $props();

  const ROUTE_LABEL: Record<string, string> = {
    group_winner: 'por división',
    wildcard: 'repechaje',
    overall: 'por la tabla'
  };
</script>

{#if bracket}
  {#key bracket}
  <div class="panel">
    <div class="spread">
      <h3 style="margin:0">Postemporada</h3>
      {#if bracket.slots}
        <span class="tag accent">{bracket.slots} plazas</span>
      {/if}
    </div>
    <p class="small muted" style="margin:6px 0 10px">{bracket.note}</p>

    {#if bracket.qualifiers.length}
      <h4>Quién clasifica</h4>
      <div class="clasificados">
        {#each bracket.qualifiers as q (q.seed)}
          <div class="clasificado" class:repechaje={q.route === 'wildcard'}>
            <span class="siembra mono">{q.seed}</span>
            <span class="small">
              {q.label}
              <span class="muted">· {ROUTE_LABEL[q.route] ?? q.route}</span>
            </span>
          </div>
        {/each}
      </div>
      <p class="small muted">
        <span class="muestra division"></span> campeones y segundos de su división
        ·
        <span class="muestra repechaje"></span> repechajes, que salen de la tabla
        general entre los que no clasificaron por su grupo. La siembra conserva
        el orden de la tabla general, salvo las entradas que hayas colocado a
        mano en una ronda posterior.
      </p>
    {/if}

    {#if bracket.rounds.length}
      <h4>El cuadro</h4>
      <div class="cuadro">
        {#each bracket.rounds as ronda (ronda.round)}
          <div class="ronda">
            <div class="small muted cabecera">
              {ronda.label || `Ronda ${ronda.round}`} · al mejor de {ronda.best_of}
            </div>
            {#each ronda.byes as bye}
              <div class="serie bye small">
                <strong>{bye}</strong>
                <div class="muted">pase directo: espera aquí</div>
              </div>
            {/each}
            {#each ronda.series as serie, i (i)}
              <div class="serie small">
                <div>{serie.high}</div>
                <div class="muted vs">contra</div>
                <div>{serie.low}</div>
              </div>
            {/each}
          </div>
        {/each}
      </div>
      {#if bracket.byes}
        <p class="small muted">
          {bracket.byes} entrada(s) comienza(n) después de la primera ronda, según
          los pases del cuadro.
        </p>
      {/if}
    {/if}
  </div>
  {/key}
{/if}

<style>
  h4 {
    margin: 16px 0 8px;
    font-size: 0.95rem;
  }
  .muestra {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 2px;
    vertical-align: -1px;
  }
  .muestra.division {
    background: var(--accent);
  }
  .muestra.repechaje {
    background: var(--accent-2);
  }
  .clasificados {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    gap: 6px;
    margin-bottom: 8px;
  }
  .clasificado {
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 6px 8px;
    border-radius: 6px;
    background: var(--panel-2);
    border-left: 3px solid var(--accent);
    animation: entrant-arrives 280ms ease-out both;
  }
  .clasificado:nth-child(2) { animation-delay: 45ms; }
  .clasificado:nth-child(3) { animation-delay: 90ms; }
  .clasificado:nth-child(4) { animation-delay: 135ms; }
  .clasificado.repechaje {
    border-left-color: var(--accent-2);
  }
  .siembra {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--panel);
    border: 1px solid var(--line);
    flex: none;
  }
  .cuadro {
    display: flex;
    gap: 14px;
    overflow-x: auto;
    align-items: flex-start;
  }
  .ronda {
    position: relative;
    min-width: 170px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    animation: round-arrives 320ms ease-out both;
  }
  .ronda:nth-child(2) { animation-delay: 110ms; }
  .ronda:nth-child(3) { animation-delay: 220ms; }
  .ronda:nth-child(4) { animation-delay: 330ms; }
  .ronda:not(:last-child)::after {
    content: '→';
    position: absolute;
    top: 50%;
    right: -12px;
    z-index: 1;
    color: var(--accent);
    font-size: 1.15rem;
    line-height: 1;
    animation: bracket-arrow 900ms ease-in-out infinite;
  }
  .cabecera {
    font-weight: 600;
  }
  .serie {
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 6px 8px;
    background: var(--panel-2);
  }
  .serie.bye {
    border-style: dashed;
    border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
  }
  .vs {
    font-size: 0.75rem;
    margin: 2px 0;
  }
  @keyframes entrant-arrives {
    from { opacity: 0; transform: translateX(-8px); }
    to { opacity: 1; transform: translateX(0); }
  }
  @keyframes round-arrives {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes bracket-arrow {
    50% { transform: translateX(3px); color: var(--accent-2); }
  }
  @media (prefers-reduced-motion: reduce) {
    .clasificado,
    .ronda,
    .ronda:not(:last-child)::after { animation: none; }
  }
</style>
