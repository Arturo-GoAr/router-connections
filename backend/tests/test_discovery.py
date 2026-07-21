import struct

from app.scanner.discovery import (
    build_nbstat_query,
    parse_nbstat_response,
    parse_ssdp_headers,
)

RESPUESTA_SSDP = (
    "HTTP/1.1 200 OK\r\n"
    "CACHE-CONTROL: max-age=1800\r\n"
    "LOCATION: http://192.168.1.1:5000/rootDesc.xml\r\n"
    "SERVER: Linux/3.10 UPnP/1.0 MiniUPnPd/2.1\r\n"
    "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
    "\r\n"
)


class TestSsdp:
    def test_extrae_las_cabeceras_en_minusculas(self):
        headers = parse_ssdp_headers(RESPUESTA_SSDP)
        assert headers["location"] == "http://192.168.1.1:5000/rootDesc.xml"
        assert headers["st"] == "urn:schemas-upnp-org:device:InternetGatewayDevice:1"

    def test_ignora_la_linea_de_estado(self):
        assert "http/1.1 200 ok" not in parse_ssdp_headers(RESPUESTA_SSDP)


def _respuesta_nbstat(nombre: str, sufijo: int = 0x00, flags: int = 0x0400) -> bytes:
    """Construye una respuesta NBSTAT sintética para probar el parser."""
    header = struct.pack(">HHHHHH", 0x4E42, 0x8400, 0, 1, 0, 0)
    encoded_name = b"\x20" + b"A" * 32 + b"\x00"
    rr = struct.pack(">HHIH", 0x0021, 0x0001, 0, 100)
    cuerpo = bytes([1]) + nombre.ljust(15).encode("ascii") + bytes([sufijo])
    cuerpo += struct.pack(">H", flags)
    cuerpo += b"\x00" * 46  # estadísticas del adaptador, que no usamos
    return header + encoded_name + rr + cuerpo


class TestNetbios:
    def test_la_consulta_tiene_la_forma_esperada(self):
        query = build_nbstat_query()
        # 12 de cabecera + 1 de longitud + 32 del nombre + 1 nulo + 4 de tipo/clase
        assert len(query) == 50
        assert query[-4:] == struct.pack(">HH", 0x0021, 0x0001)

    def test_extrae_el_nombre_del_equipo(self):
        assert parse_nbstat_response(_respuesta_nbstat("THEEZIOMI")) == "THEEZIOMI"

    def test_ignora_los_nombres_de_grupo(self):
        # Los nombres de grupo (bit 0x8000) son el workgroup, no el equipo.
        assert parse_nbstat_response(_respuesta_nbstat("WORKGROUP", flags=0x8400)) is None

    def test_tolera_respuestas_truncadas(self):
        assert parse_nbstat_response(b"") is None
        assert parse_nbstat_response(b"\x00" * 20) is None
