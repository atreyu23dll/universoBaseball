"""C03 (parte) — el RNG es determinista y está separado por contexto."""

from __future__ import annotations

from simulation.core.rng import clamped_normal, derive_seed, rng_for, weighted_choice


def test_misma_ruta_misma_semilla():
    assert derive_seed(7, "clubs", 3) == derive_seed(7, "clubs", 3)


def test_rutas_distintas_semillas_distintas():
    assert derive_seed(7, "clubs", 3) != derive_seed(7, "clubs", 4)
    assert derive_seed(7, "clubs", 3) != derive_seed(8, "clubs", 3)


def test_rutas_no_colisionan_por_concatenacion():
    """("a", "bc") y ("ab", "c") no deben dar la misma semilla."""
    assert derive_seed(1, "a", "bc") != derive_seed(1, "ab", "c")


def test_semilla_cabe_en_bigint_con_signo():
    """Se persiste en BIGINT; por encima de 2^63-1 no se puede guardar."""
    for i in range(300):
        assert 0 <= derive_seed(i, "game", i * 31) <= 2**63 - 1


def test_flujos_independientes_no_se_desplazan():
    """Consumir de un contexto no mueve a los demás.

    Es la propiedad que justifica derivar por contexto: añadir una opción a la
    interfaz que genere un atributo más no debe cambiar el futuro de todo.
    """
    antes = [rng_for(5, "club", i).random() for i in range(5)]
    ruido = rng_for(5, "otro_contexto")
    for _ in range(1000):
        ruido.random()
    despues = [rng_for(5, "club", i).random() for i in range(5)]
    assert antes == despues


def test_clamped_normal_respeta_limites():
    rng = rng_for(1, "attrs")
    for _ in range(2000):
        value = clamped_normal(rng, 0.5, 0.4, 0.1, 0.9)
        assert 0.1 <= value <= 0.9


def test_weighted_choice_respeta_pesos():
    rng = rng_for(2, "weights")
    counts = {"a": 0, "b": 0}
    for _ in range(4000):
        counts[weighted_choice(rng, [("a", 9.0), ("b", 1.0)])] += 1  # type: ignore[index]
    assert counts["a"] > counts["b"] * 5


def test_weighted_choice_rechaza_pesos_vacios():
    rng = rng_for(3, "weights")
    try:
        weighted_choice(rng, [("a", 0.0)])
    except ValueError:
        return
    raise AssertionError("se esperaba ValueError con todos los pesos a cero")
