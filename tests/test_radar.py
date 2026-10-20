"""Testes com dados simulados (não acessam a internet)."""

from radar import arte, comparar, config, telegram, tmdb


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
    assert all(posts.cabe_no_x(p.texto) for p in lista)
    assert "em Netflix e Prime Video" in lista[1].texto  # mesmo título em 2 plataformas
    assert "Obscuro" not in lista[0].texto               # filtro de relevância
    assert "Saiu da Netflix" in lista[-1].texto
    assert "Drama" in lista[1].texto
    for p in lista:
        assert (tmp_path / p.imagem.split("/")[-1]).stat().st_size > 10_000


def test_resumo_corta_para_caber_no_x():
    itens = [{"t": "Um Título Bem Comprido Número %d" % i, "plataforma": "Paramount+"} for i in range(7)]
    texto = posts.texto_resumo(itens)
    assert posts.cabe_no_x(texto) and texto.endswith("🍿")


# ---------------------------------------------------------------- Fase 3
from radar import publicar


def test_publicar_so_redes_com_secrets(monkeypatch, tmp_path):
    for k in ("THREADS_TOKEN", "INSTAGRAM_TOKEN", "X_API_KEY", "X_API_SECRET",
              "X_ACCESS_TOKEN", "X_ACCESS_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("THREADS_TOKEN", "t")
    chamadas = []
    monkeypatch.setattr(publicar, "hospedar", lambda c, d: "https://exemplo/img.jpg")
    monkeypatch.setattr(publicar, "threads", lambda u, t, topico=None: chamadas.append(("threads", u, topico)) or "1")
    monkeypatch.setattr(publicar, "x", lambda c, t: chamadas.append(("x", c)) or "1")
    lista = [posts.Post("alerta", "a.jpg", "oi"), posts.Post("alerta", "b.jpg", "oi")]
    r = publicar.publicar_todos(lista, dt.date(2026, 10, 9), {"threads": 1})
    assert r == {"threads": {"ok": 1, "erros": []}}
    assert chamadas == [("threads", "https://exemplo/img.jpg", "Streaming")]


def test_erro_numa_rede_nao_derruba_outra(monkeypatch):
    monkeypatch.setenv("THREADS_TOKEN", "t")
    monkeypatch.setenv("INSTAGRAM_TOKEN", "i")
    monkeypatch.setattr(publicar, "hospedar", lambda c, d: "https://exemplo/img.jpg")
    monkeypatch.setattr(publicar, "threads", lambda u, t, topico=None: (_ for _ in ()).throw(RuntimeError("caiu")))
    monkeypatch.setattr(publicar, "instagram", lambda u, t: "1")
    r = publicar.publicar_todos([posts.Post("alerta", "a.jpg", "oi")], dt.date(2026, 10, 9))
    assert r["instagram"]["ok"] == 1 and r["threads"]["erros"] == ["caiu"]


# ---------------------------------------------------------------- Indicação
from radar import indicacao


class ClienteFalso:
    def __init__(self):
        self.chamadas = []

    def resolver_plataformas(self):
        return {"Netflix": 8, "Prime Video": 119}, []

    def get(self, caminho, params=None):
        self.chamadas.append((caminho, params))
        if caminho == "/discover/movie":
            return {"total_pages": 1, "results": [{"id": 1, "title": "Já Indicado"},
                                                  {"id": 2, "title": "Novo"}]}
        if caminho.endswith("/watch/providers"):
            return {"results": {"BR": {"flatrate": [{"provider_id": 119}]}}}
        return {"title": "Até o Último Homem", "release_date": "2016-11-04", "vote_average": 8.1,
                "vote_count": 14000, "genres": [{"name": "Guerra"}, {"name": "Drama"}],
                "runtime": 139, "overview": "A história real de um médico do exército " * 8}


def test_indicacao_sexta_guerra_sem_repetir(monkeypatch, tmp_path):
    monkeypatch.setattr(indicacao, "ARQUIVO_HISTORICO", str(tmp_path / "h.json"))
    indicacao.salvar_historico([{"id": 1}])
    c = ClienteFalso()
    filme = indicacao.escolher(c, 4, dt.date(2026, 10, 9))
    assert filme["id"] == 2 and filme["plataformas"] == ["Prime Video"]
    busca = next(p for cam, p in c.chamadas if cam == "/discover/movie")
    assert busca["with_genres"] == "10752" and busca["with_keywords"] == "9672"
    post = indicacao.montar(filme, dt.date(2026, 10, 9), str(tmp_path))
    assert post.texto.startswith("🎖️ Sexta de guerra: Até o Último Homem (2016)")
    assert "baseado em fatos reais" in post.texto and "Prime Video" in post.texto
    assert posts.cabe_no_x(post.texto) and post.texto.endswith("🍿")
    indicacao.registrar(filme, dt.date(2026, 10, 9))
    assert [h["id"] for h in indicacao.carregar_historico()] == [1, 2]


def test_indicacao_so_no_fim_de_semana():
    assert indicacao.escolher(ClienteFalso(), 2, dt.date(2026, 10, 7)) is None


def test_indicacao_reserva_nao_afirma_fatos_reais(monkeypatch, tmp_path):
    monkeypatch.setattr(indicacao, "ARQUIVO_HISTORICO", str(tmp_path / "h.json"))

    class SoReserva(ClienteFalso):
        def get(self, caminho, params=None):
            if caminho == "/discover/movie" and params.get("with_keywords"):
                return {"total_pages": 1, "results": []}
            return super().get(caminho, params)

    filme = indicacao.escolher(SoReserva(), 4, dt.date(2026, 10, 9))
    assert filme["fatos_reais"] is False
    texto = indicacao.texto(filme)
    assert "fatos reais" not in texto and "mergulho na história" in texto


# ---------------------------------------------------------------- Reels e tópicos
import shutil
import subprocess

import pytest

from radar import reels


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")
def test_reel_vertical_com_audio(tmp_path):
    imgs = []
    for i in range(3):
        c = tmp_path / f"p{i}.jpg"
        arte.post_alerta({"chave": f"movie:{i}", "t": f"Filme {i}", "a": "2024", "n": 7.5, "v": 100},
                         "Netflix", dt.date(2026, 10, 13), str(c))
        imgs.append(str(c))
    video = reels.gerar(imgs, dt.date(2026, 10, 13), str(tmp_path / "r.mp4"))
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_name,width,height:format=duration", "-of", "csv=p=0", video],
                          capture_output=True, text=True).stdout
    assert "h264,1080,1920" in info and "aac" in info
    dur = float(info.strip().splitlines()[-1])
    assert 10 < dur < 16


