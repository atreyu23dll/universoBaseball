<script lang="ts">
  /**
   * Un fallo contado a quien está usando la aplicación, no a quien la escribió.
   *
   * Antes el título era el código interno —`http_error`, `rule_validation_failed`—
   * y el cuerpo, el mensaje crudo de la petición: «422 en /universes/.../competitions».
   * Ahora manda el mensaje en castellano, el código baja a una línea de
   * referencia para poder citarlo, y lo que no tiene mensaje se traduce aquí.
   */
  import { RequestFailed } from '$lib/api/client';

  let { error }: { error: unknown } = $props();
  const failure = $derived(error instanceof RequestFailed ? error : null);

  /** Lo que se dice cuando el servidor no mandó un mensaje propio. */
  const PORESTADO: Record<number, string> = {
    0: 'No se pudo contactar con el motor. Comprueba que está en marcha.',
    400: 'La petición no era válida.',
    401: 'Hace falta identificarse para esto.',
    403: 'Esta operación no está permitida.',
    404: 'Eso ya no existe. Puede que se haya borrado desde otra pestaña.',
    409: 'Otra operación cambió esto mientras tanto. Vuelve a cargar y reinténtalo.',
    422: 'Hay datos que el formulario no puede aceptar.',
    429: 'Demasiadas peticiones seguidas. Espera un momento.',
    500: 'El motor no pudo completar la operación. No se ha modificado nada del mundo.',
    503: 'El motor no está disponible ahora mismo.'
  };

  const titulo = $derived.by(() => {
    if (!error) return '';
    if (failure) {
      const propio = failure.message ?? '';
      const generico = /^\d{3} en \//.test(propio) || propio === '';
      return generico ? (PORESTADO[failure.status] ?? 'La operación no se pudo completar.') : propio;
    }
    if (error instanceof TypeError) return PORESTADO[0];
    return error instanceof Error ? error.message : String(error);
  });
</script>

{#if error}
  <div class="notice error" role="alert">
    <strong>{titulo}</strong>
    {#if failure && failure.suggestions.length}
      <ul class="small" style="margin:7px 0 0 16px">
        {#each failure.suggestions as suggestion}
          <li>{suggestion}</li>
        {/each}
      </ul>
    {/if}
    {#if failure}
      <p class="small muted" style="margin:8px 0 0">
        Referencia: <span class="mono">{failure.code}</span>
      </p>
    {/if}
  </div>
{/if}
