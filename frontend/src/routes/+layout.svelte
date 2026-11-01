<script lang="ts">
  import '../app.css';
  let { children } = $props();
</script>

<div class="shell">
  <header>
    <a class="brand" href="/">
      <span class="logo" aria-hidden="true">B</span>
      <span>
        <strong>Beyond Baseball</strong>
        <small>cada liga cuenta otra historia</small>
      </span>
    </a>
    <nav>
      <a href="/">Universos</a>
      <a href="/identidades">Identidades</a>
      <a href="/acerca">La plataforma</a>
    </nav>
  </header>
  <main>
    <!--
      Una página que falla al dibujarse tiene que decirlo. Sin esta frontera, un
      error en pleno render deja el DOM como lo mandó el servidor —«Cargando
      club…»— para siempre, sin aviso y sin que recargar sirva de nada. Pasó con
      un importe sin moneda: `Intl.NumberFormat` lanzaba y la ficha entera se
      quedaba colgada.
    -->
    <svelte:boundary>
      {@render children()}

      {#snippet failed(error, reset)}
        <div class="render-error" role="alert">
          <strong>Esta vista no se pudo dibujar.</strong>
          <p>{(error as Error)?.message ?? String(error)}</p>
          <button onclick={reset}>Reintentar</button>
        </div>
      {/snippet}
    </svelte:boundary>
  </main>
  <footer>
    Universos, clubes y personas son ficticios y evolucionan con la simulación.
  </footer>
</div>

<style>
  .render-error {
    margin: 18px 0;
    padding: 14px 16px;
    background: #2b0f14;
    border: 1px solid #7d2a38;
    border-radius: 10px;
    color: #ffd7de;
  }
  .render-error p {
    margin: 6px 0 10px;
    font-family: var(--mono, monospace);
    font-size: 12px;
  }
  .render-error button {
    cursor: pointer;
  }
</style>
