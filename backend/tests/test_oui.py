from app.scanner import oui

CSV_IEEE = """Registry,Assignment,Organization Name,Organization Address
MA-L,4896D9,zte corporation,Shenzhen
MA-L,C8A6EF,Samsung Electronics Co.\\,Ltd,Suwon
MA-L,60CF84,ASUSTek COMPUTER INC.,Taipei
"""


class TestParseIeeeCsv:
    def test_construye_el_indice_por_prefijo(self):
        registry = oui.parse_ieee_csv(CSV_IEEE)
        assert registry["4896D9"] == "zte corporation"
        assert registry["60CF84"] == "ASUSTek COMPUTER INC."

    def test_ignora_filas_incompletas(self):
        registry = oui.parse_ieee_csv(
            "Registry,Assignment,Organization Name\nMA-L,ABC,\nMA-L,,Vacio\n"
        )
        assert registry == {}


class TestLookup:
    def test_resuelve_un_fabricante_conocido(self, monkeypatch):
        monkeypatch.setattr(oui, "_registry", {"4896D9": "zte corporation"})
        assert oui.lookup("48:96:d9:de:76:e7") == "zte corporation"

    def test_no_adivina_fabricante_de_una_mac_aleatoria(self, monkeypatch):
        # Los móviles aleatorizan la MAC; el OUI resultante no significa nada y
        # devolver un fabricante sería inventárselo.
        monkeypatch.setattr(oui, "_registry", {"DAA119": "Alguien"})
        assert oui.lookup("da:a1:19:00:00:01") is None

    def test_devuelve_none_si_no_esta_en_el_catalogo(self, monkeypatch):
        monkeypatch.setattr(oui, "_registry", {})
        assert oui.lookup("48:96:d9:de:76:e7") is None
        assert oui.lookup(None) is None
