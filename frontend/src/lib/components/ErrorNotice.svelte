<script lang="ts">
  import { RequestFailed } from '$lib/api/client';
  let { error }: { error: unknown } = $props();
  const failure = $derived(error instanceof RequestFailed ? error : null);
</script>

{#if error}
  <div class="notice error">
    <strong>{failure?.code ?? 'error'}</strong>
    — {error instanceof Error ? error.message : String(error)}
    {#if failure && failure.suggestions.length}
      <ul class="small" style="margin:6px 0 0 16px">
        {#each failure.suggestions as suggestion}
          <li>{suggestion}</li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}
