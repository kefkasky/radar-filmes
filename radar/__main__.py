"""Execução diária do Radar de Filmes (Fase 1: só relatório, sem postar).

Uso:
    python -m radar            # coleta, compara e envia o relatório
    python -m radar chat-id    # mostra o ID do seu chat com o bot
    python -m radar previa     # manda posts de exemplo (com títulos reais)
    python -m radar indicacao [sexta|sabado|domingo] [--previa]  # indicação do fim de semana
"""

import datetime as dt
import html
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

from . import comparar, config, posts, telegram
from .tmdb import ClienteTMDB, ErroTMDB


def carregar_retrato() -> dict:
    if not os.path.exists(config.ARQUIVO_RETRATO):
        return {}
    with open(config.ARQUIVO_RETRATO, encoding="utf-8") as f:
        return json.load(f).get("plataformas", {})


def salvar_retrato(plataformas: dict, quando: str) -> None:
    os.makedirs(os.path.dirname(config.ARQUIVO_RETRATO), exist_ok=True)
    with open(config.ARQUIVO_RETRATO, "w", encoding="utf-8") as f:
        json.dump(
            {"atualizado_em": quando, "plataformas": plataformas},
            f,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def coletar(cliente: ClienteTMDB) -> tuple[dict, set, list[str]]:
    avisos: list[str] = []
    plataformas, faltando = cliente.resolver_plataformas()
    if faltando:
        avisos.append("Não encontradas no TMDB: " + ", ".join(faltando))

    atual, incompletas = {}, set()
    for nome, pid in plataformas.items():
        try:
            itens = {}
            for tipo in config.TIPOS:
                parte, incompleto = cliente.catalogo(tipo, pid)
                itens.update(parte)
                if incompleto:
                    incompletas.add(nome)
            atual[nome] = itens
            print(f"{nome}: {len(itens)} títulos")
        except Exception as e:  # uma plataforma com erro não derruba as outras
            avisos.append(f"{nome}: erro na coleta ({e})")
            traceback.print_exc()

    if incompletas:
        avisos.append(
            "Coleta parcial (catálogo grande demais) em: " + ", ".join(sorted(incompletas))
        )
    return atual, incompletas, avisos


def rodar() -> int:
    agora = dt.datetime.now(ZoneInfo("America/Sao_Paulo"))
    tg_token = os.environ.get("TELEGRAM_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    try:
        cliente = ClienteTMDB(os.environ.get("TMDB_TOKEN", ""))
        atual, incompletas, avisos = coletar(cliente)
    except ErroTMDB as e:
        anotar("error", str(e))
        telegram.enviar(tg_token, tg_chat, f"❌ Radar de Filmes: {e}")
        return 1

    if not atual:
        telegram.enviar(tg_token, tg_chat, "❌ Radar de Filmes: nenhuma plataforma coletada hoje.")
        return 1

    anterior = carregar_retrato()
    diferencas = comparar.comparar(anterior, atual, incompletas)
    relatorio = comparar.montar_relatorio(diferencas, avisos, agora.strftime("%d/%m/%Y"))
    print(relatorio)
    print(f"\nChamadas à API do TMDB: {cliente.chamadas}")

    novo = comparar.aplicar_retrato(anterior, atual, diferencas, incompletas)
    salvar_retrato(novo, agora.isoformat(timespec="minutes"))
    for aviso in avisos:
        anotar("warning", aviso)
    total = sum(len(v) for v in atual.values())
    anotar("notice", f"{len(atual)} plataformas, {total} titulos, {cliente.chamadas} chamadas TMDB")
    so_redes = os.environ.get("SO_REDES", "").strip().lower()
    refazendo = so_redes not in ("", "todas")  # republicação parcial: sem relatório/prévia
    if not refazendo:
        try:
            telegram.enviar(tg_token, tg_chat, relatorio)
        except Exception as e:  # relatório é só aviso: não impede os posts
            anotar("warning", f"Falha ao enviar o relatório no Telegram: {e}")

    # Fase 2: posts prontos para aprovação
    try:
        lista = posts.montar(diferencas, cliente.generos(), agora.date(), PASTA_POSTS)
        if not refazendo:
            enviar_posts(tg_token, tg_chat, lista)
    except Exception as e:
        anotar("error", f"Falha ao gerar/enviar posts: {e}")
        traceback.print_exc()
        return 1

    # Fase 3: publicação automática no canal do Telegram
    canal = os.environ.get("TELEGRAM_CANAL_ID", "").strip() or config.TELEGRAM_CANAL
    if canal and lista and (not refazendo or "telegram" in so_redes):
        try:
            for p in lista:
                telegram.enviar_foto(tg_token, canal, p.imagem, p.texto)
            anotar("notice", f"{len(lista)} posts publicados no canal do Telegram")
        except Exception as e:
            anotar("error", f"Falha ao publicar no canal: {e}")
            telegram.enviar(tg_token, tg_chat, f"❌ Falha ao publicar no canal: {e}")

    # Guarda as novidades do dia (sugestões de resposta e top 10 da semana)
    salvar_novidades(lista_novidades(diferencas), agora.date())

    # Instagram e X (o Threads segue a agenda do dia, abaixo)
    codigo = publicar_redes(tg_token, tg_chat, lista, agora.date(), excluir={"threads"})

    # Reel do dia no Instagram (maior alcance para quem ainda não segue)
    codigo_reel = publicar_reel_do_dia(tg_token, tg_chat, lista, agora.date())
    codigo = max(codigo, codigo_reel)

    # Domingo: Top 10 da semana, exclusivo do Instagram
    top = None
    if agora.weekday() == 6:
        codigo = max(codigo, publicar_top10(tg_token, tg_chat, agora.date()))
        from . import agenda
        top = agenda.top_da_semana(ARQUIVO_NOVIDADES, agora.date())

    # Threads: fio da manhã agora + agenda do dia
    codigo = max(codigo, agenda_threads(tg_token, tg_chat, lista, diferencas, cliente,
                                        agora.date(), com_reel=codigo_reel == 0, top=top))
    return codigo


def agenda_threads(tg_token, tg_chat, lista, diferencas, cliente, data, com_reel, top) -> int:
    from . import agenda, publicar

    if not publicar.redes_ativas().get("threads"):
        return 0
    try:
        generos = cliente.generos()
    except Exception:
        generos = {}
    entradas = [posts._com_generos(i, generos) for i in posts._juntar(diferencas, "entrou")]
    fio, agendados = agenda.montar_dia(lista, entradas, cliente, data, com_reel, top)
    erros = []
    if fio:
        try:
            url = publicar.hospedar(fio["imagem"], data)
            ids = publicar.threads_fio(fio["textos"], url_imagem=url, topico=fio["topico"])
            agenda.registrar_publicacao(ids[0], "resumo_fio")
            for mid in ids[1:]:
                agenda.registrar_publicacao(mid, "fio_resposta")
            anotar("notice", f"Threads: fio da manhã com {len(ids)} posts")
        except Exception as e:
            erros.append(f"fio: {e}")
    erros += agenda.enfileirar(agendados, data, publicar.hospedar)
    anotar("notice", f"Threads: {len(agendados)} posts agendados para o dia")
    for e in erros:
        anotar("error", f"Threads: {e}")
    if erros:
        telegram.enviar(tg_token, tg_chat, "⚠️ <b>Threads</b>\n" + "\n".join(html.escape(e[:200]) for e in erros))
    return 1 if erros else 0


def publicar_top10(tg_token, tg_chat, data) -> int:
    from . import agenda, publicar

    if not publicar.redes_ativas().get("instagram"):
        return 0
    top = agenda.top_da_semana(ARQUIVO_NOVIDADES, data)
    if len(top) < 5:
        anotar("notice", "Top 10: poucas novidades na semana, pulado")
        return 0
    try:
        imagens = agenda.imagens_top10(top, data, os.path.join(PASTA_POSTS, "top10"))
        urls = [publicar.hospedar(c, data) for c in imagens]
        publicar.instagram_carrossel(urls, agenda.legenda_top10(top) + config.HASHTAGS_INSTAGRAM)
        anotar("notice", f"Instagram: carrossel Top {len(top)} da semana publicado")
        return 0
    except Exception as e:
        anotar("error", f"Top 10: {e}")
        telegram.enviar(tg_token, tg_chat, f"⚠️ Top 10 da semana falhou: {html.escape(str(e)[:300])}")
        return 1


def semear_hoje() -> int:
    """Agenda para hoje a enquete (19h) e a dica (21h), com as novidades da manhã."""
    from . import agenda

    hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    try:
        with open(ARQUIVO_NOVIDADES, encoding="utf-8") as f:
            novidades = json.load(f).get(hoje.isoformat(), [])
    except (OSError, ValueError):
        novidades = []
    itens = []
    enquete = agenda.texto_enquete(novidades)
    if enquete:
        itens.append({"quando": agenda._quando(hoje, "noite"), "tipo": "enquete",
                      "texto": enquete[0], "poll": enquete[1], "topico": "Streaming"})
    itens.append({"quando": agenda._quando(hoje, "dica"), "tipo": "dica",
                  "texto": agenda.dica_do_dia(hoje), "topico": "Filmes"})
    agenda.enfileirar(itens, hoje)
    anotar("notice", "Agendado para hoje: " + ", ".join(i["tipo"] for i in itens))
    return 0


def rodar_fila() -> int:
    """Publica no Threads o que estiver agendado para este horário."""
    from . import agenda, publicar

    if not publicar.redes_ativas().get("threads"):
        return 0
    agora = dt.datetime.now(ZoneInfo("America/Sao_Paulo"))
    ok, erros = agenda.publicar_vencidos(agora, publicar.threads_publicar)
    anotar("notice", f"Threads: {ok} posts da agenda publicados")
    for e in erros:
        anotar("error", f"Threads: {e}")
    if erros:
        telegram.enviar(os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""),
                        "⚠️ <b>Agenda do Threads</b>\n" + "\n".join(html.escape(e) for e in erros))
    return 1 if erros else 0


def publicar_reel_do_dia(tg_token: str, tg_chat: str, lista: list, data) -> int:
    from . import publicar, reels

    fotos = [p for p in lista if p.tipo in ("resumo", "alerta")]
    if len(fotos) < 2 or not publicar.redes_ativas().get("instagram"):
        return 0
    legenda = next((p.texto for p in fotos if p.tipo == "resumo"), fotos[0].texto)
    try:
        video = reels.gerar([p.imagem for p in fotos], data, os.path.join(PASTA_POSTS, "reel.mp4"))
        publicar.publicar_reel(video, legenda, data)
        anotar("notice", "Instagram: Reel do dia publicado")
        return 0
    except Exception as e:
        anotar("error", f"Reel: {e}")
        telegram.enviar(tg_token, tg_chat, f"⚠️ Reel do dia falhou: {html.escape(str(e)[:300])}")
        return 1


ARQUIVO_NOVIDADES = os.path.join(os.path.dirname(config.ARQUIVO_RETRATO), "novidades.json")


def lista_novidades(diferencas: dict) -> list[dict]:
    itens = posts._juntar(diferencas, "entrou")[:15]
    return [{"t": i["t"], "a": i.get("a"), "plataformas": i["plataformas"], "p": i["p"],
             "tipo": i["chave"].split(":")[0], "chave": i["chave"], "n": i.get("n"),
             "v": i.get("v", 0)} for i in itens]


def salvar_novidades(itens: list[dict], data) -> None:
    """Mantém as novidades dos últimos 7 dias."""
    try:
        with open(ARQUIVO_NOVIDADES, encoding="utf-8") as f:
            todas = json.load(f)
    except (OSError, ValueError):
        todas = {}
    todas[data.isoformat()] = itens
    for d in sorted(todas)[:-7]:
        del todas[d]
    with open(ARQUIVO_NOVIDADES, "w", encoding="utf-8") as f:
        json.dump(todas, f, ensure_ascii=False, indent=1)


def publicar_redes(tg_token: str, tg_chat: str, lista: list, data, excluir: set | None = None) -> int:
    from . import publicar

    if not lista:
        return 0
    resultado = publicar.publicar_todos(lista, data, excluir=excluir)
    if not resultado:
        return 0
    linhas, falhou = ["📤 <b>Publicação nas redes</b>"], False
    for rede, r in resultado.items():
        nome = {"x": "X", "threads": "Threads", "instagram": "Instagram"}[rede]
        if r["erros"]:
            falhou = True
            linhas.append(f"⚠️ {nome}: {r['ok']} ok, {len(r['erros'])} erro(s)")
            linhas += [f"   • {html.escape(e)}" for e in r["erros"][:3]]
            for e in r["erros"]:
                anotar("error", f"{nome}: {e}")
        else:
            linhas.append(f"✅ {nome}: {r['ok']} posts")
            anotar("notice", f"{nome}: {r['ok']} posts publicados")
    telegram.enviar(tg_token, tg_chat, "\n".join(linhas))
    return 1 if falhou else 0


def renovar() -> int:
    from . import publicar

    msgs = publicar.renovar_tokens()
    for rede, m in msgs.items():
        anotar("warning" if "falha" in m else "notice", f"{rede}: {m}")
    alertas = [f"⚠️ {r}: {m}" for r, m in msgs.items() if "falha" in m]
    if alertas:
        telegram.enviar(os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""),
                        "🔑 <b>Tokens das redes</b>\n" + "\n".join(html.escape(a) for a in alertas))
    return 0


