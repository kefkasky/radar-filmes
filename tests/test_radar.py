"""Testes com dados simulados (não acessam a internet)."""

from radar import comparar, telegram, tmdb


def item(titulo, pop, nota=7.5, votos=100, ano="2024"):
    return {"t": titulo, "a": ano, "p": pop, "n": nota, "v": votos}


def test_base_inicial():
    atual = {"Netflix": {"movie:1": item("A", 10)}}
    dif = comparar.comparar({}, atual)
    assert dif["Netflix"]["base_inicial"]
    texto = comparar.montar_relatorio(dif, [], "08/10/2026")
    assert "Primeira coleta" in texto


def test_entrou_e_saiu_ordenado_por_popularidade():
    antes = {"Netflix": {"movie:1": item("Fica", 5), "movie:2": item("Sai", 3)}}
    hoje = {
        "Netflix": {
            "movie:1": item("Fica", 5),
            "movie:3": item("Pouco popular", 1),
            "tv:4": item("Série <nova>", 50),
        }
    }
    dif = comparar.comparar(antes, hoje)["Netflix"]
    assert [i["chave"] for i in dif["entrou"]] == ["tv:4", "movie:3"]
    assert [i["chave"] for i in dif["saiu"]] == ["movie:2"]
    texto = comparar.montar_relatorio({"Netflix": dif}, [], "08/10/2026")
    assert "Série &lt;nova&gt;" in texto  # escapado para o Telegram
    assert "Entraram 2" in texto and "Saíram 1" in texto


def test_trava_de_remocao_suspeita():
    antes = {"Max": {f"movie:{i}": item(f"F{i}", i) for i in range(100)}}
    hoje = {"Max": {"movie:0": item("F0", 0)}}
    dif = comparar.comparar(antes, hoje)
    assert dif["Max"]["suspeito"]
    salvo = comparar.aplicar_retrato(antes, hoje, dif)
    assert salvo["Max"] == antes["Max"]  # mantém o retrato anterior


def test_coleta_incompleta_nao_reporta_saidas():
    antes = {"Netflix": {"movie:1": item("A", 1), "movie:2": item("B", 2)}}
    hoje = {"Netflix": {"movie:1": item("A", 1), "movie:3": item("C", 3)}}
    dif = comparar.comparar(antes, hoje, {"Netflix"})
    assert dif["Netflix"]["saiu"] == []
    salvo = comparar.aplicar_retrato(antes, hoje, dif, {"Netflix"})
    assert set(salvo["Netflix"]) == {"movie:1", "movie:2", "movie:3"}


def test_plataforma_que_falhou_mantem_retrato():
    antes = {"Netflix": {"movie:1": item("A", 1)}, "Globoplay": {"tv:9": item("Z", 1)}}
    hoje = {"Netflix": {"movie:1": item("A", 1)}}
    dif = comparar.comparar(antes, hoje)
    salvo = comparar.aplicar_retrato(antes, hoje, dif)
    assert "Globoplay" in salvo


def test_divisao_de_mensagens_longas():
    texto = "\n".join(f"linha {i} " + "x" * 50 for i in range(500))
    partes = telegram.dividir(texto)
    assert len(partes) > 1
    assert all(len(p) <= telegram.LIMITE for p in partes)
    assert "\n".join(partes) == texto


def test_resolver_plataformas_por_apelido(monkeypatch):
    cliente = tmdb.ClienteTMDB("token-falso")
    monkeypatch.setattr(
        cliente,
        "provedores_brasil",
        lambda: {"netflix": 8, "hbo max": 1899, "globoplay": 307},
    )
    achadas, faltando = cliente.resolver_plataformas()
    assert achadas["HBO Max"] == 1899 and achadas["Netflix"] == 8
    assert "Disney+" in faltando


def test_catalogo_divide_quando_passa_de_500_paginas(monkeypatch):
    cliente = tmdb.ClienteTMDB("token-falso")
    chamadas = []

    def falso_get(caminho, params=None):
        chamadas.append(params)
        divide = "primary_release_date.gte" in params
        return {
            "total_pages": 1 if divide else 600,
            "results": [{"id": len(chamadas), "title": "X", "release_date": "2020-01-01",
                         "popularity": 1, "vote_average": 7, "vote_count": 30}],
        }

    monkeypatch.setattr(cliente, "get", falso_get)
    itens, incompleto = cliente.catalogo("movie", 8)
    assert not incompleto
    assert any("primary_release_date.gte" in c for c in chamadas)
    assert len(itens) > 1
