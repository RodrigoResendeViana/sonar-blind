import pytest

from sonar_api.paradas import CadastroParadas, normalizar_linha


def test_lista_paradas(cliente):
    paradas = cliente.get("/paradas").json()
    assert "demo" in [p["id"] for p in paradas]


def test_parada_mais_proxima(cliente):
    corpo = cliente.get("/paradas/proxima", params={"lat": -23.5425, "lon": -46.4713}).json()
    assert corpo["parada"]["id"] == "demo"
    assert corpo["distancia_m"] < 50


def test_previsao_da_parada_demo(cliente):
    corpo = cliente.get("/paradas/demo/previsao").json()
    assert corpo["fonte"] == "demonstracao"
    assert {v["linha"] for v in corpo["veiculos"]} == {"DEMO-10", "DEMO-20"}


def test_previsao_de_parada_inexistente(cliente):
    assert cliente.get("/paradas/nao-existe/previsao").status_code == 404


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("8000-10", "8000-10"), ("8000 10", "8000-10"), ("971d-10", "971D-10"), ("800010", "8000-10"), ("8000", None), ("", None)],
)
def test_normalizar_linha(entrada, esperado):
    assert normalizar_linha(entrada) == esperado


def test_cadastro_rejeita_id_invalido(tmp_path):
    arquivo = tmp_path / "paradas.json"
    arquivo.write_text('[{"id": "Parada Errada", "nome": "x"}]', encoding="utf-8")
    with pytest.raises(ValueError):
        CadastroParadas.carregar(str(arquivo))
