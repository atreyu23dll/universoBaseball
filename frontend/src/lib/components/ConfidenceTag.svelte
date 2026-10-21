<script lang="ts">
  import { CONFIDENCE_LABEL } from '$lib/format';
  let { confidence, sources = [] }: { confidence: string; sources?: string[] } = $props();
  const cls = $derived(
    confidence === 'fictional'
      ? 'tag fictional'
      : confidence === 'observed'
        ? 'tag accent'
        : 'tag warn'
  );
</script>

<span class={cls} title={sources.length ? sources.join(' · ') : undefined}>
  {CONFIDENCE_LABEL[confidence] ?? confidence}
</span>
