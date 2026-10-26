<script lang="ts">
  export type RelationshipCompetition = {
    id: string;
    name: string;
    club_count: number;
    education_track?: 'school' | 'formative' | null;
    structure?: Array<{ key: string; label: string; slots: number }>;
  };

  type RelationKind = 'promotion_relegation' | 'affiliate' | 'development' | 'postseason';
  type Direction = 'above' | 'below';

  interface Props {
    competitions: RelationshipCompetition[];
    leagueName: string;
    relationshipMode?: 'independent' | 'dependent';
    linkPartnerId?: string;
    linkPosition?: Direction;
    linkRelation?: RelationKind;
    linkSlots?: number;
    linkLowerMethod?: string;
    onpartnerchange?: () => void;
  }

  let {
    competitions,
    leagueName,
    relationshipMode = $bindable<'independent' | 'dependent'>('independent'),
    linkPartnerId = $bindable(''),
    linkPosition = $bindable<Direction>('below'),
    linkRelation = $bindable<RelationKind>('promotion_relegation'),
    linkSlots = $bindable(2),
    linkLowerMethod = $bindable('top_standings'),
    onpartnerchange
  }: Props = $props();

  let draggedId = $state<string | null>(null);
  let hovering = $state<Direction | null>(null);
  const partner = $derived(competitions.find((competition) => competition.id === linkPartnerId) ?? null);
  const isHierarchy = $derived(linkRelation === 'promotion_relegation');
  const isPostseason = $derived(linkRelation === 'postseason');

  function setIndependent() {
    relationshipMode = 'independent';
    linkPartnerId = '';
  }

  function selectPartner(id: string, direction: Direction = linkPosition) {
    relationshipMode = 'dependent';
    linkPartnerId = id;
    linkPosition = direction;
    onpartnerchange?.();
  }

  function dropPartner(event: DragEvent, direction: Direction) {
    event.preventDefault();
    const id = event.dataTransfer?.getData('text/competition-id') || draggedId;
    if (id) selectPartner(id, direction);
    hovering = null;
    draggedId = null;
  }

  function setRelation(kind: RelationKind) {
    relationshipMode = 'dependent';
    linkRelation = kind;
    if (kind === 'postseason') linkPosition = 'below';
  }

  function changeSlots(delta: number) {
    linkSlots = Math.max(1, Math.min(12, linkSlots + delta));
  }
</script>

