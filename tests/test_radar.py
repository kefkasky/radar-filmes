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


# ---------------------------------------------------------------- Fase 2
import datetime as dt

from radar import posts


def test_posts_selecao_legendas_e_imagens(tmp_path):
    def it(chave, t, p, v=500, n=7.5, g=("18",)):
        return {"chave": chave, "t": t, "a": "2024", "p": p, "n": n, "v": v, "g": list(g)}

    dif = {
        "Netflix": {"entrou": [it("movie:1", "Filme Famoso", 80), it("movie:9", "Obscuro", 1, v=3)],
                    "saiu": [it("tv:5", "Série Antiga", 30)], "suspeito": False},
        "Prime Video": {"entrou": [it("movie:1", "Filme Famoso", 80), it("movie:2", "Outro", 40),
                                   it("tv:3", "Série Nova " * 6, 20)], "saiu": [], "suspeito": False},
        "Globoplay": {"base_inicial": True, "total": 10},
    }
    lista = posts.montar(dif, {"18": "Drama"}, dt.date(2026, 10, 9), str(tmp_path))
    tipos = [p.tipo for p in lista]
    assert tipos == ["resumo", "alerta", "alerta", "alerta", "saiu"]
    assert all(len(p.texto) <= posts.LIMITE_X for p in lista)
    assert "em Netflix e Prime Video" in lista[1].texto  # mesmo título em 2 plataformas
    assert "Obscuro" not in lista[0].texto               # filtro de relevância
    assert "Saiu da Netflix" in lista[-1].texto
    assert "Drama" in lista[1].texto
    for p in lista:
        assert (tmp_path / p.imagem.split("/")[-1]).stat().st_size > 10_000


def test_resumo_corta_para_caber_no_x():
    itens = [{"t": "Um Título Bem Comprido Número %d" % i, "plataforma": "Paramount+"} for i in range(7)]
    texto = posts.texto_resumo(itens)
    assert len(texto) <= posts.LIMITE_X and texto.endswith("🍿")


# ---------------------------------------------------------------- Fase 3
from radar import publicar


def test_publicar_so_redes_com_secrets(monkeypatch, tmp_path):
    for k in ("THREADS_TOKEN", "INSTAGRAM_TOKEN", "X_API_KEY", "X_API_SECRET",
              "X_ACCESS_TOKEN", "X_ACCESS_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("THREADS_TOKEN", "t")
    chamadas = []
    monkeypatch.setattr(publicar, "hospedar", lambda c, d: "https://exemplo/img.jpg")
    monkeypatch.setattr(publicar, "threads", lambda u, t: chamadas.append(("threads", u)) or "1")
    monkeypatch.setattr(publicar, "x", lambda c, t: chamadas.append(("x", c)) or "1")
    lista = [posts.Post("alerta", "a.jpg", "oi"), posts.Post("alerta", "b.jpg", "oi")]
    r = publicar.publicar_todos(lista, dt.date(2026, 10, 9), {"threads": 1})
    assert r == {"threads": {"ok": 1, "erros": []}}
    assert chamadas == [("threads", "https://exemplo/img.jpg")]


def test_erro_numa_rede_nao_derruba_outra(monkeypatch):
    monkeypatch.setenv("THREADS_TOKEN", "t")
    monkeypatch.setenv("INSTAGRAM_TOKEN", "i")
    monkeypatch.setattr(publicar, "hospedar", lambda c, d: "https://exemplo/img.jpg")
    monkeypatch.setattr(publicar, "threads", lambda u, t: (_ for _ in ()).throw(RuntimeError("caiu")))
    monkeypatch.setattr(publicar, "instagram", lambda u, t: "1")
    r = publicar.publicar_todos([posts.Post("alerta", "a.jpg", "oi")], dt.date(2026, 10, 9))
    assert r["instagram"]["ok"] == 1 and r["threads"]["erros"] == ["caiu"]