def test_topico_do_threads_por_tipo(tmp_path):
    dif = {"Netflix": {"entrou": [{"chave": "movie:1", "t": "A", "a": "2024", "p": 50, "n": 7, "v": 99, "g": []},
                                  {"chave": "movie:2", "t": "B", "a": "2024", "p": 40, "n": 7, "v": 99, "g": []},
                                  {"chave": "movie:3", "t": "C", "a": "2024", "p": 30, "n": 7, "v": 99, "g": []}],
                       "saiu": [], "suspeito": False}}
    lista = posts.montar(dif, {}, dt.date(2026, 10, 13), str(tmp_path))
    assert lista[0].topico == "Streaming" and lista[1].topico == "Netflix"


# ---------------------------------------------------------------- Sugestões
from radar import sugestoes


def test_sugestoes_filtra_e_monta_resposta(monkeypatch, tmp_path):
    for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"):
        monkeypatch.setenv(k, "x")
    arq = tmp_path / "n.json"
    arq.write_text('{"2026-10-13": [{"t": "Duna: Parte Dois", "plataformas": ["HBO Max"], "p": 90}]}',
                   encoding="utf-8")

    class Resp:
        ok = True
        def json(self):
            return {"data": [{"id": "1", "author_id": "a", "text": "Vale ver Duna?",
                              "public_metrics": {"like_count": 300}},
                             {"id": "2", "author_id": "b", "text": "duna", "public_metrics": {"like_count": 1}}],
                    "includes": {"users": [{"id": "a", "username": "cinefilo",
                                            "public_metrics": {"followers_count": 50000}},
                                           {"id": "b", "username": "ninguem",
                                            "public_metrics": {"followers_count": 10}}]}}

    monkeypatch.setattr(sugestoes.requests, "get", lambda *a, **k: Resp())
    lista = sugestoes.montar(str(arq), dt.date(2026, 10, 13))
    assert len(lista) == 1 and lista[0]["autor"] == "cinefilo"
    assert "na HBO Max" in lista[0]["resposta"]
    assert "x.com/cinefilo/status/1" in sugestoes.mensagem(lista)


# ---------------------------------------------------------------- Agenda do Threads
from radar import agenda, relatorio


def _entradas():
    base = [("Duna: Parte Dois", 90), ("Um Título Bem Comprido Demais Pra Enquete", 80),
            ("Rota 66", 70), ("Maré Alta", 60), ("Verão", 50)]
    return [{"chave": f"movie:{i}", "t": t, "a": "2024", "p": p, "n": 7.8, "v": 500, "g": [],
             "plataformas": ["Netflix"], "plataforma": "Netflix"} for i, (t, p) in enumerate(base)]