def testar_reel() -> int:
    """Gera e publica um Reel de teste com títulos reais do catálogo."""
    retrato = carregar_retrato()
    tg_token = os.environ.get("TELEGRAM_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    falso = {pl: {"entrou": sorted(({"chave": k, **v} for k, v in it.items()),
                                   key=lambda i: i["p"], reverse=True)[:1],
                  "saiu": [], "suspeito": False} for pl, it in retrato.items()}
    generos = {}
    try:
        generos = ClienteTMDB(os.environ.get("TMDB_TOKEN", "")).generos()
    except Exception:
        pass
    hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    lista = posts.montar(falso, generos, hoje, PASTA_POSTS)
    return publicar_reel_do_dia(tg_token, tg_chat, lista, hoje)


def testar_redes() -> int:
    """Publica UM post de exemplo (com título real) nas redes ativas."""
    retrato = carregar_retrato()
    tg_token = os.environ.get("TELEGRAM_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    falso = {}
    for plataforma, itens in retrato.items():
        ordem = sorted(({"chave": k, **v} for k, v in itens.items()), key=lambda i: i["p"], reverse=True)
        falso[plataforma] = {"entrou": ordem[:1], "saiu": [], "suspeito": False}
    generos = {}
    try:
        generos = ClienteTMDB(os.environ.get("TMDB_TOKEN", "")).generos()
    except Exception:
        pass
    hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    lista = [p for p in posts.montar(falso, generos, hoje, PASTA_POSTS) if p.tipo == "resumo"][:1]
    if not lista:
        anotar("error", "Não foi possível montar o post de teste.")
        return 1
    return publicar_redes(tg_token, tg_chat, lista, hoje)


def rodar_indicacao(dia_forcado: int | None = None, so_previa: bool = False) -> int:
    """Indicação de fim de semana (sexta/sábado/domingo)."""
    from . import indicacao

    tg_token = os.environ.get("TELEGRAM_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    dia = hoje.weekday() if dia_forcado is None else dia_forcado
    if dia not in indicacao.TEMAS:
        anotar("notice", "Hoje não é dia de indicação.")
        return 0
    cliente = ClienteTMDB(os.environ.get("TMDB_TOKEN", ""))
    filme = indicacao.escolher(cliente, dia, hoje)
    if not filme:
        anotar("error", "Nenhum filme encontrado para a indicação de hoje.")
        telegram.enviar(tg_token, tg_chat, "❌ Indicação do fim de semana: nenhum filme encontrado.")
        return 1
    post = indicacao.montar(filme, hoje, PASTA_POSTS)
    anotar("notice", f"Indicação: {filme['t']} ({filme['a']}) — {', '.join(filme['plataformas'])}"
           + (" — fatos reais confirmado" if filme.get('fatos_reais') else ""))

    if so_previa:
        telegram.enviar(tg_token, tg_chat, "🧪 <b>PRÉVIA da indicação</b> (nada foi publicado)")
        telegram.enviar_foto(tg_token, tg_chat, post.imagem, post.texto)
        return 0

    so_redes = os.environ.get("SO_REDES", "").strip().lower()
    canal = os.environ.get("TELEGRAM_CANAL_ID", "").strip() or config.TELEGRAM_CANAL
    if canal and so_redes in ("", "todas") or "telegram" in so_redes:
        try:
            telegram.enviar_foto(tg_token, canal, post.imagem, post.texto)
        except Exception as e:
            anotar("error", f"Falha ao publicar no canal: {e}")
    codigo = publicar_redes(tg_token, tg_chat, [post], hoje)
    indicacao.registrar(filme, hoje)
    return codigo


def rodar_sugestoes() -> int:
    from . import sugestoes

    hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    if not sugestoes.titulos_recentes(ARQUIVO_NOVIDADES):
        # ainda sem histórico: usa os títulos mais populares do catálogo
        retrato = carregar_retrato()
        falso = {pl: {"entrou": sorted(({"chave": k, **v} for k, v in it.items()),
                                       key=lambda i: i["p"], reverse=True)[:3],
                      "saiu": [], "suspeito": False} for pl, it in retrato.items()}
        salvar_novidades(lista_novidades(falso), hoje)
    lista = sugestoes.montar(ARQUIVO_NOVIDADES, hoje)
    telegram.enviar(os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""),
                    sugestoes.mensagem(lista))
    anotar("notice", f"{len(lista)} sugestões de resposta enviadas")
    return 0


def diagnosticar() -> int:
    """Testa os tokens da Meta e mostra o erro exato (sem exibir tokens)."""
    import requests

    testes = {
        "Instagram": ("INSTAGRAM_TOKEN", "https://graph.instagram.com/v23.0/me",
                      {"fields": "user_id,username,account_type"}),
        "Threads": ("THREADS_TOKEN", "https://graph.threads.net/v1.0/me",
                    {"fields": "id,username"}),
    }
    linhas = ["🩺 <b>Diagnóstico da Meta</b>"]
    for nome, (var, url, params) in testes.items():
        token = os.environ.get(var, "").strip()
        if not token:
            linhas.append(f"• {nome}: sem token")
            continue
        r = requests.get(url, params={**params, "access_token": token}, timeout=30)
        if r.ok:
            msg = f"OK, conectado como @{r.json().get('username', '?')}"
        else:
            e = r.json().get("error", {}) if r.headers.get("content-type", "").startswith("application/json") else {}
            msg = (f"ERRO {e.get('code', r.status_code)}/{e.get('error_subcode', '-')} "
                   f"({e.get('type', '?')}): {e.get('message', r.text[:200])}")
        anotar("notice" if r.ok else "error", f"{nome}: {msg}")
        linhas.append(f"• {nome}: {html.escape(msg)}")
    if os.environ.get("THREADS_TOKEN", "").strip():
        r = requests.get("https://graph.threads.net/v1.0/me/threads_insights",
                         params={"metric": "followers_count,views",
                                 "access_token": os.environ["THREADS_TOKEN"].strip()}, timeout=30)
        if r.ok:
            valores = {m["name"]: m.get("total_value", {}).get("value",
                       sum(v.get("value", 0) for v in m.get("values", []))) for m in r.json().get("data", [])}
            msg = (f"OK: {valores.get('followers_count', '?')} seguidores, "
                   f"{valores.get('views', '?')} visualizações (ontem-hoje)")
        else:
            msg = f"SEM ACESSO: {r.json().get('error', {}).get('message', r.text[:150])}"
        anotar("notice" if r.ok else "error", f"Threads insights: {msg}")
        linhas.append(f"• Threads insights: {html.escape(msg)}")
    telegram.enviar(os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""),
                    "\n".join(linhas))
    return 0


