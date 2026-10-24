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
        general entre los que no clasificaron por su grupo. La siembra es el
        orden de la tabla general, así que un campeón de división flojo no se
        pone por encima de uno mejor.
      </p>
    {/if}

    {#if bracket.rounds.length}
      <h4>El cuadro</h4>
      <div class="cuadro">
        {#each bracket.rounds as ronda (ronda.round)}
          <div class="ronda">
            <div class="small muted cabecera">
              Ronda {ronda.round} · al mejor de {ronda.best_of}
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
          Con {bracket.slots} clasificados el cuadro es de {bracket.bracket_size}, así
          que {bracket.byes} siembra(s) se salta(n) la primera ronda. Es lo que
          hacen las ligas de verdad en vez de redondear el número de clasificados.
        </p>
      {/if}
    {/if}
  </div>
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
  }
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
    min-width: 170px;
    display: flex;
    flex-direction: column;
    gap: 8px;
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
</style>
