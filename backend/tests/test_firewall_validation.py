import pytest

from app.services.firewall import FirewallError, _validate_port_spec


class TestValidacionDePuertos:
    def test_acepta_las_formas_validas(self):
        assert _validate_port_spec("8080") == "8080"
        assert _validate_port_spec("80,443") == "80,443"
        assert _validate_port_spec("8000-8100") == "8000-8100"
        assert _validate_port_spec(" 80, 443 ") == "80,443"

    @pytest.mark.parametrize(
        "entrada",
        [
            "8080; Remove-Item C:\\",  # inyección de comandos en PowerShell
            "80 | Get-Process",
            "$(whoami)",
            "80-90-100",
            "abc",
            "",
        ],
    )
    def test_rechaza_lo_que_no_son_puertos(self, entrada):
        # La especificación se interpola en un comando de PowerShell, así que
        # esta validación es lo que impide que un valor de la API ejecute otra cosa.
        with pytest.raises(FirewallError):
            _validate_port_spec(entrada)

    @pytest.mark.parametrize("entrada", ["0", "65536", "99999"])
    def test_rechaza_puertos_fuera_de_rango(self, entrada):
        with pytest.raises(FirewallError):
            _validate_port_spec(entrada)
