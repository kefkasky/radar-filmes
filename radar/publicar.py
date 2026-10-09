"""Publicação automática: Threads, Instagram e X (Fase 3).

Cada rede só é usada se os seus secrets existirem. Uma rede com erro não
impede as outras.

Instagram e Threads exigem a imagem num link público: os posts são
enviados antes para o repositório público de mídia (MIDIA_REPO).
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import os
import time

import requests

from . import config

GITHUB_API = "https://api.github.com"
THREADS_API = "https://graph.threads.net/v1.0"
INSTAGRAM_API = "https://graph.instagram.com/v23.0"
X_API = "https://api.x.com/2"


class ErroPublicacao(Exception):
    pass


def _env(nome: str) -> str:
    return os.environ.get(nome, "").strip()


def redes_ativas() -> dict[str, bool]:
    return {
        "threads": bool(_env("THREADS_TOKEN")),
        "instagram": bool(_env("INSTAGRAM_TOKEN")),
        "x": all(_env(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")),
    }


# ----------------------------------------------------------------------
# Hospedagem pública das imagens (repositório público no GitHub)
# ----------------------------------------------------------------------
def hospedar(caminho: str, data: dt.date) -> str:
    """Envia a imagem ao repositório público e devolve o link direto."""
    token, repo = _env("MIDIA_TOKEN"), _env("MIDIA_REPO") or config.MIDIA_REPO
    if not token:
        raise ErroPublicacao("MIDIA_TOKEN não configurado (necessário para Instagram/Threads).")
    with open(caminho, "rb") as f:
        dados = f.read()
    resumo = hashlib.sha1(dados).hexdigest()[:10]
    nome = os.path.splitext(os.path.basename(caminho))[0]
    destino = f"posts/{data.isoformat()}/{nome}-{resumo}.jpg"
    resp = requests.put(
        f"{GITHUB_API}/repos/{repo}/contents/{destino}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"message": f"post {destino}", "content": base64.b64encode(dados).decode()},
        timeout=60,
    )
    if resp.status_code not in (200, 201, 422):  # 422 = já existe (mesmo conteúdo)
        raise ErroPublicacao(f"GitHub recusou a imagem ({resp.status_code}): {resp.text[:200]}")
    url = f"https://raw.githubusercontent.com/{repo}/main/{destino}"
    for _ in range(12):  # espera o link ficar disponível
        if requests.head(url, timeout=20).status_code == 200:
            return url
        time.sleep(5)
    raise ErroPublicacao(f"Imagem não ficou disponível em {url}")


# ----------------------------------------------------------------------
# Threads
# ----------------------------------------------------------------------
def threads(url_imagem: str, texto: str) -> str:
    token = _env("THREADS_TOKEN")
    r = requests.post(
        f"{THREADS_API}/me/threads",
        data={"media_type": "IMAGE", "image_url": url_imagem, "text": texto[:500],
              "access_token": token},
        timeout=60,
    )
    if not r.ok:
        raise ErroPublicacao(f"Threads (container): {_erro_meta(r)}")
    container = r.json()["id"]
    time.sleep(30)  # recomendado pela Meta antes de publicar
    for tentativa in range(4):
        r = requests.post(
            f"{THREADS_API}/me/threads_publish",
            data={"creation_id": container, "access_token": token},
            timeout=60,
        )
        if r.ok:
            return r.json()["id"]
        time.sleep(15)
    raise ErroPublicacao(f"Threads (publicar): {_erro_meta(r)}")


# ----------------------------------------------------------------------
# Instagram (API do Instagram com login do Instagram)
# ----------------------------------------------------------------------
def instagram(url_imagem: str, legenda: str) -> str:
    token = _env("INSTAGRAM_TOKEN")
    r = requests.post(
        f"{INSTAGRAM_API}/me/media",
        data={"image_url": url_imagem, "caption": legenda[:2200], "access_token": token},
        timeout=60,
    )
    if not r.ok:
        raise ErroPublicacao(f"Instagram (container): {_erro_meta(r)}")
    container = r.json()["id"]
    for _ in range(20):  # espera o Instagram processar a imagem
        s = requests.get(
            f"{INSTAGRAM_API}/{container}",
            params={"fields": "status_code", "access_token": token},
            timeout=30,
        )
        status = s.json().get("status_code") if s.ok else None
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise ErroPublicacao("Instagram não conseguiu processar a imagem.")
        time.sleep(5)
    r = requests.post(
        f"{INSTAGRAM_API}/me/media_publish",
        data={"creation_id": container, "access_token": token},
        timeout=60,
    )
    if not r.ok:
        raise ErroPublicacao(f"Instagram (publicar): {_erro_meta(r)}")
    return r.json()["id"]


def _erro_meta(r: requests.Response) -> str:
    try:
        e = r.json().get("error", {})
        return f"{e.get('message', r.text[:200])} (código {e.get('code', r.status_code)})"
    except ValueError:
        return f"HTTP {r.status_code}"


# ----------------------------------------------------------------------
# X (OAuth 1.0a, contexto do usuário)
# ----------------------------------------------------------------------
def _oauth_x():
    from requests_oauthlib import OAuth1

    return OAuth1(_env("X_API_KEY"), _env("X_API_SECRET"),
                  _env("X_ACCESS_TOKEN"), _env("X_ACCESS_SECRET"))


def x(caminho_imagem: str, texto: str) -> str:
    auth = _oauth_x()
    with open(caminho_imagem, "rb") as f:
        dados = f.read()

    # upload simples; se não for aceito, cai para o upload em partes
    r = requests.post(
        f"{X_API}/media/upload",
        auth=auth,
        files={"media": ("post.jpg", dados, "image/jpeg")},
        data={"media_category": "tweet_image", "media_type": "image/jpeg"},
        timeout=90,
    )
    if r.ok:
        media_id = r.json()["data"]["id"]
    else:
        media_id = _x_upload_em_partes(auth, dados)

    r = requests.post(
        f"{X_API}/tweets",
        auth=auth,
        json={"text": texto[:280], "media": {"media_ids": [media_id]}},
        timeout=60,
    )
    if not r.ok:
        raise ErroPublicacao(f"X (post): HTTP {r.status_code} {r.text[:300]}")
    return r.json()["data"]["id"]


def _x_upload_em_partes(auth, dados: bytes) -> str:
    url = f"{X_API}/media/upload"
    r = requests.post(url, auth=auth, data={
        "command": "INIT", "total_bytes": len(dados),
        "media_type": "image/jpeg", "media_category": "tweet_image"}, timeout=60)
    if not r.ok:
        raise ErroPublicacao(f"X (upload INIT): HTTP {r.status_code} {r.text[:300]}")
    media_id = r.json()["data"]["id"]
    r = requests.post(url, auth=auth,
                      data={"command": "APPEND", "media_id": media_id, "segment_index": 0},
                      files={"media": ("post.jpg", dados, "image/jpeg")}, timeout=90)
    if not r.ok:
        raise ErroPublicacao(f"X (upload APPEND): HTTP {r.status_code} {r.text[:300]}")
    r = requests.post(url, auth=auth, data={"command": "FINALIZE", "media_id": media_id}, timeout=60)
    if not r.ok:
        raise ErroPublicacao(f"X (upload FINALIZE): HTTP {r.status_code} {r.text[:300]}")
    return media_id


# ----------------------------------------------------------------------
# Orquestração
# ----------------------------------------------------------------------
def publicar_todos(lista: list, data: dt.date, limite_por_rede: dict | None = None) -> dict:
    """Publica a lista de posts nas redes ativas.

    Retorna {rede: {"ok": n, "erros": [mensagens]}}.
    """
    ativas = {r for r, ok in redes_ativas().items() if ok}
    limite_por_rede = limite_por_rede or config.LIMITE_POSTS_POR_REDE
    resultado = {r: {"ok": 0, "erros": []} for r in ativas}
    if not ativas:
        return resultado

    precisa_link = ativas & {"threads", "instagram"}
    for i, post in enumerate(lista):
        url = None
        if precisa_link:
            try:
                url = hospedar(post.imagem, data)
            except Exception as e:
                for r in precisa_link:
                    resultado[r]["erros"].append(str(e))

        for rede in sorted(ativas):
            if i >= limite_por_rede.get(rede, 99):
                continue
            try:
                if rede == "x":
                    x(post.imagem, post.texto)
                elif url is None:
                    continue
                elif rede == "threads":
                    threads(url, post.texto)
                elif rede == "instagram":
                    instagram(url, post.texto + config.HASHTAGS_INSTAGRAM)
                resultado[rede]["ok"] += 1
            except Exception as e:
                resultado[rede]["erros"].append(str(e)[:300])
    return resultado


# ----------------------------------------------------------------------
# Renovação dos tokens da Meta (valem 60 dias)
# ----------------------------------------------------------------------
def renovar_tokens() -> dict[str, str]:
    """Renova os tokens longos do Instagram e do Threads.

    Retorna {rede: mensagem}. Se a Meta devolver um token diferente,
    a mensagem pede para atualizar o secret (o token nunca é exibido).
    """
    msgs = {}
    alvos = {
        "instagram": ("INSTAGRAM_TOKEN", "https://graph.instagram.com/refresh_access_token", "ig_refresh_token"),
        "threads": ("THREADS_TOKEN", "https://graph.threads.net/refresh_access_token", "th_refresh_token"),
    }
    for rede, (var, url, tipo) in alvos.items():
        token = _env(var)
        if not token:
            continue
        r = requests.get(url, params={"grant_type": tipo, "access_token": token}, timeout=30)
        if not r.ok:
            msgs[rede] = f"falha ao renovar: {_erro_meta(r)}"
            continue
        novo = r.json().get("access_token", "")
        dias = int(r.json().get("expires_in", 0)) // 86400
        if novo and novo != token:
            try:
                salvar_secret(var, novo)
                msgs[rede] = f"renovado e salvo, válido por mais {dias} dias"
            except Exception as e:
                msgs[rede] = (f"falha ao salvar o token renovado ({e}). O atual vale por "
                              f"pouco tempo: gere um novo e atualize o secret {var}.")
        else:
            msgs[rede] = f"renovado, válido por mais {dias} dias"
    return msgs


def salvar_secret(nome: str, valor: str) -> None:
    """Atualiza um secret deste repositório pela API do GitHub.

    Usa o SECRETS_TOKEN (ou o MIDIA_TOKEN, se ele tiver a permissão
    'Secrets: read and write' no radar-filmes).
    """
    from nacl import encoding, public

    token = _env("SECRETS_TOKEN") or _env("MIDIA_TOKEN")
    repo = _env("GITHUB_REPOSITORY")
    if not token or not repo:
        raise ErroPublicacao("sem token com permissão de Secrets")
    cab = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    r = requests.get(f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key", headers=cab, timeout=30)
    if not r.ok:
        raise ErroPublicacao(f"GitHub recusou ler a chave dos secrets (HTTP {r.status_code}); "
                             "o token precisa da permissão 'Secrets: read and write' no radar-filmes")
    chave = r.json()
    caixa = public.SealedBox(public.PublicKey(chave["key"].encode(), encoding.Base64Encoder()))
    cifrado = base64.b64encode(caixa.encrypt(valor.encode())).decode()
    r = requests.put(f"{GITHUB_API}/repos/{repo}/actions/secrets/{nome}", headers=cab,
                     json={"encrypted_value": cifrado, "key_id": chave["key_id"]}, timeout=30)
    if r.status_code not in (201, 204):
        raise ErroPublicacao(f"GitHub recusou salvar o secret (HTTP {r.status_code})")
