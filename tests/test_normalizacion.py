import pytest

from catastro_noa.texto import clave, limpiar, numero
from catastro_noa.titulares import clave_titular, titular_publicado
from catastro_noa.tramites import ClasificadorTramites

T = ClasificadorTramites()


@pytest.mark.parametrize("a, b", [
    ("LITHIUM S. CORPORATION S. A.", "LITHIUM S CORPORATION S.A."),
    ("HECTOR FIAD SOCIEDAD DE RESPONSABILIDAD LIMITADA", "Hector Fiad S.R.L."),
    ("JUJUY ENERGIA Y MINERIA SOCIEDAD DEL ESTADO", "Jujuy Energía y Minería S.E."),
    ("AUSTROID ARGENTINA RESOURCES S.A.U.", "AUSTROID ARGENTINA RESOURCES S. A. U."),
])
def test_titulares_equivalentes(a, b):
    assert clave_titular(a) == clave_titular(b)


def test_siglas():
    assert clave_titular("Y.M.A.D.") == "YMAD"


@pytest.mark.parametrize("v", ["Vacancia Solicitada", "----------", None])
def test_no_titulares(v):
    assert clave_titular(v) is None
    assert titular_publicado(v) is None


def test_texto():
    assert limpiar("  ALUVION DE ORO Y \nESTAÑO ") == "ALUVION DE ORO Y ESTAÑO"
    assert clave("Doña  Pancha.") == "DONA PANCHA"
    assert numero("22,4675 ha") == 22.4675
    assert numero("2400,0000 ha") == 2400.0
    assert numero(4978.6) == 4978.6
    assert numero("sin dato") is None


@pytest.mark.parametrize("prov, tramite, adm, proy", [
    ("jujuy", "CATEO", "Cateo", "Exploración"),
    ("jujuy", "SOLICITUD DE MINA", "Solicitud de mina", "Exploración"),
    ("jujuy", "MINA CONCEDIDA", "Mina concedida", "Explotación"),
    ("jujuy", "SOLIC. GRUPO MINERO", "Solicitud de grupo minero", "Canteras y otros"),
    ("salta", "Manifestacion", "Manifestación", "Exploración"),
    ("salta", "Mina", "Mina", "Explotación"),
    ("salta", "Convenio", "Convenio", "Canteras y otros"),
    ("catamarca", None, None, None),
    ("salta", "Algo nuevo", None, None),
])
def test_etapas(prov, tramite, adm, proy):
    assert T.etapa(prov, tramite) == (adm, proy)


@pytest.mark.parametrize("prov, estado, esperado", [
    ("jujuy", "EN TRAMITE", "En trámite"),
    ("jujuy", "CONCEDIDA - MENSURADA", "Vigente"),
    ("jujuy", "INCLUIDA EN G. M. AGUILAR", "Vigente"),
    ("jujuy", "Res 62-J-2026 (18/ 08/ 2026)", "Otro"),
    ("salta", "Vigente", "Vigente"),
    ("salta", "Anulación de registro sin publicar (REMSa)", "Anulado"),
])
def test_estados(prov, estado, esperado):
    assert T.estado(prov, estado) == esperado
