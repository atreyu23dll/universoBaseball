<script lang="ts">
  import type { PageData } from './$types';
  import type { IdentityCard } from './+page';
  let { data }: { data: PageData } = $props();
  let search = $state('');
  let style = $state('');
  let country = $state('');
  let background = $state('light');
  let limit = $state(24);
  let selected = $state<IdentityCard | null>(null);
  let variant = $state('primary');
  let size = $state(384);
  let dialog: HTMLDialogElement;
  const styles: Record<string,string> = {
    heritage:'Firma clásica', athletic:'Firma deportiva', seal:'Sello',
    ligature:'Monograma', pennant:'Banderín', symbolic:'Símbolo',
    heraldic:'Heráldica', floral:'Composición floral', radial:'Geometría radial'
  };
  const variants: Record<string,string> = {
    primary:'Principal',secondary:'Secundario',monogram:'Monograma',
    reduced:'Reducido',cap:'Gorra',light:'Fondo claro',dark:'Fondo oscuro'
  };
  const institutions: Record<string,string> = {
    community:'Club comunitario',municipal:'Club municipal',
    private:'Club privado',corporate:'Club empresarial'
  };
  const normalize = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const filtered = $derived(data.gallery.items.filter(item =>
    (!style || item.style === style) && (!country || item.country === country) &&
    normalize(item.name + ' ' + item.place + ' ' + item.concept).includes(normalize(search))
  ));
  const availableStyles = $derived([...new Set(data.gallery.items.map(item => item.style))].sort());
  const countries = $derived([...new Set(data.gallery.items.map(item => item.country))].sort());
  const imageUrl = (item: IdentityCard, version = 'primary', pixels = 256) =>
    `/api/v1/identity-gallery/${item.index}/crest.svg?seed=${data.gallery.seed}&variant=${version}&size=${pixels}&v=${data.gallery.version}`;
  function inspect(item: IdentityCard) {
    selected = item;
    variant = background === 'dark' ? 'dark' : 'primary';
    size = 384;
    dialog.showModal();
  }
</script>

<svelte:head>
  <title>Atlas de identidades · Beyond Baseball</title>
  <meta name="description" content="Cien instituciones ficticias: nombres, símbolos y marcas generados por el motor procedural de Baseball Universe." />
</svelte:head>

<section class="intro">
  <div>
    <span class="eyebrow">LABORATORIO DE IDENTIDAD / 01</span>
    <h1>Cien clubes.<br /><em>Cien historias por empezar.</em></h1>
    <p>Explora las marcas que nacen de un nombre, un lugar y una cultura institucional.
      Cada colección se calcula con una semilla: puedes volver a ella y encontrar los mismos clubes.</p>
  </div>
  <div class="collection">
    <div class="big-number">{data.gallery.total}<span>instituciones ficticias</span></div>
    <div class="metrics"><span>{data.gallery.unique_logos} logos distintos</span><span>{data.gallery.structures} estructuras</span></div>
    <form method="GET" action="/identidades">
      <label for="seed">Semilla de la colección</label>
      <div class="seed-row">
        <input id="seed" name="seed" type="number" min="0" max="4294967295" step="1" required value={data.gallery.seed} />
        <button type="submit">Generar</button>
      </div>
    </form>
    <small>{data.gallery.version} · SVG calculado, sin imágenes externas</small>
  </div>
</section>

