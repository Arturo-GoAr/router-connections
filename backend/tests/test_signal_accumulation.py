"""Regresión: la clasificación no debe empeorar cuando un barrido ve menos.

Caso real que motivó estas pruebas: un televisor Samsung se identificó
correctamente por SSDP en el primer barrido, pero al apagarse dejó de
responder y los barridos siguientes lo reclasificaron como "teléfono" usando
solo el fabricante de la MAC. La categoría se degradaba con el tiempo.
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Device, DeviceCategory, DeviceSignal, utcnow
from app.scanner import orchestrator
from app.scanner.classify import Evidence, classify
from app.scanner.discovery import DiscoveryInfo


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def tv(session):
    device = Device(mac="c8:a6:ef:71:4a:2a", ip="192.168.1.17")
    session.add(device)
    session.flush()
    return device


# Lo que la TV anunció realmente por SSDP cuando estaba encendida.
TV_ENCENDIDA = DiscoveryInfo(
    ip="192.168.1.17",
    friendly_name='65" Crystal UHD',
    model="UN65DU8200FXZX",
    upnp_device_types=["urn:schemas-upnp-org:device:MediaRenderer:1"],
    server_banners=["Linux/9.0 UPnP/1.0 Samsung/1.0"],
)

# Lo que se ve de esa misma TV una vez apagada: nada.
TV_APAGADA = DiscoveryInfo(ip="192.168.1.17")


class TestAlmacenamientoDeSenales:
    def test_guarda_las_senales_observadas(self, session, tv):
        orchestrator._store_signals(session, tv, TV_ENCENDIDA, utcnow())
        session.flush()

        signals = session.exec(
            select(DeviceSignal).where(DeviceSignal.device_id == tv.id)
        ).all()
        kinds = {signal.kind for signal in signals}
        assert kinds == {"upnp", "banner"}

    def test_no_duplica_una_senal_ya_conocida(self, session, tv):
        orchestrator._store_signals(session, tv, TV_ENCENDIDA, utcnow())
        session.flush()
        orchestrator._store_signals(session, tv, TV_ENCENDIDA, utcnow())
        session.flush()

        signals = session.exec(
            select(DeviceSignal).where(DeviceSignal.device_id == tv.id)
        ).all()
        assert len(signals) == 2  # un upnp y un banner, no cuatro

    def test_un_barrido_sin_senales_no_borra_las_anteriores(self, session, tv):
        orchestrator._store_signals(session, tv, TV_ENCENDIDA, utcnow())
        session.flush()
        orchestrator._store_signals(session, tv, TV_APAGADA, utcnow())
        session.flush()

        assert len(orchestrator._load_signals(session, tv)["upnp"]) == 1

    def test_load_signals_agrupa_por_tipo(self, session, tv):
        orchestrator._store_signals(session, tv, TV_ENCENDIDA, utcnow())
        session.flush()

        signals = orchestrator._load_signals(session, tv)
        assert signals["upnp"] == ["urn:schemas-upnp-org:device:MediaRenderer:1"]
        assert signals["mdns"] == []


class TestLaCategoriaNoSeDegrada:
    def test_con_senales_frescas_la_tv_se_identifica(self):
        result = classify(
            Evidence(
                mac="c8:a6:ef:71:4a:2a",
                vendor="Samsung Electronics Co.,Ltd",
                friendly_name='65" Crystal UHD',
                upnp_device_types=["urn:schemas-upnp-org:device:MediaRenderer:1"],
            )
        )
        assert result.category == DeviceCategory.TV

    def test_sin_senales_el_fabricante_solo_no_basta_y_acierta_mal(self):
        # Esto documenta el fallo original: con solo el fabricante Samsung, la
        # heurística se inclina por teléfono. Por eso hay que persistir señales.
        result = classify(
            Evidence(mac="c8:a6:ef:71:4a:2a", vendor="Samsung Electronics Co.,Ltd")
        )
        assert result.category == DeviceCategory.PHONE

    def test_las_senales_persistidas_mantienen_la_tv_tras_apagarse(
        self, session, tv
    ):
        # Barrido 1: la TV está encendida y se descubre por SSDP.
        orchestrator._store_signals(session, tv, TV_ENCENDIDA, utcnow())
        session.flush()

        # Barrido 2: la TV está apagada y no aporta nada nuevo.
        orchestrator._store_signals(session, tv, TV_APAGADA, utcnow())
        session.flush()

        signals = orchestrator._load_signals(session, tv)
        result = classify(
            Evidence(
                mac=tv.mac,
                vendor="Samsung Electronics Co.,Ltd",
                friendly_name='65" Crystal UHD',
                upnp_device_types=signals["upnp"],
                mdns_services=signals["mdns"],
                server_banners=signals["banner"],
            )
        )
        assert result.category == DeviceCategory.TV

    def test_el_nombre_comercial_por_si_solo_identifica_la_tv(self):
        # Refuerzo: aunque se perdieran las señales, "Crystal UHD" es una línea
        # de televisores y el propio aparato lo anuncia.
        result = classify(
            Evidence(
                mac="c8:a6:ef:71:4a:2a",
                vendor="Samsung Electronics Co.,Ltd",
                friendly_name='65" Crystal UHD',
            )
        )
        assert result.category == DeviceCategory.TV