<div class="relationship-canvas" aria-label="Editor visual de dependencias">
  <div class="canvas-topbar">
    <div>
      <p class="eyebrow">Dependencias</p>
      <h2>Dibuja la relación</h2>
      <p class="muted small">Arrastra una liga existente al espacio de arriba o abajo. La posición define el sentido; las líneas son la configuración.</p>
    </div>
    <div class="mode-switch" aria-label="Modo de relación">
      <button class:active={relationshipMode === 'independent'} class="canvas-button" type="button" onclick={setIndependent}>
        Sin vínculo
      </button>
      <button
        class:active={relationshipMode === 'dependent'}
        class="canvas-button"
        type="button"
        onclick={() => (relationshipMode = 'dependent')}
        disabled={competitions.length === 0}
      >Conectar liga</button>
    </div>
  </div>

  {#if competitions.length === 0}
    <div class="empty-canvas">
      Esta es la primera competición del universo. Cuando exista otra, aparecerá aquí para conectarla visualmente.
    </div>
  {:else}
    <div class="connection-workspace" class:inactive={relationshipMode === 'independent'}>
      <aside class="league-shelf" aria-label="Ligas existentes">
        <p class="eyebrow">Ligas existentes</p>
        {#each competitions as competition (competition.id)}
          <button
            class:selected={competition.id === linkPartnerId}
            class="league-chip"
            draggable="true"
            type="button"
            onclick={() => selectPartner(competition.id)}
            ondragstart={(event) => {
              draggedId = competition.id;
              event.dataTransfer?.setData('text/competition-id', competition.id);
              if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
            }}
            ondragend={() => {
              draggedId = null;
              hovering = null;
            }}
          >
            <span class="drag-mark" aria-hidden="true">⠿</span>
            <span>
              <strong>{competition.name}</strong>
              <small>{competition.club_count} equipos · {competition.structure?.length ?? 1} división(es)</small>
            </span>
          </button>
        {/each}
      </aside>

      <div class="connection-stage">
        <div
          class:over={hovering === 'above'}
          class="drop-lane upper"
          role="button"
          tabindex="0"
          ondragover={(event) => {
            event.preventDefault();
            hovering = 'above';
          }}
          ondragleave={() => (hovering = null)}
          ondrop={(event) => dropPartner(event, 'below')}
          onclick={() => partner && (linkPosition = 'below')}
          onkeydown={(event) => event.key === 'Enter' && partner && (linkPosition = 'below')}
        >
          <span>{partner && linkPosition === 'below' ? partner.name : 'Arrastra aquí la liga superior'}</span>
          <small>la nueva liga queda por debajo</small>
        </div>

        <div class="node new-league">
          <span class="node-kicker">NUEVA LIGA</span>
          <strong>{leagueName || 'Liga sin nombre'}</strong>
          <span class="node-caption">estructura que estás creando</span>
        </div>

        <svg class="relation-line" viewBox="0 0 100 190" preserveAspectRatio="none" aria-hidden="true">
          {#if partner && relationshipMode === 'dependent'}
            {#if isPostseason}
              <path d="M50 164 C16 132 16 61 50 28" class="flow post" marker-end="url(#arrowhead)" />
            {:else if linkPosition === 'below'}
              <path d="M50 44 L50 150" class:player-flow={!isHierarchy} class="flow" marker-end="url(#arrowhead)" />
              {#if isHierarchy}<path d="M59 150 L59 44" class="flow return" marker-end="url(#arrowhead-muted)" />{/if}
            {:else}
              <path d="M50 150 L50 44" class:player-flow={!isHierarchy} class="flow" marker-end="url(#arrowhead)" />
              {#if isHierarchy}<path d="M59 44 L59 150" class="flow return" marker-end="url(#arrowhead-muted)" />{/if}
            {/if}
          {/if}
          <defs>
            <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" /></marker>
            <marker id="arrowhead-muted" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" /></marker>
          </defs>
        </svg>

        <div
          class:over={hovering === 'below'}
          class="drop-lane lower"
          role="button"
          tabindex="0"
          ondragover={(event) => {
            event.preventDefault();
            hovering = 'below';
          }}
          ondragleave={() => (hovering = null)}
          ondrop={(event) => dropPartner(event, 'above')}
          onclick={() => partner && (linkPosition = 'above')}
          onkeydown={(event) => event.key === 'Enter' && partner && (linkPosition = 'above')}
        >
          <span>{partner && linkPosition === 'above' ? partner.name : 'Arrastra aquí la liga inferior'}</span>
          <small>la nueva liga queda por encima</small>
        </div>
      </div>

      <aside class="inspector" aria-live="polite">
        <p class="eyebrow">Tipo de conexión</p>
        <div class="relation-kinds">
          <button class:active={linkRelation === 'promotion_relegation'} type="button" onclick={() => setRelation('promotion_relegation')}>
            <strong>↕ División</strong><small>suben y bajan clubes</small>
          </button>
          <button class:active={linkRelation === 'affiliate'} type="button" onclick={() => setRelation('affiliate')}>
            <strong>⇄ Filial</strong><small>circulan jugadores</small>
          </button>
          <button class:active={linkRelation === 'development'} type="button" onclick={() => setRelation('development')}>
            <strong>→ Desarrollo</strong><small>programa compartido</small>
          </button>
          <button class:active={linkRelation === 'postseason'} type="button" onclick={() => setRelation('postseason')}>
            <strong>↗ Postemporada</strong><small>clasifica, no desciende</small>
          </button>
        </div>

        {#if partner && relationshipMode === 'dependent'}
          <div class="structure-readout">
            <div class="spread"><strong>{partner.name}</strong><span class="tag accent">estructura origen</span></div>
            <div class="division-strip">
              {#each partner.structure ?? [{ key: 'general', label: 'Tabla general', slots: partner.club_count }] as division (division.key)}
                <span title={`${division.slots} equipos`}>{division.label}<b>{division.slots}</b></span>
              {/each}
            </div>
          </div>

          {#if isHierarchy || isPostseason}
            <div class="slot-config">
              <span>{isHierarchy ? 'Intercambio por temporada' : 'Cupos que entran al cuadro'}</span>
              <div class="stepper">
                <button type="button" aria-label="Restar plaza" onclick={() => changeSlots(-1)}>−</button>
                <strong>{linkSlots}</strong>
                <button type="button" aria-label="Sumar plaza" onclick={() => changeSlots(1)}>+</button>
              </div>
            </div>
            {#if isHierarchy}
              <div class="choice-row" aria-label="Criterio de ascenso">
                <button class:active={linkLowerMethod === 'top_standings'} type="button" onclick={() => (linkLowerMethod = 'top_standings')}>Por tabla</button>
                <button class:active={linkLowerMethod === 'playoff_champion'} type="button" onclick={() => (linkLowerMethod = 'playoff_champion')}>Campeón primero</button>
              </div>
            {/if}
          {/if}

          <p class="relation-summary">
            {#if isHierarchy}
              {linkPosition === 'below'
                ? `La nueva liga alimenta a ${partner.name}; ${linkSlots} equipo(s) ascienden y el mismo número desciende.`
                : `La nueva liga recibe a los mejores de ${partner.name}; ${linkSlots} equipo(s) intercambian categoría.`}
            {:else if isPostseason}
              {partner.name} envía {linkSlots} clasificado(s) a la postemporada de esta nueva competición. Conserva su independencia.
            {:else}
              Es una conexión operativa: puede mover jugadores, pero ningún club sube ni baja por este vínculo.
            {/if}
          </p>
        {:else}
          <p class="muted small inspector-empty">Elige o arrastra una liga para ver sus divisiones y trazar el vínculo.</p>
        {/if}
      </aside>
    </div>
  {/if}
</div>

<style>
  .relationship-canvas { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; background: linear-gradient(135deg, #111923, #13191f); }
  .canvas-topbar { display: flex; justify-content: space-between; gap: 18px; align-items: start; padding: 18px; border-bottom: 1px solid var(--line); }
  .canvas-topbar h2 { margin: 0 0 4px; }
  .canvas-topbar p { margin: 0; max-width: 610px; }
  .eyebrow { color: var(--accent); font: 700 10px/1 var(--mono); letter-spacing: .12em; margin: 0 0 7px; }
  .mode-switch, .choice-row { display: flex; gap: 5px; background: #0d131a; padding: 4px; border-radius: 9px; }
  .canvas-button, .choice-row button { padding: 7px 10px; color: var(--muted); background: transparent; border: 1px solid transparent; font-size: 12px; }
  .canvas-button.active, .choice-row button.active { color: #07150e; background: var(--accent); }
  .empty-canvas { margin: 18px; color: var(--muted); border: 1px dashed var(--line); border-radius: 10px; padding: 20px; }
  .connection-workspace { display: grid; grid-template-columns: minmax(170px, .78fr) minmax(280px, 1.3fr) minmax(230px, 1fr); min-height: 450px; transition: opacity .25s ease; }
  .connection-workspace.inactive { opacity: .48; }
  .league-shelf, .inspector { padding: 16px; background: color-mix(in srgb, var(--panel) 88%, #06130d); }
  .league-shelf { border-right: 1px solid var(--line); }
  .inspector { border-left: 1px solid var(--line); }
  .league-chip { display: flex; align-items: flex-start; gap: 8px; width: 100%; padding: 10px; margin-bottom: 8px; text-align: left; color: var(--text); background: var(--panel-2); border: 1px solid var(--line); transition: transform .16s ease, border-color .16s ease, background .16s ease; }
  .league-chip:hover, .league-chip.selected { transform: translateX(3px); border-color: var(--accent); background: #183126; }
  .league-chip small { display: block; color: var(--muted); font-size: 11px; font-weight: 400; margin-top: 2px; }
  .drag-mark { color: var(--accent-2); font-size: 17px; line-height: 1; cursor: grab; }
  .connection-stage { position: relative; display: grid; grid-template-rows: 1fr auto 1fr; justify-items: center; align-items: center; padding: 20px; min-height: 450px; background-image: radial-gradient(color-mix(in srgb, var(--line) 70%, transparent) 1px, transparent 1px); background-size: 14px 14px; }
  .drop-lane { z-index: 2; width: min(90%, 280px); min-height: 82px; padding: 14px; display: grid; place-items: center; text-align: center; border: 1px dashed #455261; border-radius: 12px; color: var(--muted); background: color-mix(in srgb, var(--panel) 78%, transparent); transition: border-color .18s ease, transform .18s ease, background .18s ease; }
  .drop-lane:hover, .drop-lane.over { border-color: var(--accent); background: #183126; transform: scale(1.025); color: var(--text); }
  .drop-lane span { font-weight: 650; font-size: 13px; }
  .drop-lane small { margin-top: 4px; font-size: 11px; }
  .node { position: relative; z-index: 3; width: min(84%, 250px); padding: 14px; text-align: center; border-radius: 12px; background: #19392a; border: 1px solid var(--accent); box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 8%, transparent); }
  .node-kicker, .node-caption { display: block; font-size: 10px; color: #9ccfb7; letter-spacing: .09em; }
  .node strong { display: block; margin: 5px 0; }
  .relation-line { position: absolute; inset: 66px 0; width: 100%; height: calc(100% - 132px); pointer-events: none; z-index: 1; overflow: visible; }
  .relation-line path { fill: none; stroke: var(--accent); stroke-width: 2; stroke-dasharray: 5 4; animation: travel 1.1s linear infinite; }
  .relation-line .return { stroke: var(--accent-2); opacity: .78; }
  .relation-line .player-flow { stroke: #7eb7e9; }
  .relation-line .post { stroke: #d5a84f; }
  :global(#arrowhead) { fill: var(--accent); } :global(#arrowhead-muted) { fill: var(--accent-2); }
  @keyframes travel { to { stroke-dashoffset: -18; } }
  .relation-kinds { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .relation-kinds button { text-align: left; padding: 9px; color: var(--muted); background: var(--panel-2); border: 1px solid var(--line); transition: border-color .16s ease, transform .16s ease; }
  .relation-kinds button:hover, .relation-kinds button.active { color: var(--text); border-color: var(--accent); transform: translateY(-1px); }
  .relation-kinds strong, .relation-kinds small { display: block; }
  .relation-kinds small { margin-top: 2px; font-size: 10px; color: inherit; opacity: .8; }
  .structure-readout, .slot-config { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); }
  .structure-readout strong { font-size: 13px; }
  .division-strip { display: flex; gap: 4px; margin-top: 9px; flex-wrap: wrap; }
  .division-strip span { flex: 1 1 72px; min-width: 0; padding: 6px; background: #202b37; border-radius: 5px; font-size: 10px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .division-strip b { color: var(--accent); margin-left: 4px; }
  .slot-config { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: var(--muted); font-size: 12px; }
  .stepper { display: flex; align-items: center; gap: 7px; background: #0d131a; padding: 3px; border-radius: 8px; }
  .stepper button { width: 26px; height: 26px; padding: 0; font-size: 18px; background: var(--panel-2); color: var(--text); }
  .stepper strong { min-width: 18px; text-align: center; color: var(--accent); font-family: var(--mono); }
  .choice-row { margin-top: 10px; }
  .relation-summary { margin: 14px 0 0; padding: 10px; border-left: 2px solid var(--accent); color: var(--muted); font-size: 12px; background: color-mix(in srgb, var(--panel-2) 70%, transparent); }
  .inspector-empty { margin-top: 16px; }
  @media (max-width: 900px) { .canvas-topbar { flex-direction: column; } .connection-workspace { grid-template-columns: 1fr; } .league-shelf, .inspector { border: 0; border-bottom: 1px solid var(--line); } .connection-stage { min-height: 400px; } .league-shelf { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; } .league-shelf .eyebrow { grid-column: 1 / -1; } .league-chip { margin: 0; } }
</style>
