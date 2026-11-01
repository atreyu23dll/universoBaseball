<script lang="ts">
  /**
   * El escudo de un club.
   *
   * No lo dibuja: lo pide. El contrato del logo —capas, colocación, orden,
   * nivel de detalle— lo interpreta el motor, que devuelve un SVG por
   * `/clubs/{id}/crest.svg`. Antes la semántica vivía aquí, en una cadena de
   * `if/else`, y era el único sitio del sistema que sabía leerla: ningún
   * export, ninguna miniatura y ninguna prueba podían dibujar un escudo sin
   * reimplementarla.
   *
   * `size` viaja al servidor porque **decide el nivel de detalle**, no solo la
   * escala: a 28 píxeles el nombre completo de un club no se dibuja.
   */
  interface Props {
    clubId?: string;
    /** Escudo ya dibujado, para quien lo tenga a mano y evite otra petición. */
    svg?: string;
    size?: number;
    title?: string;
    variant?: 'primary' | 'secondary' | 'monogram' | 'reduced' | 'cap' | 'light' | 'dark';
  }
  let { clubId = '', svg = '', size = 28, title = '', variant = 'primary' }: Props = $props();

  const src = $derived(clubId ? `/api/v1/clubs/${clubId}/crest.svg?size=${Math.round(size)}${variant === 'primary' ? '' : `&variant=${variant}`}` : '');
</script>

{#if svg}
  <span class="crest" style={`width:${size}px;height:${size}px`} role={title ? 'img' : 'presentation'} aria-label={title || undefined}>
    <!-- SVG del propio motor: estático, sin scripts y con el texto escapado. -->
    {@html svg}
  </span>
{:else if src}
  <img class="crest" {src} width={size} height={size} alt={title} loading="lazy" decoding="async" />
{/if}

<style>
  .crest {
    display: block;
    flex: none;
  }
  .crest :global(svg) {
    display: block;
    width: 100%;
    height: 100%;
  }
</style>