def teste_canal(so_visual: bool = False) -> int:
    """Aplica foto/descrição no canal e (opcional) publica as boas-vindas."""
    tg_token = os.environ.get("TELEGRAM_TOKEN", "")
    canal = os.environ.get("TELEGRAM_CANAL_ID", "").strip() or config.TELEGRAM_CANAL
    if not canal:
        anotar("error", "Canal do Telegram não configurado.")
        return 1
    from . import arte
    os.makedirs(PASTA_POSTS, exist_ok=True)
    logo = arte.gerar_logo(os.path.join(PASTA_POSTS, "logo.png"))
    erros = telegram.configurar_canal(tg_token, canal, logo, config.BIO)
    for erro in erros:
        anotar("warning", f"Canal: {erro}")
    if so_visual:
        if not erros:
            anotar("notice", "Foto e descrição do canal aplicadas")
        return 1 if erros else 0
    texto = (
        "📡 Bem-vindo ao Radar da Tela!\n\n"
        "Todo dia de manhã você recebe aqui o que entrou e o que saiu "
        "do streaming no Brasil 🍿\n\n"
        "• Resumo do dia\n• Destaques que acabaram de chegar\n• Despedidas do catálogo\n\n"
        "Fica de olho que o primeiro radar sai amanhã cedo 👀"
    )
    try:
        telegram.enviar_foto(tg_token, canal, logo, texto)
    except Exception as e:
        anotar("error", f"Falha ao publicar no canal: {e}")
        return 1
    anotar("notice", "Boas-vindas publicadas no canal")
    return 0


