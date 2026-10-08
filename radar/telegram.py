"""Envio de mensagens pelo bot do Telegram."""

import requests

LIMITE = 4000  # o Telegram aceita até 4096 caracteres por mensagem


def dividir(texto: str, limite: int = LIMITE) -> list[str]:
    """Quebra o texto em mensagens, sempre em fim de linha."""
    partes, atual = [], ""
    for linha in texto.split("\n"):
        while len(linha) > limite:  # linha gigante (raro): corta à força
            if atual:
                partes.append(atual)
                atual = ""
            partes.append(linha[:limite])
            linha = linha[limite:]
        candidato = f"{atual}\n{linha}" if atual else linha
        if len(candidato) > limite:
            partes.append(atual)
            atual = linha
        else:
            atual = candidato
    if atual:
        partes.append(atual)
    return partes


def enviar(token: str, chat_id: str, texto: str) -> None:
    if not token or not chat_id:
        print("Telegram não configurado; relatório só no log.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for parte in dividir(texto):
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": parte,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Telegram recusou a mensagem: {resp.status_code} {resp.text}")


def enviar_foto(token: str, chat_id: str, caminho: str, legenda: str = "") -> None:
    """Envia uma imagem com legenda (texto puro, fácil de copiar)."""
    if not token or not chat_id:
        print(f"Telegram não configurado; imagem {caminho} não enviada.")
        return
    with open(caminho, "rb") as f:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": chat_id, "caption": legenda[:1024]},
            files={"photo": f},
            timeout=60,
        )
    if not resp.ok:
        raise RuntimeError(f"Telegram recusou a imagem: {resp.status_code} {resp.text}")


def descobrir_chats(token: str) -> list[tuple[str, str]]:
    """Lista (chat_id, nome) de quem mandou mensagem recente ao bot."""
    resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
    resp.raise_for_status()
    vistos = {}
    for upd in resp.json().get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or upd.get("my_chat_member") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            nome = chat.get("title") or chat.get("first_name") or chat.get("username") or "?"
            vistos[str(chat["id"])] = nome
    return list(vistos.items())
