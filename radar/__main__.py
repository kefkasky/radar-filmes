"""Execução diária do Radar de Filmes (Fase 1: só relatório, sem postar).

Uso:
    python -m radar            # coleta, compara e envia o relatório
    python -m radar chat-id    # mostra o ID do seu chat com o bot
    python -m radar previa     # manda posts de exemplo (com títulos reais)
"""

import datetime as dt
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
    try:
        telegram.enviar(tg_token, tg_chat, relatorio)
    except Exception as e:
        anotar("error", f"Falha ao enviar no Telegram: {e}")
        return 1

    # Fase 2: posts prontos para aprovação
    try:
        lista = posts.montar(diferencas, cliente.generos(), agora.date(), PASTA_POSTS)
        enviar_posts(tg_token, tg_chat, lista)
    except Exception as e:
        anotar("error", f"Falha ao gerar/enviar posts: {e}")
        traceback.print_exc()
        return 1
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
    sys.exit(rodar())
