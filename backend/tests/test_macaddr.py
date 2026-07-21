from app.scanner.macaddr import (
    is_locally_administered,
    is_multicast,
    normalize_mac,
    oui_key,
)


class TestNormalizeMac:
    def test_acepta_los_formatos_habituales(self):
        esperado = "48:96:d9:de:76:e7"
        assert normalize_mac("48-96-D9-DE-76-E7") == esperado
        assert normalize_mac("48:96:d9:de:76:e7") == esperado
        assert normalize_mac("4896.d9de.76e7") == esperado
        assert normalize_mac("4896D9DE76E7") == esperado

    def test_rechaza_entradas_invalidas(self):
        assert normalize_mac(None) is None
        assert normalize_mac("") is None
        assert normalize_mac("48:96:d9") is None
        assert normalize_mac("no-es-una-mac") is None

    def test_descarta_macs_que_no_son_de_un_dispositivo(self):
        # El broadcast y la MAC nula aparecen en la tabla ARP pero no son hosts.
        assert normalize_mac("ff:ff:ff:ff:ff:ff") is None
        assert normalize_mac("00:00:00:00:00:00") is None


def test_oui_key_extrae_el_prefijo_del_fabricante():
    assert oui_key("48:96:d9:de:76:e7") == "4896D9"


class TestBitsDeLaMac:
    def test_detecta_mac_aleatoria(self):
        # El segundo bit menos significativo del primer octeto marca las MAC
        # administradas localmente, que es lo que usan los móviles por privacidad.
        assert is_locally_administered("02:00:00:00:00:01")
        assert is_locally_administered("da:a1:19:00:00:01")
        assert not is_locally_administered("48:96:d9:de:76:e7")

    def test_detecta_multicast(self):
        assert is_multicast("01:00:5e:00:00:16")
        assert not is_multicast("48:96:d9:de:76:e7")
