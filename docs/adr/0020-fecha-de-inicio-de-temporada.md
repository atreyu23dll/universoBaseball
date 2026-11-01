# ADR 0020 — La temporada empieza el día que se declara

- **Fecha:** 1 de noviembre de 2026
- **Estado:** aceptado e implementado
- **Contexto:** petición del usuario: «podemos definir también una fecha de
  inicio de temporada, actualmente todas las ligas comienzan cuando se crean…
  aunque el final lo marca el calendario que el motor decide»; y «debemos tener
  cuidado con si una liga es dependiente de otra, ver cómo van a cuadrar sus
  fechas»

## Problema

El calendario de una competición arrancaba **el día del mundo**:

```python
start = world_date + timedelta(days=ruleset.season.start_date_offset_days)
```

`start_date_offset_days` existía, pero no había ningún control que lo moviera:
en la práctica toda liga empezaba el día en que se pulsaba «crear». Eso tiene
tres consecuencias:

1. No se puede fundar una liga en noviembre para que **debute en abril**, que
   es como se funda una liga de verdad.
2. Dos competiciones creadas con minutos de diferencia arrancan en días
   distintos sin que nadie lo haya decidido.
3. El paso de calendario del asistente contaba partidos, jornadas y días, pero
   no decía **cuándo** se juega. Un recuento no se parece a un calendario.

## Decisiones

### D1 — `season.start_date`: el día de la jornada inaugural, y sólo ese

`SeasonRules` gana un campo `start_date: date | None`. Declara el **arranque**.
No hay campo para el final, y no lo habrá: el último día sale del calendario
que el motor construye con las vueltas, los partidos por serie, los días entre
series y los días cerrados de la semana. Pedir también el final sería pedir dos
números que pueden contradecirse.

Sin fecha, el comportamiento es exactamente el de antes —día del mundo más el
desplazamiento—, así que ningún reglamento ya guardado cambia de significado.

### D2 — Un solo sitio donde se decide: `SeasonRules.opening()`

```python
def opening(self, world_date, *, season=None, earliest=None) -> date
```

- **Primera edición** (`season=None`): la fecha tal cual la escribió el usuario.
- **Ediciones siguientes** (`season=<año>`): su **aniversario**. Una liga que
  debuta el 4 de mayo de 2042 abre la de 2043 el 4 de mayo de 2043, que es como
  arranca una liga año tras año. El 29 de febrero de un año común cae al 1 de
  marzo.
- **`earliest`**: el suelo que impone la pausa entre temporadas. Si la anterior
  terminó tarde y el aniversario ya pasó, manda el suelo.
- Nunca se programa un partido antes del día del mundo: una temporada no puede
  empezar en el pasado, ni siquiera si el usuario escribe una fecha vieja.

El método vive en el reglamento, no en el servicio, porque lo usan tres sitios:
la generación del mundo (`simulation/generation/world.py`), la apertura de la
temporada siguiente (`season_service.open_next_edition`) y la previsualización
del asistente.

### D3 — Una escalera arranca junta

Dos competiciones que intercambian plazas no pueden resolver el ascenso y el
descenso hasta que **las dos** hayan terminado. Si la superior empieza el 1 de
abril y su filial el 15 de marzo, la filial juega dos semanas sola y el
intercambio espera igual.

`process_season_boundaries` calcula ahora `_ladder_start`: el arranque de cada
miembro de la escalera y se queda con **el más tardío**. Todos los miembros
abren su edición ese día. Con un solo miembro no hay nada que cuadrar y cada
competición usa su propia fecha.

Es una regla del motor, no un aviso: el usuario no tiene que acordarse de
alinear dos fechas a mano.

### D4 — El asistente enseña un calendario, no una cuenta

`POST /schedule/preview` devuelve `calendar`: los días con partido, cada uno
con **sus cruces** (`home`, `away`, división y tipo de enfrentamiento), más
`calendar_complete` y los días cerrados de la semana. La pregunta que alguien
hace mirando un calendario no es «cuántos partidos hay el sábado», es «quién
juega el sábado».

El componente `SeasonCalendar.svelte` lo dibuja mes a mes, con sus semanas de
lunes a domingo, los días cerrados en gris, los días con partido marcados con
su número de encuentros y un panel que lista la jornada del día elegido.

Tope: `MAX_CALENDAR_DAYS = 200` días con partido. Es una previsualización del
asistente, no el acta de la temporada; si se pasa, se dice.

## Consecuencias

- Una liga puede fundarse hoy y debutar dentro de cinco meses.
- Las competiciones vinculadas arrancan el mismo día sin que nadie lo gestione.
- El paso de calendario del asistente se puede **mirar**: se ve que se juega de
  martes a domingo, que mayo está lleno y que la temporada termina el 13 de
  abril porque lo dice el calendario, no porque alguien lo haya escrito.
- `start_date_offset_days` sigue existiendo para el caso sin fecha declarada.
  No se retira: es lo que hace que un reglamento viejo signifique lo mismo.

## Alternativas descartadas

- **Pedir también la fecha de final.** Dos números que pueden no cuadrar con el
  calendario real. El motor ya sabe cuándo termina.
- **Mandar el calendario entero de la temporada a la vista.** Una liga larga de
  treinta clubes son miles de partidos en una pantalla que todavía no tiene
  clubes con nombre.
- **Avisar al usuario de que dos ligas vinculadas no cuadran.** Un aviso deja
  el trabajo en sus manos; la escalera arranca junta por regla.