PASTA_POSTS = os.path.join(os.path.dirname(config.ARQUIVO_RETRATO), "..", "saida")


def enviar_posts(tg_token: str, tg_chat: str, lista: list) -> None:
    if not lista:
        anotar("notice", "Nenhum post relevante hoje.")
        return
    telegram.enviar(tg_token, tg_chat, f"🎨 <b>{len(lista)} posts prontos</b> (prévia, nada foi publicado)")
    for p in lista:
        telegram.enviar_foto(tg_token, tg_chat, p.imagem, p.texto)
    anotar("notice", f"{len(lista)} posts enviados para aprovação")


def previa() -> int:
    """Gera posts de exemplo com títulos reais do catálogo salvo."""
    tg_token = os.environ.get("TELEGRAM_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    retrato = carregar_retrato()
    if not retrato:
        anotar("error", "Sem catálogo salvo ainda.")
        return 1
    # finge que os mais populares de cada plataforma "entraram" e alguns "saíram"
    falso = {}
    for plataforma, itens in retrato.items():
        ordem = sorted(
            ({"chave": k, **v} for k, v in itens.items()), key=lambda i: i["p"], reverse=True
        )
        falso[plataforma] = {"entrou": ordem[:2], "saiu": ordem[40:41], "suspeito": False}
    generos = {}
    try:
        generos = ClienteTMDB(os.environ.get("TMDB_TOKEN", "")).generos()
    except Exception:
        pass
    hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    lista = posts.montar(falso, generos, hoje, PASTA_POSTS)
    telegram.enviar(tg_token, tg_chat, "🧪 <b>PRÉVIA DE TESTE</b>: títulos reais, mas as entradas/saídas são simuladas.")
    enviar_posts(tg_token, tg_chat, lista)
    return 0


def anotar(nivel: str, msg: str) -> None:
    """Mensagem que aparece em destaque na página da execução no GitHub."""
    print(f"::{nivel}::{msg}")


def mostrar_chat_id() -> int:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    if not token:
        anotar("error", "Secret TELEGRAM_TOKEN vazio ou com nome diferente.")
        return 1
    try:
        chats = telegram.descobrir_chats(token)
    except Exception as e:
        codigo = getattr(getattr(e, "response", None), "status_code", "?")
        anotar("error", f"Telegram recusou o token (HTTP {codigo}). Confira o TELEGRAM_TOKEN.")
        return 1
    if not chats:
        anotar("error", "Nenhuma mensagem encontrada. Mande um 'oi' para o seu bot e rode de novo.")
        return 1
    for chat_id, nome in chats:
        print(f"TELEGRAM_CHAT_ID = {chat_id}   ({nome})")
        anotar("notice", f"TELEGRAM_CHAT_ID = {chat_id} ({nome})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chat-id":
        sys.exit(mostrar_chat_id())
    if len(sys.argv) > 1 and sys.argv[1] == "previa":
        sys.exit(previa())
    if len(sys.argv) > 1 and sys.argv[1] == "indicacao":
        dias = {"sexta": 4, "sabado": 5, "domingo": 6}
        forcado = next((dias[a] for a in sys.argv[2:] if a in dias), None)
        sys.exit(rodar_indicacao(forcado, so_previa="--previa" in sys.argv))
    if len(sys.argv) > 1 and sys.argv[1] == "semear-hoje":
        sys.exit(semear_hoje())
    if len(sys.argv) > 1 and sys.argv[1] == "fila":
        sys.exit(rodar_fila())
    if len(sys.argv) > 1 and sys.argv[1] == "relatorio-semanal":
        from . import relatorio
        sys.exit(relatorio.rodar())
    if len(sys.argv) > 1 and sys.argv[1] == "diagnosticar":
        sys.exit(diagnosticar())
    if len(sys.argv) > 1 and sys.argv[1] == "testar-reel":
        sys.exit(testar_reel())
    if len(sys.argv) > 1 and sys.argv[1] == "sugestoes":
        sys.exit(rodar_sugestoes())
    if len(sys.argv) > 1 and sys.argv[1] == "renovar-tokens":
        sys.exit(renovar())
    if len(sys.argv) > 1 and sys.argv[1] == "testar-redes":
        sys.exit(testar_redes())
    if len(sys.argv) > 1 and sys.argv[1] == "teste-canal":
        sys.exit(teste_canal(so_visual="--so-visual" in sys.argv))
    sys.exit(rodar())
