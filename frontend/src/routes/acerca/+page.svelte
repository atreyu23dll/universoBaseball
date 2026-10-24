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
        Creación de competiciones con reglas validadas y versionadas (estructura,
        calendario, clasificación, desempates, playoffs). Nacen
        <strong>independientes</strong> siempre; el asistente permite vincularlas
        en el acto con otra que ya exista, y la dependencia la crea esa relación,
        nunca una etiqueta del reglamento.
      </li>
      <li>
        <strong>El usuario configura la competición, no los clubes.</strong> La
        única pregunta de naturaleza institucional es la modalidad de
        participación, y lo que define son reglas: si se admite pagar a los
        jugadores, si hace falta licencia, qué carga de calendario es sostenible.
        El formulario no pregunta —ni la API acepta— presupuestos, financiación,
        propiedad de estadios, personal ni nivel de riqueza.
      </li>
      <li>
        <strong>Categorías de edad y elegibilidad</strong>: edad mínima y máxima,
        fecha de corte del reglamento, permanencia en la categoría tras cumplir
        años, residencia y salvaguarda obligatoria cuando hay menores. Crear una
        categoría 8–12 no crea otra de 13–17.
      </li>
      <li>
        <strong>Economía de abajo arriba.</strong> Cada club estima lo que puede
        recaudar en su zona —cuotas, su parte del patrocinio local, taquilla si
        controla el recinto, apoyos según quién lo gobierne, derechos de emisión
        solo si tiene audiencia— y después decide en qué gastarlo: primero lo
        obligatorio, y solo con el margen lo demás. El presupuesto es el
        resultado, no el punto de partida, y cada partida dice su causa.
      </li>
      <li>
        <strong>Recursos locales finitos.</strong> La bolsa publicitaria de una
        zona se reparte entre los clubes que la disputan y, si hay menos campos
        que clubes, se comparte sede. Meter veinte equipos en un barrio divide el
        dinero, no lo multiplica.
      </li>
      <li>
        <strong>Instituciones heterogéneas y autónomas.</strong> En la misma
        competición conviven colectivos sin propietario, asociaciones de socios,
        equipos respaldados por un negocio, programas municipales o escolares y
        sociedades deportivas, cada uno con su acuerdo de sede y su reparto de
        responsabilidades, con funciones acumuladas en una persona y puestos sin
        cubrir.
      </li>
      <li>
        <strong>Moneda por jurisdicción.</strong> Sale del territorio, no del
        idioma de la interfaz, y todo importe es un múltiplo del gasto mensual de
        referencia de un hogar de ese país, declarado como estimación.
      </li>
      <li>
        <strong>Geografía mundial.</strong> El territorio se resuelve contra un
        gazetteer de GeoNames: 252 países con su moneda, 3 865 divisiones
        administrativas y 236 632 localidades de 500 habitantes o más, con
        variantes de nombre y búsqueda sin acentos. Se elige una entidad concreta
        y la competición guarda su identificador, no el texto escrito.
      </li>
      <li>
        <strong>Cobertura y conocimiento, separados.</strong> De un territorio
        nuevo se sabe su jerarquía, su población y su moneda, con fuente. No se
        sabe su economía, su cultura beisbolística ni su infraestructura: esos
        índices quedan como supuesto declarado y <strong>no</strong> se deducen
        del país. Si falta el coste de referencia, el mundo se genera igual y las
        cuentas salen sin importes.
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
      <li>
        <strong>Ascenso y descenso</strong> al cerrar la temporada: la relación es
        la autoridad única de su cuota, el intercambio es atómico, los clubes
        conservan identidad, estadio, plantilla, deudas e historia, y con varias
        ligas alimentadoras la cuota total se reparte en vez de multiplicarse.
        Los requisitos de ascenso (aforo, deuda) pueden bloquear una plaza, y
        entonces tampoco desciende nadie por ella.
      </li>
      <li>
        <strong>Divisiones, grupos y conferencias</strong> dentro de una misma
        competición: el reparto lo hace el motor por cercanía o por recursos y
        deja escrito por qué cada club está donde está, el calendario juega más
        veces contra los de la propia división, la tabla trae el puesto del
        grupo sin dejar de contar todos los partidos, y a la postemporada entra
        quien el tablero del paso 6 haya puesto en una ronda. El reparto se
        rehace cada temporada con los clubes que hay.
      </li>
      <li>
        <strong>Temporadas encadenadas</strong>: cuando una edición termina, el
        mundo abre la siguiente con los clubes que ya existen —sin regenerar
        nada— y las ligas vinculadas esperan a que todas cierren antes de mover
        clubes.
      </li>
      <li>
        Vínculos filiales, juveniles y de desarrollo, que mueven jugadores y
        <strong>nunca</strong> clubes.
      </li>
      <li>
        <strong>Liquidación de temporada.</strong> Al cerrar el año, cada club
        cuenta lo que <strong>cobró</strong>, que no es lo que había previsto: un
        patrocinio prometido no es dinero cobrado y un partido que no se jugó no
        vendió entradas. Las obligaciones, en cambio, se pagan enteras: lo que no
        se puede cubrir pasa a deuda y se dice. El libro mayor de cada temporada
        está en la ficha del club, asiento por asiento, con lo previsto al lado.
      </li>
      <li>
        <strong>Instituciones que cambian y clubes que desaparecen.</strong> La
        afición crece o se va según lo que pasó en el campo, la sede mejora o se
        pierde, un colectivo con años y cuentas sanas se constituye en asamblea
        de socios. Y dos temporadas seguidas sin poder cubrir sus obligaciones y
        el club deja de competir: nadie le regala el dinero que le falta para
        mantener el número de equipos de la liga. Conserva su ficha, su historia
        y sus títulos; deja de jugar.
      </li>
      <li>
        <strong>Postemporada con pases directos.</strong> Las plazas no tienen
        que ser potencia de dos: con seis clasificados el cuadro es de ocho y las
        dos mejores siembras esperan en la segunda ronda, como en las ligas de
        verdad.
      </li>
      <li>
        <strong>La estructura se dibuja, no se rellena.</strong> El paso 6 es un
        editor: arrancas con una tabla única de tus equipos, añades divisiones y
        arrastras plazas de una a otra. Cada división lleva sus propias vueltas
        —no tienen que parecerse entre sí—. Debajo se dibuja en vivo lo que
        sale: partidos, jornadas, matriz de cruces, las dos primeras semanas día
        a día y el cuadro de postemporada con el motivo de cada clasificado. Lo
        calcula el motor, no es una maqueta, y no escribe nada hasta que
        confirmas.
      </li>
      <li>
        <strong>El camino al título es un tablero.</strong> La primera columna
        es la competición entera —todos los puestos de todas las divisiones— y
        las demás son las rondas que tú añades y nombras. Una plaza clasifica
        porque está puesta en una ronda: no hay pase directo ni repechaje,
        porque esas etiquetas no decidían nada. Con eso se dibuja igual una copa
        —los campeones de grupo a octavos y los ganadores subiendo— que una
        postemporada de la MLB, donde los campeones de división esperan la
        segunda ronda mientras los comodines pelean la primera. Y por ronda se
        elige quién se cruza con quién: resembrando por la tabla, por sorteo o
        con las llaves fijas del cuadro.
      </li>
      <li>Procedencia de cada número generado, consultable en la ficha del club.</li>
    </ul>
  </div>

  <div class="panel">
    <h2>Diseñado, todavía sin implementar</h2>
    <ul class="small">
      <li>
        <strong>Nombres fuera del español.</strong> El generador de nombres de
        clubes y personas tiene un solo léxico, de español de México. Ahora que
        se puede crear una liga en cualquier parte del mundo, eso se nota: los
        clubes de Kampala se llamarán «Zopilotes» y sus jugadores tendrán
        nombres mexicanos. Hace falta léxico por idioma, con sus fuentes.
      </li>
      <li>
        <strong>Mapa cartográfico.</strong> La búsqueda y la ficha de un
        territorio son texto, navegable con teclado. No hay vista de mapa, ni
        polígonos administrativos descargados: cuando un territorio no tiene
        límite publicado se ofrece delimitar por radio y se avisa de que es una
        aproximación.
      </li>
      <li>
        <strong>Coste de referencia fuera de cinco países.</strong> Se conoce la
        moneda de 251 de 252, pero los importes solo se pueden calcular donde el
        ancla está curada: México, Argentina, Brasil, Cuba y República
        Dominicana.
      </li>
      <li>
        <strong>Una segunda fase de tabla.</strong> Una liguilla entre los
        clasificados antes de los cruces cabe en el modelo, y el motor todavía no
        la juega: hace falta una clasificación por fase y no por temporada. El
        reglamento la rechaza diciéndolo, en vez de aceptarla y no simularla.
      </li>
      <li>
        <strong>Fusiones y refundaciones.</strong> Un club crece, se encoge o
        desaparece, pero dos clubes no se unen y uno desaparecido no se refunda.
      </li>
      <li>
        <strong>Mercado de fichajes, derechos de televisión y traspasos.</strong>
        Sin ellos, la escala de un club profesional de este simulador se queda
        por debajo de la realidad: recauda como un semiprofesional grande.
      </li>
      <li>
        <strong>Rutas de clasificación a copas.</strong> Se registran; no extraen
        participantes todavía.
      </li>
      <li>
        <strong>Consecuencias económicas del ascenso más allá del presupuesto.</strong>
        Al cambiar de categoría se reescala el presupuesto y se mueve la
        reputación, con su procedencia anotada; no hay renegociación de
        contratos, ni ventas, ni ajuste de plantilla.
      </li>
      <li>
        <strong>La escala profesional.</strong> Faltan los ingresos que dominan
        ese nivel —derechos de televisión nacionales, traspasos, explotación
        comercial—, así que un club profesional sale más modesto de lo que sería.
        No se finge ninguno: no hay partida que los represente.
      </li>
      <li>
        <strong>Evolución económica de los clubes en el tiempo.</strong> Las
        cuentas se calculan al generar la competición y al cambiar de categoría;
        todavía no hay temporada a temporada con ingresos cobrados, impagos,
        patrocinadores que llegan y se van o clubes que desaparecen.
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
  <h2>Quién decide qué</h2>
  <p class="small">
    Esta frontera es el contrato del producto. <strong>Tú defines</strong> el
    nombre, la clase y el territorio de la competición, su modalidad de
    participación, las edades admitidas, los requisitos verificables de admisión
    —licencia, seguridad, aforo mínimo—, las normas económicas de la liga, el
    calendario, el reglamento deportivo y los vínculos con otras competiciones.
    <strong>El motor decide</strong> qué clubes existen, quién los gobierna, si
    tienen propietario, en qué campo juegan, cuánto dinero reúnen y en qué se lo
    gastan, quién cobra y quién es voluntario, y qué jugadores atraen del mercado
    compartido. No hay un panel avanzado donde eso se pueda tocar: la API
    rechaza esos campos con un código propio.
  </p>
</div>

<div class="panel">
  <h2>De dónde salen los datos</h2>
  <p class="small">
    Los nombres de países, estados y ciudades y sus coordenadas son datos
    públicos. Las poblaciones son <strong>estimaciones de orden de magnitud</strong>
    con su año declarado: sirven para escalar mercados, no para citarse como
    censo. Los índices de economía, cultura beisbolística, coste e infraestructura
    son <strong>heurísticas propias</strong> en escala relativa, y son calibrables.
    Cada país lleva además un <strong>ancla monetaria</strong>: su moneda de curso
    legal y el gasto mensual de referencia de un hogar, estimado y con año
    declarado. Es el único punto donde los índices se convierten en importes, de
    modo que cualquier presupuesto se puede leer como «tantos meses de gasto
    doméstico»; un territorio sin ancla produce cuentas sin cifra en vez de una
    cantidad inventada.
    Las subzonas de ciudad, los clubes, las personas, los estadios y los escudos
    son <strong>ficticios</strong>: no corresponden a nada real y no usan ninguna
    marca existente. Cada dato lleva su etiqueta en la interfaz.
  </p>
</div>