class TMDBSinopse:
    def get(self, caminho, params=None):
        return {"overview": "Uma história " * 60}


def test_montar_dia_fio_enquete_dica_e_previa(tmp_path):
    lista = [posts.Post("resumo", "r.jpg", "📡 resumo"), posts.Post("alerta", "a1.jpg", "a1", "Netflix"),
             posts.Post("alerta", "a2.jpg", "a2", "Netflix"), posts.Post("alerta", "a3.jpg", "a3", "Netflix"),
             posts.Post("saiu", "s.jpg", "s", "Netflix")]
    sexta = dt.date(2026, 10, 23)
    fio, itens = agenda.montar_dia(lista, _entradas(), TMDBSinopse(), sexta, com_reel=True)
    assert fio["textos"][0] == "📡 resumo" and len(fio["textos"]) == 6
    assert fio["textos"][1].startswith("1/5 🎬 Duna: Parte Dois (2024)")
    assert agenda.CHAMADA_REEL in fio["textos"][-1]
    assert all(len(t.encode()) <= 500 for t in fio["textos"])
    tipos = [i["tipo"] for i in itens]
    assert tipos.count("alerta") == 3 and "previa_indicacao" in tipos and "enquete" in tipos
    assert tipos[-1] == "dica" and "dica" in itens[-1]["texto"].lower()
    enquete = next(i for i in itens if i["tipo"] == "enquete")
    assert all(len(v) <= 25 for v in enquete["poll"].values()) and len(enquete["poll"]) == 4
    assert next(i for i in itens if i["tipo"] == "dica")["quando"].startswith("2026-10-23T21:00")


def test_domingo_gancho_top10(tmp_path):
    lista = [posts.Post("alerta", "a1.jpg", "a1", "Netflix")]
    domingo = dt.date(2026, 10, 25)
    _, itens = agenda.montar_dia(lista, _entradas(), TMDBSinopse(), domingo, False, top_semana=_entradas())
    gancho = next(i for i in itens if i["tipo"] == "gancho_top10")
    assert "top 10 completo tá no nosso Insta @radardatela" in gancho["texto"]


def test_fila_publica_so_vencidos(monkeypatch, tmp_path):
    monkeypatch.setattr(agenda, "ARQUIVO_FILA", str(tmp_path / "fila.json"))
    monkeypatch.setattr(agenda, "ARQUIVO_LOG", str(tmp_path / "log.json"))
    hoje = dt.date(2026, 10, 20)
    agenda.enfileirar([
        {"quando": agenda._quando(hoje, "almoco"), "tipo": "alerta", "texto": "a", "imagem": "x.jpg"},
        {"quando": agenda._quando(hoje, "dica"), "tipo": "dica", "texto": "d"},
    ], hoje, hospedar_fn=lambda c, d: "https://img/x.jpg")
    feitos = []
    agora = dt.datetime(2026, 10, 20, 12, 25, tzinfo=agenda.FUSO)
    ok, erros = agenda.publicar_vencidos(agora, lambda item: feitos.append(item) or f"id{len(feitos)}")
    assert ok == {"threads": 1} and not erros and feitos[0]["imagem_url"] == "https://img/x.jpg"
    assert [f["tipo"] for f in agenda._ler(agenda.ARQUIVO_FILA, [])] == ["dica"]
    assert agenda._ler(agenda.ARQUIVO_LOG, [])[0]["tipo"] == "alerta"


def test_top10_e_relatorio(monkeypatch, tmp_path):
    arq = tmp_path / "n.json"
    arq.write_text('{"2026-10-20": [{"t": "A", "plataformas": ["Netflix"], "p": 9, "tipo": "movie"},'
                   '{"t": "B", "plataformas": ["HBO Max"], "p": 99, "tipo": "tv"}]}', encoding="utf-8")
    top = agenda.top_da_semana(str(arq), dt.date(2026, 10, 25))
    assert [t["t"] for t in top] == ["B", "A"]
    imgs = agenda.imagens_top10(top, dt.date(2026, 10, 25), str(tmp_path / "top"))
    assert len(imgs) == 2
    dados = {"seguidores": {"instagram": 120, "threads": 340}, "anterior": {"instagram": 100, "threads": 300},
             "sem_permissao": False,
             "posts": [{"tipo": "enquete", "quando": "2026-10-20T19:00", "views": 900, "likes": 30, "replies": 12,
                        "engaj": 54},
                       {"tipo": "alerta", "quando": "2026-10-20T12:20", "views": 300, "likes": 5, "replies": 0,
                        "engaj": 5}]}
    texto = relatorio.mensagem(dados)
    assert "Instagram: 120 (+20 na semana)" in texto and "Threads: 340 (+40 na semana)" in texto
    assert "Melhor horário</b>: início da noite" in texto and "1. Enquete" in texto


