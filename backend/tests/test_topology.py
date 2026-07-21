from app.scanner.netinfo import classify_topology, parse_traceroute

# Salida real de `tracert -d` en un Windows en español, con el equipo colgando
# directamente del router del ISP y CGNAT por encima.
TRACERT_DIRECTO = """
Traza a 8.8.8.8 sobre caminos de 5 saltos como maximo.

  1    <1 ms    <1 ms    <1 ms  192.168.1.1
  2     1 ms     1 ms     1 ms  100.69.44.155
  3     4 ms     2 ms     1 ms  100.69.44.153
  4     1 ms     1 ms     1 ms  201.174.73.213
  5     2 ms     1 ms     1 ms  187.251.2.112

Traza completa.
"""

# Dos routers privados encadenados: el clásico doble NAT.
TRACERT_CASCADA = """
  1     1 ms     1 ms     1 ms  192.168.0.1
  2     2 ms     2 ms     2 ms  192.168.1.1
  3     8 ms     9 ms     8 ms  10.20.30.1
  4    12 ms    11 ms    12 ms  200.10.1.1
"""

TRACERT_SIN_RESPUESTA = """
  1     *        *        *     Tiempo de espera agotado para esta solicitud.
  2     *        *        *     Tiempo de espera agotado para esta solicitud.
"""


class TestParseTraceroute:
    def test_extrae_saltos_con_ip_y_latencia(self):
        hops = parse_traceroute(TRACERT_DIRECTO, max_hops=5)
        assert len(hops) == 5
        assert hops[0].ip == "192.168.1.1"
        assert hops[0].rtt_ms == 1.0
        assert hops[4].ip == "187.251.2.112"

    def test_conserva_los_saltos_sin_respuesta(self):
        hops = parse_traceroute(TRACERT_SIN_RESPUESTA, max_hops=5)
        assert len(hops) == 2
        assert all(hop.ip is None for hop in hops)

    def test_ignora_lineas_de_texto(self):
        # El parser no debe depender del idioma de Windows.
        hops = parse_traceroute(TRACERT_DIRECTO, max_hops=5)
        assert all(hop.ttl <= 5 for hop in hops)


class TestClassifyTopology:
    def test_un_solo_salto_privado_es_conexion_directa(self):
        topology = classify_topology(parse_traceroute(TRACERT_DIRECTO, 5))
        assert topology.kind == "direct"
        assert topology.private_hops == ["192.168.1.1"]

    def test_detecta_cgnat_del_operador(self):
        topology = classify_topology(parse_traceroute(TRACERT_DIRECTO, 5))
        assert topology.behind_cgnat is True
        assert "CGNAT" in topology.summary

    def test_dos_saltos_privados_son_doble_nat(self):
        topology = classify_topology(parse_traceroute(TRACERT_CASCADA, 5))
        assert topology.kind == "cascade"
        assert topology.private_hops == ["192.168.0.1", "192.168.1.1", "10.20.30.1"]
        assert "cascada" in topology.summary

    def test_sin_saltos_utiles_no_inventa_una_topologia(self):
        topology = classify_topology(parse_traceroute(TRACERT_SIN_RESPUESTA, 5))
        assert topology.kind == "unknown"
        assert topology.private_hops == []
