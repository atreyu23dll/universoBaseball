<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api/client';
  import { formatDate, formatPct } from '$lib/format';
  import ConfidenceTag from '$lib/components/ConfidenceTag.svelte';
  import ErrorNotice from '$lib/components/ErrorNotice.svelte';

  const personId = $derived($page.params.id);
  let person = $state<any>(null);
  let error = $state<unknown>(null);

  onMount(async () => {
    try {
      person = await api.get<any>(`/people/${personId}`);
    } catch (err) {
      error = err;
    }
  });

  const GROUP_LABEL: Record<string, string> = {
    batting: 'Bateo',
    pitching: 'Pitcheo',
    fielding: 'Defensa',
    physical: 'Físico',
    cognition: 'Cognición'
  };
  const ATTR_LABEL: Record<string, string> = {
    contact: 'contacto', power: 'potencia', discipline: 'disciplina',
    strikeout_avoidance: 'evitar el ponche', speed: 'velocidad',
    stuff: 'calidad de lanzamientos', control: 'control', movement: 'movimiento',
    stamina: 'resistencia', hold_runners: 'control de corredores',
    range: 'rango', hands: 'manos', arm: 'brazo',
    durability: 'durabilidad', recovery: 'recuperación', acceleration: 'aceleración',
    composure: 'temple', competitiveness: 'competitividad', work_ethic: 'trabajo',
    risk_tolerance: 'tolerancia al riesgo', sociability: 'sociabilidad', learning: 'aprendizaje'
  };
</script>

<ErrorNotice {error} />

{#if person}
  <div class="spread" style="margin-bottom:16px">
    <div>
      <h1 style="margin-bottom:2px">{person.name}</h1>
      <p class="muted small" style="margin:0">
        {person.age} años · {person.primary_position}
        {#if person.pitcher_role}({person.pitcher_role}){/if}
        · batea {person.bats} / lanza {person.throws}
        · {person.height_cm} cm, {person.weight_kg} kg
        · nacido el {formatDate(person.birth_date)} en {person.origin?.name}
        {#if person.origin}<ConfidenceTag confidence={person.origin.confidence} />{/if}
      </p>
    </div>
    {#if person.club}
      <div class="stat">
        <div class="value" style="font-size:15px">
          <a href={`/clubes/${person.club.id}`}>{person.club.name}</a>
        </div>
        <div class="label">club actual</div>
      </div>
    {/if}
  </div>

  <div class="grid sidebar">
    <div>
      {#if person.batting_totals}
        <div class="panel">
          <h2>Bateo</h2>
          <table>
            <thead>
              <tr>
                <th class="num">J</th><th class="num">AP</th><th class="num">VB</th>
                <th class="num">H</th><th class="num">2B</th><th class="num">3B</th>
                <th class="num">HR</th><th class="num">C</th><th class="num">CP</th>
                <th class="num">BB</th><th class="num">K</th><th class="num">BR</th>
                <th class="num">AVG</th><th class="num">OBP</th><th class="num">SLG</th><th class="num">OPS</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="num">{person.batting_totals.games}</td>
                <td class="num">{person.batting_totals.plate_appearances}</td>
                <td class="num">{person.batting_totals.at_bats}</td>
                <td class="num">{person.batting_totals.hits}</td>
                <td class="num">{person.batting_totals.doubles}</td>
                <td class="num">{person.batting_totals.triples}</td>
                <td class="num">{person.batting_totals.home_runs}</td>
                <td class="num">{person.batting_totals.runs}</td>
                <td class="num">{person.batting_totals.runs_batted_in}</td>
                <td class="num">{person.batting_totals.walks}</td>
                <td class="num">{person.batting_totals.strikeouts}</td>
                <td class="num">{person.batting_totals.stolen_bases}</td>
                <td class="num">{formatPct(person.batting_totals.avg)}</td>
                <td class="num">{formatPct(person.batting_totals.obp)}</td>
                <td class="num">{formatPct(person.batting_totals.slg)}</td>
                <td class="num">{formatPct(person.batting_totals.ops)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      {/if}

      {#if person.pitching_totals}
        <div class="panel">
          <h2>Pitcheo</h2>
          <table>
            <thead>
              <tr>
                <th class="num">J</th><th class="num">JI</th><th class="num">IP</th>
                <th class="num">H</th><th class="num">C</th><th class="num">CL</th>
                <th class="num">BB</th><th class="num">K</th><th class="num">HR</th>
                <th class="num">G</th><th class="num">P</th><th class="num">SV</th>
                <th class="num">ERA</th><th class="num">WHIP</th><th class="num">K/9</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="num">{person.pitching_totals.games}</td>
                <td class="num">{person.pitching_totals.games_started}</td>
                <td class="num">{person.pitching_totals.innings}</td>
                <td class="num">{person.pitching_totals.hits_allowed}</td>
                <td class="num">{person.pitching_totals.runs_allowed}</td>
                <td class="num">{person.pitching_totals.earned_runs}</td>
                <td class="num">{person.pitching_totals.walks}</td>
                <td class="num">{person.pitching_totals.strikeouts}</td>
                <td class="num">{person.pitching_totals.home_runs_allowed}</td>
                <td class="num">{person.pitching_totals.wins}</td>
                <td class="num">{person.pitching_totals.losses}</td>
                <td class="num">{person.pitching_totals.saves}</td>
                <td class="num">{person.pitching_totals.era}</td>
                <td class="num">{person.pitching_totals.whip}</td>
                <td class="num">{person.pitching_totals.k_per_9}</td>
              </tr>
            </tbody>
          </table>
        </div>
      {/if}

      {#if !person.batting_totals && !person.pitching_totals}
        <div class="panel">
          <p class="muted small">
            Todavía no ha jugado ningún partido, así que no hay estadísticas. No
            se muestran números inventados.
          </p>
        </div>
      {/if}
    </div>

    <div>
      <div class="panel">
        <h2>Informe de scouting</h2>
        <div class="stat" style="margin-bottom:10px">
          <div class="value">{person.scouting.scouted_potential?.toFixed(2)}</div>
          <div class="label">proyección observada</div>
        </div>
        <p class="small muted">{person.scouting.note}</p>
      </div>

      {#each Object.entries(person.attributes) as [group, values]}
        <div class="panel">
          <h2>{GROUP_LABEL[group] ?? group}</h2>
          {#each Object.entries(values as Record<string, number>) as [key, value]}
            <div style="margin-bottom:6px">
              <div class="spread small">
                <span>{ATTR_LABEL[key] ?? key}</span>
                <span class="mono">{value.toFixed(2)}</span>
              </div>
              <div style="height:4px;background:var(--panel-2);border-radius:2px;overflow:hidden">
                <div style={`height:100%;width:${Math.round(value * 100)}%;background:var(--accent)`}></div>
              </div>
            </div>
          {/each}
        </div>
      {/each}
    </div>
  </div>
{:else if !error}
  <p class="muted">Cargando persona…</p>
{/if}