def test_x_limitado_a_3():
    assert config.LIMITE_POSTS_POR_REDE["x"] == 3


def test_fila_instagram_carrossel_e_reel(monkeypatch, tmp_path):
    monkeypatch.setattr(agenda, "ARQUIVO_FILA", str(tmp_path / "fila.json"))
    monkeypatch.setattr(agenda, "ARQUIVO_LOG", str(tmp_path / "log.json"))
    hoje = dt.date(2026, 10, 21)
    agenda.enfileirar([
        {"quando": agenda._quando(hoje, "almoco"), "rede": "instagram", "tipo": "carrossel",
         "imagens": ["a.jpg", "b.jpg"], "texto": "legenda"},
        {"quando": agenda._quando(hoje, "noite"), "rede": "instagram", "tipo": "reel",
         "video": "r.mp4", "texto": "legenda"},
    ], hoje, hospedar_fn=lambda c, d: f"https://m/{c}")
    fila = agenda._ler(agenda.ARQUIVO_FILA, [])
    assert fila[0]["imagens_url"] == ["https://m/a.jpg", "https://m/b.jpg"]
    assert fila[1]["video_url"] == "https://m/r.mp4"
    meio_dia = dt.datetime(2026, 10, 21, 12, 30, tzinfo=agenda.FUSO)
    ok, _ = agenda.publicar_vencidos(meio_dia, lambda item: "ig1")
    assert ok == {"instagram": 1}
    assert [f["tipo"] for f in agenda._ler(agenda.ARQUIVO_FILA, [])] == ["reel"]
    assert agenda._ler(agenda.ARQUIVO_LOG, []) == []  # só o Threads entra no registro


def test_chamada_reel_avisa_horario():
    assert "19h" in agenda.CHAMADA_REEL


def test_gancho_top10_no_x_cabe_e_chama_insta():
    top = [{"t": "Um Título Extremamente Comprido Que Não Acaba Mais Nunca " * 2, "plataformas": ["Paramount+"]}] * 3
    texto = agenda.gancho_top10_x(top)
    assert posts.cabe_no_x(texto) and "top 10 completo tá no nosso Insta (@radardatela)" in texto
    assert texto.count("\n1. ") == 1 and "3. " in texto


# ---------------------------------------------------------------- Saídas falsas
import radar.__main__ as principal


def test_saida_falsa_nao_e_anunciada():
    mk2 = {"t": "Mortal Kombat 2", "a": "2026", "p": 51.4, "n": 6.5, "v": 900, "g": []}
    velho = {"t": "Saiu Mesmo", "a": "2010", "p": 30, "n": 7, "v": 900, "g": []}
    anterior = {"HBO Max": {"movie:1": mk2, "movie:2": velho, "movie:3": {**velho, "t": "Fica"}}}
    atual = {"HBO Max": {"movie:3": {**velho, "t": "Fica"}}}

    class Cli:
        def disponivel(self, chave, pid):
            return chave == "movie:1"  # MK2 ainda está na HBO Max

    avisos = principal.confirmar_saidas(Cli(), anterior, atual, {"HBO Max": 1899})
    dif = comparar.comparar(anterior, atual)
    assert [i["t"] for i in dif["HBO Max"]["saiu"]] == ["Saiu Mesmo"]
    assert "movie:1" in atual["HBO Max"] and "Mortal Kombat 2" in avisos[0]


def test_retorno_recente_nao_vira_novidade(monkeypatch, tmp_path):
    monkeypatch.setattr(principal, "ARQUIVO_SAIDAS", str(tmp_path / "s.json"))
    (tmp_path / "s.json").write_text('{"HBO Max": {"movie:1": "2026-10-20"}}', encoding="utf-8")
    dif = {"HBO Max": {"entrou": [{"chave": "movie:1", "t": "Mortal Kombat 2", "p": 51},
                                  {"chave": "movie:9", "t": "Novo", "p": 20}],
                       "saiu": [{"chave": "movie:5", "t": "Foi", "p": 3}], "suspeito": False}}
    avisos = principal.filtrar_retornos(dif, dt.date(2026, 10, 21))
    assert [i["t"] for i in dif["HBO Max"]["entrou"]] == ["Novo"] and "Mortal Kombat 2" in avisos[0]
    import json as _j
    assert "movie:5" in _j.loads((tmp_path / "s.json").read_text())["HBO Max"]
