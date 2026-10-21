<script lang="ts">
  import '../app.css';
  let { children } = $props();
</script>

<div class="shell">
  <header>
    <a class="brand" href="/">
      <span class="logo" aria-hidden="true">◆</span>
      <span>
        <strong>Baseball Universe</strong>
        <small>central de control de un universo beisbolístico</small>
      </span>
    </a>
    <nav>
      <a href="/">Universos</a>
      <a href="/acerca">Qué funciona</a>
    </nav>
  </header>
  <main>
    {@render children()}
  </main>
  <footer>
    Mundos, clubes y personas son ficticios y generados por la simulación.
    Etapas implementadas: 0 y 1.
  </footer>
</div>