<section class="examples" aria-labelledby="examples-title">
  <div class="examples-heading">
    <span class="eyebrow">TRES POSIBILIDADES DEL MISMO MOTOR</span>
    <h2 id="examples-title">De las iniciales a la heráldica</h2>
    <p>Curvas, capas y repeticiones. Estos ejemplos muestran capacidades; la colección combina las reglas libremente.</p>
  </div>
  {#each [['monogram','Iniciales CJ','Letras superpuestas a un círculo'],['elephant','Elefante frontal','Escudo dividido, curvas y contornos'],['roses','Tres rosas','Repetición triangular sin contenedor']] as [key,title,description]}
    <a class="example" href={`/api/v1/identity-gallery/examples/${key}.svg?size=512`} target="_blank" rel="noreferrer">
      <img src={`/api/v1/identity-gallery/examples/${key}.svg?size=256`} width="192" height="192" alt={title} />
      <strong>{title}</strong><span>{description}</span>
    </a>
  {/each}
</section>

<section aria-labelledby="collection-title">
  <div class="section-heading"><h2 id="collection-title">La colección</h2><span>{filtered.length} identidades</span></div>
  <div class="filters">
    <label class="search">Buscar nombre o territorio<input type="search" bind:value={search} oninput={() => limit=24} placeholder="Juárez, Cumbre, Unión…" /></label>
    <label>Lenguaje visual<select bind:value={style} onchange={() => limit=24}><option value="">Todos los estilos</option>{#each availableStyles as key}<option value={key}>{styles[key] ?? key}</option>{/each}</select></label>
    <label>País<select bind:value={country} onchange={() => limit=24}><option value="">Todos</option>{#each countries as code}<option>{code}</option>{/each}</select></label>
    <fieldset class="background-toggle"><legend>Fondo</legend>
      <button class:active={background==='light'} aria-pressed={background==='light'} onclick={() => background='light'}>Claro</button>
      <button class:active={background==='dark'} aria-pressed={background==='dark'} onclick={() => background='dark'}>Oscuro</button>
    </fieldset>
  </div>
  <div class="cards">
    {#each filtered.slice(0,limit) as item (data.gallery.seed + ':' + item.index)}
      <button class="identity-card" onclick={() => inspect(item)} aria-label={`Inspeccionar identidad de ${item.name}`}>
        <div class="art" class:dark={background==='dark'}>
          <span class="card-number">{String(item.index+1).padStart(3,'0')}</span>
          <img src={imageUrl(item,background,256)} width="256" height="256" alt="" loading="lazy" decoding="async" />
          <div class="swatches" aria-hidden="true">{#each ['field','mark','accent'] as role}<span style:background={item.palette[role]}></span>{/each}</div>
        </div>
        <div class="card-text">
          <span class="place">{item.country} / {item.place}</span>
          <h3>{item.name}</h3>
          <div class="card-meta"><span>{styles[item.style] ?? item.style}</span><span>{item.year}</span></div>
        </div>
      </button>
    {/each}
  </div>
  {#if filtered.length===0}<p class="empty">No hay identidades con esos filtros.</p>{/if}
  {#if filtered.length>limit}<div class="load-more"><button class="ghost" onclick={() => limit+=24}>Mostrar más · {filtered.length-limit} restantes</button></div>{/if}
</section>

<dialog bind:this={dialog} onclose={() => selected=null}>
  {#if selected}
    <div class="detail-heading"><span class="eyebrow">IDENTIDAD {String(selected.index+1).padStart(3,'0')}</span><button class="ghost" onclick={() => dialog.close()} aria-label="Cerrar detalle">Cerrar ×</button></div>
    <div class="detail-grid">
      <div>
        <div class="large-art" class:dark={background==='dark'}>
          <img src={imageUrl(selected,variant,size)} width={size} height={size} alt={selected.name} />
        </div>
        <div class="size-options" aria-label="Tamaño de la marca">
          {#each [24,48,128,256,384] as pixels}<button class:active={size===pixels} aria-pressed={size===pixels} onclick={() => size=pixels}>{pixels} px</button>{/each}
        </div>
        <p class="size-note">La principal usa el símbolo reducido por debajo de 64 px.</p>
      </div>
      <div class="detail-copy">
        <span class="place">{selected.place}, {selected.country} · {selected.year}</span>
        <h2>{selected.name}</h2>
        <p>{institutions[selected.institution] ?? selected.institution} · identidad ficticia</p>
        <p>{selected.rationale}</p>
        <label>Variante<select bind:value={variant}>{#each Object.entries(variants) as [value,label]}<option {value}>{label}</option>{/each}</select></label>
        <div class="color-list">{#each Object.entries(selected.palette) as [role,color]}<span title={role}><i style:background={color}></i>{color}</span>{/each}</div>
        <div class="export-actions">
          <a class="button" href={imageUrl(selected,variant,512)} download={`identidad-${selected.index}-${variant}.svg`}>Descargar SVG</a>
          <a class="button ghost" href={`/api/v1/identity-gallery/${selected.index}?seed=${data.gallery.seed}`} download={`identidad-${selected.index}.json`}>Exportar identidad</a>
        </div>
        <details>
          <summary>Proceso y comprobaciones</summary>
          <p>Concepto: {selected.concept}. Gramática: {selected.grammar}. Semilla: {selected.seed}.</p>
          <p>Medidas geométricas orientativas; la valoración estética requiere revisión visual.</p>
          <dl>{#each [['Contraste','contrast'],['Equilibrio','balance'],['Legibilidad','legibility'],['Dentro del lienzo','bounds'],['Separación texto/símbolo','collisions']] as [label,key]}
            <div><dt>{label}</dt><dd>{Math.round(Number(selected.quality[variant]?.[key as keyof typeof selected.quality.primary] ?? 0)*100)}%</dd></div>
          {/each}</dl>
          {#each selected.quality[variant]?.issues ?? [] as issue}<p class="issue">{issue}</p>{/each}
        </details>
      </div>
    </div>
  {/if}
</dialog>

<style>
  .eyebrow { display:block; font-size:10px; font-weight:800; letter-spacing:.17em; color:var(--accent-2); margin-bottom:14px; }
  .intro { display:grid; grid-template-columns:1.6fr 1fr; gap:60px; padding:40px 0 42px; align-items:center; }
  h1 { font-size:clamp(32px,4.2vw,56px); letter-spacing:-.045em; line-height:1.08; }
  h1 em { font-style:normal; color:var(--muted); }
  .intro p { max-width:570px; color:var(--muted); font-size:15px; line-height:1.8; margin-top:22px; }
  .collection { padding:24px; border:1px solid var(--line); border-radius:16px; background:var(--panel); }
  .big-number { font-size:60px; font-weight:800; letter-spacing:-.06em; line-height:1; }
  .big-number span { display:block; margin-top:10px; font-size:12px; letter-spacing:.02em; color:var(--muted); font-weight:500; }
  .metrics { display:flex; gap:16px; font-size:11px; padding:18px 0; color:var(--accent-2); }
  .seed-row { display:flex; gap:8px; margin:6px 0 12px; }
  input,select { width:100%; min-width:0; padding:10px; border-radius:8px; }
  label,legend { font-size:11px; color:var(--muted); }
  label { display:grid; gap:6px; }
  .collection small { font-size:10px; color:var(--muted); }
  .examples { display:grid; grid-template-columns:1.3fr repeat(3,1fr); gap:18px; align-items:center; border-block:1px solid var(--line); padding:28px 0; margin-bottom:38px; }
  .examples-heading p { font-size:12px; color:var(--muted); max-width:220px; }
  .example { display:grid; justify-items:center; text-align:center; text-decoration:none; padding:16px 8px; border-radius:12px; background:#ede8db; color:#27372f; }
  .example img { max-width:100%; object-fit:contain; margin-bottom:12px; }
  .example strong { font-size:12px; }.example span { font-size:10px; color:#556259; margin-top:4px; }
  .section-heading { display:flex; justify-content:space-between; align-items:baseline; }.section-heading span { color:var(--muted);font-size:12px; }
  .filters { display:flex; gap:14px; align-items:end; margin:18px 0 24px; flex-wrap:wrap; }
  .search { flex:1; min-width:180px; }
  .background-toggle { border:0; padding:0; margin:0; white-space:nowrap; }
  .background-toggle button,.size-options button { background:var(--panel-2); color:var(--muted); box-shadow:none; }
  .background-toggle .active,.size-options .active { background:var(--accent-2); color:#182411; }
  .cards { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; }
  .identity-card { display:block; padding:0; background:var(--panel); border:1px solid var(--line); text-align:left; overflow:hidden; border-radius:12px; color:var(--text); }
  .identity-card:hover { border-color:var(--accent); box-shadow:0 12px 30px #0004; }
  .art { display:grid; place-items:center; position:relative; background:#eee9de; padding:18px 8px 24px; min-height:306px; }
  .art.dark,.large-art.dark { background:#101a23; }
  .art img { max-width:100%; height:auto; }
  .card-number { position:absolute; left:12px; top:10px; font:10px var(--mono); color:#657269; }.dark .card-number { color:#9caba7; }
  .swatches { display:flex; position:absolute; bottom:12px; gap:4px; }.swatches span { width:8px; height:8px; border-radius:50%; box-shadow:0 0 0 1px #7c827255; }
  .card-text { padding:16px; }.place { color:var(--muted);font-size:10px;font-weight:500;letter-spacing:.04em; }
  .card-text h3 { text-transform:none; color:var(--text); font-size:15px; letter-spacing:-.02em; margin:8px 0 14px; min-height:40px; }
  .card-meta { display:flex; justify-content:space-between; color:var(--muted); font-size:10px; font-weight:500; }
  .load-more,.empty { text-align:center; margin:28px; }.empty { color:var(--muted); }
  dialog { width:min(1080px,calc(100vw - 24px)); max-height:90vh; overflow:auto; padding:24px; border:1px solid var(--line); border-radius:18px; background:var(--panel);color:var(--text); }
  dialog::backdrop { background:#05050bbb; backdrop-filter:blur(5px); }
  .detail-heading { display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; }.detail-heading .eyebrow { margin:0; }
  .detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:28px; }
  .large-art { min-height:416px; display:grid;place-items:center;background:#eee9de;border-radius:12px;overflow:hidden; }
  .large-art img { max-width:100%; height:auto; object-fit:contain; }
  .detail-copy h2 { font-size:26px; margin:8px 0; }.detail-copy p { color:var(--muted);font-size:12px;line-height:1.7; }
  .size-options { display:flex; justify-content:center;flex-wrap:wrap;gap:5px;margin-top:12px; }.size-note { font-size:10px;color:var(--muted);text-align:center; }
  .color-list { display:flex; flex-wrap:wrap; gap:10px;margin:18px 0; }.color-list span { display:flex; align-items:center;gap:5px;font:9px var(--mono); }.color-list i { width:12px;height:12px;border-radius:50%;border:1px solid #8885; }
  .export-actions { display:flex;gap:8px;flex-wrap:wrap; }.export-actions a { font-size:11px; }
  details { border-top:1px solid var(--line);margin-top:24px;padding-top:14px; font-size:12px; }summary { cursor:pointer; }
  dl div { display:flex;justify-content:space-between;margin:6px 0; }dd { font-family:var(--mono); }.issue { color:var(--accent-2)!important; }
  @media(max-width:950px) { .cards { grid-template-columns:repeat(2,minmax(0,1fr)); }.intro { gap:24px; }.examples { grid-template-columns:repeat(3,1fr); }.examples-heading { grid-column:1/-1; }.examples-heading p { max-width:none; } }
  @media(max-width:650px) { .intro,.detail-grid { grid-template-columns:1fr; }.intro { padding:24px 0; }.cards { grid-template-columns:1fr; gap:16px; }.art { min-height:306px; }.card-text { padding:12px; }.card-text h3 { font-size:13px; }.examples { grid-template-columns:1fr;gap:12px; }.example { padding:20px; }.example img { height:192px; }.example span { display:none; }.large-art { min-height:280px; }dialog { padding:16px; } }
</style>
