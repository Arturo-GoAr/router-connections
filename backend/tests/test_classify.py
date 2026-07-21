from app.models import DeviceCategory
from app.scanner.classify import Evidence, classify


class TestGateway:
    def test_el_gateway_se_clasifica_como_router(self):
        result = classify(Evidence(mac="48:96:d9:de:76:e7", is_gateway=True))
        assert result.category == DeviceCategory.ROUTER

    def test_gateway_con_tr069_se_identifica_como_modem_del_isp(self):
        # El puerto 7547 es el canal de gestión remota que usa el operador; solo
        # lo expone el equipo que administra el ISP.
        result = classify(
            Evidence(
                mac="48:96:d9:de:76:e7",
                vendor="zte corporation",
                is_gateway=True,
                open_ports=[80, 443, 7547],
            )
        )
        assert result.category == DeviceCategory.MODEM

    def test_en_cascada_el_primer_salto_es_tu_router(self):
        result = classify(
            Evidence(
                mac="60:cf:84:f3:6b:ba",
                is_gateway=True,
                topology_kind="cascade",
                hop_index=0,
            )
        )
        assert result.category == DeviceCategory.ROUTER


class TestPuertos:
    def test_puertos_de_impresion_identifican_una_impresora(self):
        result = classify(Evidence(mac="00:11:22:33:44:55", open_ports=[9100, 631]))
        assert result.category == DeviceCategory.PRINTER
        assert result.confidence > 0.6

    def test_servicios_de_windows_sugieren_un_pc(self):
        result = classify(Evidence(mac="10:ff:e0:da:fa:82", open_ports=[135, 139, 445]))
        assert result.category == DeviceCategory.PC


class TestSenalesDeDescubrimiento:
    def test_un_mediarenderer_upnp_es_una_tv(self):
        result = classify(
            Evidence(
                mac="c8:a6:ef:71:4a:2a",
                friendly_name="Samsung 6 Series",
                upnp_device_types=["urn:schemas-upnp-org:device:MediaRenderer:1"],
            )
        )
        assert result.category == DeviceCategory.TV

    def test_servicio_mdns_de_impresion_identifica_impresora(self):
        result = classify(
            Evidence(mac="00:11:22:33:44:55", mdns_services=["_ipp._tcp.local."])
        )
        assert result.category == DeviceCategory.PRINTER

    def test_equipo_de_red_que_no_es_gateway_se_marca_como_punto_de_acceso(self):
        result = classify(
            Evidence(
                mac="60:cf:84:f3:6b:ba",
                hostname="RT-AX55-Router",
                vendor="ASUSTek COMPUTER INC.",
                is_gateway=False,
            )
        )
        assert result.category in {
            DeviceCategory.ACCESS_POINT,
            DeviceCategory.ROUTER,
        }


class TestSinIndicios:
    def test_un_dispositivo_mudo_se_reporta_como_desconocido(self):
        result = classify(Evidence(mac="aa:bb:cc:dd:ee:ff"))
        assert result.category == DeviceCategory.UNKNOWN
        assert result.confidence == 0.0
        # La honestidad importa: si no se sabe, hay que decirlo.
        assert "sin indicios" in result.reason_text

    def test_este_equipo_siempre_se_reconoce(self):
        result = classify(Evidence(mac="cc:28:aa:05:bf:2c", is_self=True))
        assert result.category == DeviceCategory.PC
        assert result.confidence > 0.7
