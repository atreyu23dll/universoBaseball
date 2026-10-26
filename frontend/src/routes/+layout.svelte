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
      <a href="/acerca">La plataforma</a>
    </nav>
  </header>
  <main>
    {@render children()}
  </main>
  <footer>
    Universos, clubes y personas son ficticios y evolucionan con la simulación.
  </footer>
</div>
