import zipfile

from sonar_api.planejador import descrever, planejar
from sonar_api.rede import carregar_demo, carregar_gtfs, termos


def test_termos_sem_acento_e_com_abreviacoes_da_sptrans():
    assert termos("TERM. LAPA") == ["terminal", "lapa"]
    assert termos("Hospital das Clínicas") == ["hospital", "clinicas"]


def test_lugar_por_apelido():
    rede = carregar_demo()
    assert rede.procurar_lugar("pronto socorro")[0][0].nome == "Hospital Exemplo"
    assert rede.procurar_lugar("a FIAP")[0][0].nome == "Universidade Exemplo"
    assert rede.procurar_lugar("aeroporto") == []


def _planos(rede, destino):
    lugar = rede.procurar_lugar(destino)[0][0]
    origens = [(rede.pontos["demo"], 80.0)]
    return planejar(rede, origens, rede.proximos(lugar.lat, lugar.lon, 600))


def test_viagem_direta():
    plano = _planos(carregar_demo(), "terminal")[0]
    assert [t.linha for t in plano.trechos] == ["DEMO-10"]
    assert plano.trechos[0].desembarque.nome == "Terminal Exemplo"
    assert plano.trechos[0].paradas == 3


def test_viagem_com_baldeacao():
    plano = _planos(carregar_demo(), "hospital")[0]
    assert [t.linha for t in plano.trechos] == ["DEMO-20", "DEMO-30"]
    assert plano.trechos[0].desembarque.id == plano.trechos[1].embarque.id == "ex-centro"
    fala = descrever(plano, "Hospital Exemplo")
    assert "Pegue o DEMO-20" in fala and "Lá, pegue o DEMO-30" in fala and "no ponto Hospital Exemplo" in fala


def test_nao_anda_na_contramao():
    rede = carregar_demo()
    origens = [(rede.pontos["ex-terminal"], 0.0)]
    plano = planejar(rede, origens, [(rede.pontos["ex-escola"], 0.0)])[0]
    assert plano.trechos[0].destino == "Itaquera (exemplo)"  # a volta do DEMO-10, não a ida


def _gtfs(caminho):
    arquivos = {
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n"
        "1001,PCA. RAMOS DE AZEVEDO,-23.5450,-46.6380\n1002,AV. SAO JOAO,-23.5400,-46.6450\n"
        "1003,TERM. LAPA,-23.5230,-46.7040\n1004,R. CLELIA,-23.5260,-46.6900\n",
        "routes.txt": "route_id,route_short_name\n8000-10,8000-10\n",
        "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id\n"
        "8000-10,USD,8000-10-0,TERM. LAPA,0\n8000-10,USD,8000-10-1,PCA. RAMOS DE AZEVEDO,1\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "8000-10-0,06:00:00,06:00:00,1001,1\n8000-10-0,06:05:00,06:05:00,1002,2\n"
        "8000-10-0,06:20:00,06:20:00,1004,3\n8000-10-0,06:25:00,06:25:00,1003,4\n"
        "8000-10-1,07:00:00,07:00:00,1003,1\n8000-10-1,07:20:00,07:20:00,1002,2\n8000-10-1,07:30:00,07:30:00,1001,3\n",
    }
    with zipfile.ZipFile(caminho, "w") as arquivo:
        for nome, conteudo in arquivos.items():
            arquivo.writestr(nome, conteudo)
    return caminho


def test_gtfs_vira_rede_com_padroes_por_sentido(tmp_path):
    rede = carregar_gtfs(str(_gtfs(tmp_path / "gtfs.zip")))
    assert rede.fonte == "gtfs"
    assert len(rede.padroes) == 2
    assert rede.pontos["1003"].codigo_sptrans == 1003
    assert rede.procurar_lugar("terminal lapa")[0][0].nome == "Terminal Lapa"
    perto = rede.proximos(-23.5452, -46.6382, 300)
    assert perto[0][0].id == "1001"
    plano = planejar(rede, perto, rede.proximos(-23.5231, -46.7041, 300))[0]
    assert plano.trechos[0].linha == "8000-10" and plano.trechos[0].paradas == 3
