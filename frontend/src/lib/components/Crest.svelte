<script lang="ts">
  /** Escudo dibujado con primitivas SVG. Sin imágenes externas, sin marcas reales. */
  interface Props {
    primary: string;
    secondary: string;
    shape?: string;
    motif?: string;
    size?: number;
    title?: string;
  }
  let {
    primary,
    secondary,
    shape = 'escudo_clasico',
    motif = 'pelota',
    size = 28,
    title = ''
  }: Props = $props();

  const outlines: Record<string, string> = {
    escudo_clasico: 'M50 4 L94 18 V54 C94 78 72 94 50 100 C28 94 6 78 6 54 V18 Z',
    circulo: 'M50 4 A46 46 0 1 1 49.9 4 Z',
    rombo: 'M50 2 L98 50 L50 98 L2 50 Z',
    banderola: 'M8 6 H92 V74 L50 98 L8 74 Z',
    hexagono: 'M50 3 L92 27 V73 L50 97 L8 73 V27 Z'
  };
</script>

<svg
  class="crest"
  width={size}
  height={size}
  viewBox="0 0 100 100"
  role={title ? 'img' : 'presentation'}
  aria-label={title || undefined}
>
  <path d={outlines[shape] ?? outlines.escudo_clasico} fill={primary} stroke={secondary} stroke-width="5" />
  {#if motif === 'pelota'}
    <circle cx="50" cy="50" r="19" fill={secondary} />
    <path d="M38 36 Q50 50 38 64 M62 36 Q50 50 62 64" stroke={primary} stroke-width="4" fill="none" />
  {:else if motif === 'bate_cruzado'}
    <path d="M28 70 L70 30 M70 70 L28 30" stroke={secondary} stroke-width="9" stroke-linecap="round" />
  {:else if motif === 'home_plate'}
    <path d="M30 34 H70 V58 L50 74 L30 58 Z" fill={secondary} />
  {:else if motif === 'guante'}
    <path d="M32 68 V44 Q32 30 44 30 Q50 30 50 38 Q50 28 58 28 Q68 28 68 42 V68 Z" fill={secondary} />
  {:else if motif === 'estrella'}
    <path d="M50 26 L58 45 L78 46 L62 58 L68 77 L50 66 L32 77 L38 58 L22 46 L42 45 Z" fill={secondary} />
  {:else}
    <path d="M22 70 L40 42 L52 58 L62 44 L78 70 Z" fill={secondary} />
  {/if}
</svg>
