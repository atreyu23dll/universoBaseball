<h1>Qué funciona y qué no</h1>
<p class="muted">
  Esta página existe para que nada en la interfaz dé a entender que hay más
  simulación de la que hay.
</p>

<div class="grid two">
  <div class="panel">
    <h2>Implementado y en uso</h2>
    <ul class="small">
      <li>Universos aislados con semilla, fecha y geografía propias.</li>
      <li>
        Creación de ligas <strong>independientes</strong> con reglas validadas y
        versionadas (estructura, calendario, clasificación, desempates, playoffs).
      </li>
      <li>
        Generación contextual: mercados, clubes, identidad visual, estadios con
        dimensiones reales, plantillas y una población deportiva compartida.
      </li>
      <li>Reparto de talento por draft con informes de scouting falibles.</li>
      <li>
        Motor de partidos <strong>turno al bate por turno al bate</strong>: el
        marcador es la suma de carreras producidas por eventos, y el box score se
        valida contra invariantes después de cada partido.
      </li>
      <li>Clima estacional por latitud y altitud, con efecto en el juego.</li>
      <li>Clasificación recalculada desde los partidos, con desempates explicados.</li>
      <li>Postemporada con siembra, series al mejor de N y campeón.</li>
      <li>Avance del reloj idempotente, persistente y con bloqueo por universo.</li>
      <li>Procedencia de cada número generado, consultable en la ficha del club.</li>
    </ul>
  </div>

  <div class="panel">
    <h2>Diseñado, todavía sin implementar</h2>
    <ul class="small">
      <li>
        <strong>Ascenso y descenso.</strong> Las relaciones se pueden crear y se
        validan (sin ciclos, con cuota única), pero ningún club cambia de división
        al cerrar la temporada.
      </li>
      <li>
        <strong>Rutas de clasificación a copas.</strong> Se registran; no extraen
        participantes todavía.
      </li>
      <li><strong>Selecciones nacionales</strong> y su elegibilidad por liga doméstica.</li>
      <li><strong>Economía con libro mayor</strong>, patrocinios, contratos y fichajes.</li>
      <li><strong>Desarrollo de jugadores</strong> por edad, lesiones y retiros.</li>
      <li><strong>Lanzamiento por lanzamiento</strong> y física de la pelota bateada.</li>
      <li><strong>Mapa cartográfico.</strong> La geografía se consulta como lista.</li>
      <li><strong>WebSocket en vivo.</strong> El estado se consulta por sondeo.</li>
    </ul>
  </div>
</div>

<div class="panel">
  <h2>De dónde salen los datos</h2>
  <p class="small">
    Los nombres de países, estados y ciudades y sus coordenadas son datos
    públicos. Las poblaciones son <strong>estimaciones de orden de magnitud</strong>
    con su año declarado: sirven para escalar mercados, no para citarse como
    censo. Los índices de economía, cultura beisbolística, coste e infraestructura
    son <strong>heurísticas propias</strong> en escala relativa, y son calibrables.
    Las subzonas de ciudad, los clubes, las personas, los estadios y los escudos
    son <strong>ficticios</strong>: no corresponden a nada real y no usan ninguna
    marca existente. Cada dato lleva su etiqueta en la interfaz.
  </p>
</div>
