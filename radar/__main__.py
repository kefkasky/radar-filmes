"""Execução diária do Radar de Filmes (Fase 1: só relatório, sem postar).

Uso:
    python -m radar            # coleta, compara e envia o relatório
    python -m radar chat-id    # mostra o ID do seu chat com o bot
"""

import datetime as dt
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

from . import comparar, config, telegram
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
        telegram.enviar(tg_token, tg_chat, f"❌ Radar de Filmes: {e}")
        print(e)
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
    telegram.enviar(tg_token, tg_chat, relatorio)
    return 0


def mostrar_chat_id() -> int:
    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token:
        print("Configure o TELEGRAM_TOKEN primeiro.")
        return 1
    chats = telegram.descobrir_chats(token)
    if not chats:
        print("Nenhuma mensagem encontrada. Mande um 'oi' para o seu bot e rode de novo.")
        return 1
    for chat_id, nome in chats:
        print(f"TELEGRAM_CHAT_ID = {chat_id}   ({nome})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chat-id":
        sys.exit(mostrar_chat_id())
    sys.exit(rodar())
