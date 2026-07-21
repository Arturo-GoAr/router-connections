from app.scanner.arp import parse_arp_output, sweep_targets
from app.scanner.netinfo import Interface

# Salida real de `arp -a` en Windows en español.
ARP_ES = """
Interfaz: 192.168.1.28 --- 0x9
  Direccion de Internet          Direccion fisica      Tipo
  192.168.1.1           48-96-d9-de-76-e7     dinamico
  192.168.1.25          10-ff-e0-da-fa-82     dinamico
  192.168.1.255         ff-ff-ff-ff-ff-ff     estatico
  224.0.0.22            01-00-5e-00-00-16     estatico
  239.255.255.250       01-00-5e-7f-ff-fa     estatico
"""


class TestParseArpOutput:
    def test_extrae_los_hosts_reales(self):
        entries = parse_arp_output(ARP_ES)
        ips = [entry.ip for entry in entries]
        assert ips == ["192.168.1.1", "192.168.1.25"]

    def test_normaliza_las_mac_a_dos_puntos(self):
        entries = parse_arp_output(ARP_ES)
        assert entries[0].mac == "48:96:d9:de:76:e7"

    def test_descarta_broadcast_y_multicast(self):
        # Esas entradas están siempre en la tabla ARP y no son dispositivos.
        macs = [entry.mac for entry in parse_arp_output(ARP_ES)]
        assert "ff:ff:ff:ff:ff:ff" not in macs
        assert not any(mac.startswith("01:00:5e") for mac in macs)

    def test_tolera_una_tabla_vacia(self):
        assert parse_arp_output("") == []


class TestSweepTargets:
    def test_cubre_la_subred_menos_el_propio_equipo(self):
        interface = Interface(name="test", ip="192.168.1.28", prefix_length=24)
        targets = sweep_targets(interface)
        assert len(targets) == 253  # 254 hosts de una /24 menos el nuestro
        assert "192.168.1.28" not in targets
        assert "192.168.1.1" in targets
        assert "192.168.1.254" in targets

    def test_no_incluye_red_ni_broadcast(self):
        interface = Interface(name="test", ip="192.168.1.28", prefix_length=24)
        targets = sweep_targets(interface)
        assert "192.168.1.0" not in targets
        assert "192.168.1.255" not in targets

    def test_limita_las_subredes_enormes(self):
        # Una /16 tiene 65534 hosts; barrerla entera no es razonable.
        interface = Interface(name="test", ip="10.0.0.5", prefix_length=16)
        assert len(sweep_targets(interface)) <= 4096
