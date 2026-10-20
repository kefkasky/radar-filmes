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
    so = {r.strip() for r in _env("SO_REDES").lower().split(",") if r.strip() and r.strip() != "todas"}
    ativas = {
        "threads": bool(_env("THREADS_TOKEN")),
        "instagram": bool(_env("INSTAGRAM_TOKEN")),
        "x": all(_env(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")),
    }
    if so:
        ativas = {r: ok and r in so for r, ok in ativas.items()}
    return ativas


# ----------------------------------------------------------------------
# Hospedagem pública das imagens (repositório público no GitHub)
# ----------------------------------------------------------------------
def hospedar(caminho: str, data: dt.date) -> str:
    """Envia a imagem (ou vídeo) ao repositório público e devolve o link direto."""
    token, repo = _env("MIDIA_TOKEN"), _env("MIDIA_REPO") or config.MIDIA_REPO
    if not token:
        raise ErroPublicacao("MIDIA_TOKEN não configurado (necessário para Instagram/Threads).")
    with open(caminho, "rb") as f:
        dados = f.read()
    resumo = hashlib.sha1(dados).hexdigest()[:10]
    nome = os.path.splitext(os.path.basename(caminho))[0]
    ext = os.path.splitext(caminho)[1].lower() or ".jpg"
    destino = f"posts/{data.isoformat()}/{nome}-{resumo}{ext}"
    for tentativa in range(4):  # o GitHub às vezes recusa por instabilidade (409/5xx)
        try:
            resp = requests.put(
                f"{GITHUB_API}/repos/{repo}/contents/{destino}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                json={"message": f"post {destino}", "content": base64.b64encode(dados).decode()},
                timeout=60,
            )
        except requests.RequestException:
            if tentativa == 3:
                raise
            time.sleep(10 * (tentativa + 1))
            continue
        if resp.status_code in (200, 201, 422) or resp.status_code not in (409, 500, 502, 503, 504):
            break
        time.sleep(10 * (tentativa + 1))
    if resp.status_code not in (200, 201, 422):  # 422 = já existe (mesmo conteúdo)
        raise ErroPublicacao(f"GitHub recusou a imagem ({resp.status_code}): {resp.text[:200]}")
    url = f"https://raw.githubusercontent.com/{repo}/main/{destino}"
    for _ in range(24):  # espera o link ficar disponível
        if requests.head(url, timeout=20).status_code == 200:
            return url
        time.sleep(5)
    raise ErroPublicacao(f"Imagem não ficou disponível em {url}")


# ----------------------------------------------------------------------
# Threads
# ----------------------------------------------------------------------
def cortar_threads(texto: str, limite: int = 500) -> str:
    """O Threads conta emojis pelo tamanho em bytes: corta pelo UTF-8."""
    if len(texto.encode("utf-8")) <= limite:
        return texto
    while texto and len((texto + "…").encode("utf-8")) > limite:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def threads_publicar(texto: str, url_imagem: str | None = None, poll: dict | None = None,
                     reply_to: str | None = None, topico: str | None = None) -> str:
    """Publica no Threads: imagem, texto, enquete ou resposta (fio). Retorna o id."""
    import json as _json

    token = _env("THREADS_TOKEN")
    dados = {"text": cortar_threads(texto), "access_token": token,
             "media_type": "IMAGE" if url_imagem else "TEXT"}
    if url_imagem:
        dados["image_url"] = url_imagem
    if poll:
        dados["poll_attachment"] = _json.dumps(
            {k: v[:25] for k, v in poll.items() if v}, ensure_ascii=False)
    if reply_to:
        dados["reply_to_id"] = reply_to
    topico = (topico or "").replace(".", "").replace("&", "e").strip()[:50]
    if topico and not reply_to:
        dados["topic_tag"] = topico
    r = requests.post(f"{THREADS_API}/me/threads", data=dados, timeout=60)
    if not r.ok and "topic_tag" in dados:  # se o tópico for recusado, publica sem ele
        dados.pop("topic_tag")
        r = requests.post(f"{THREADS_API}/me/threads", data=dados, timeout=60)
    if not r.ok:
        raise ErroPublicacao(f"Threads (container): {_erro_meta(r)}")
    container = r.json()["id"]
    time.sleep(30 if url_imagem else 12)  # a Meta recomenda esperar antes de publicar
    for _ in range(4):
        r = requests.post(
            f"{THREADS_API}/me/threads_publish",
            data={"creation_id": container, "access_token": token},
            timeout=60,
        )
        if r.ok:
            return r.json()["id"]
        time.sleep(15)
    raise ErroPublicacao(f"Threads (publicar): {_erro_meta(r)}")


def threads(url_imagem: str, texto: str, topico: str | None = None) -> str:
    return threads_publicar(texto, url_imagem=url_imagem, topico=topico)


def threads_fio(textos: list[str], url_imagem: str | None = None,
                topico: str | None = None) -> list[str]:
    """Primeiro post (com imagem) e as respostas encadeadas, uma embaixo da outra."""
    ids = [threads_publicar(textos[0], url_imagem=url_imagem, topico=topico)]
    for texto in textos[1:]:
        try:
            ids.append(threads_publicar(texto, reply_to=ids[-1]))
        except ErroPublicacao as e:
            print(f"resposta do fio falhou: {e}")
            break
    return ids


def threads_insights(media_id: str) -> dict:
    r = requests.get(f"{THREADS_API}/{media_id}/insights",
                     params={"metric": "views,likes,replies,reposts,quotes",
                             "access_token": _env("THREADS_TOKEN")}, timeout=30)
    if not r.ok:
        raise ErroPublicacao(f"Threads insights: {_erro_meta(r)}")
    return {m["name"]: (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value", 0))
            for m in r.json().get("data", [])}


def threads_seguidores() -> int | None:
    r = requests.get(f"{THREADS_API}/me/threads_insights",
                     params={"metric": "followers_count", "access_token": _env("THREADS_TOKEN")},
                     timeout=30)
    if not r.ok:
        return None
    for m in r.json().get("data", []):
        if m.get("name") == "followers_count":
            return m.get("total_value", {}).get("value")
    return None


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
    return _instagram_publicar(container, token, "Instagram (publicar)")


def _instagram_publicar(container: str, token: str, rotulo: str) -> str:
    """media_publish com novas tentativas: às vezes a mídia ainda não está pronta (código 9007)."""
    for tentativa in range(6):
        r = requests.post(f"{INSTAGRAM_API}/me/media_publish",
                          data={"creation_id": container, "access_token": token}, timeout=60)
        if r.ok:
            return r.json()["id"]
        if "9007" not in _erro_meta(r) and tentativa >= 1:
            break
        time.sleep(15 * (tentativa + 1))
    raise ErroPublicacao(f"{rotulo}: {_erro_meta(r)}")


def instagram_carrossel(urls: list[str], legenda: str) -> str:
    """Carrossel de até 10 imagens."""
    token = _env("INSTAGRAM_TOKEN")
    filhos = []
    for url in urls[:10]:
        r = requests.post(f"{INSTAGRAM_API}/me/media",
                          data={"image_url": url, "is_carousel_item": "true", "access_token": token},
                          timeout=60)
        if not r.ok:
            raise ErroPublicacao(f"Instagram carrossel (item): {_erro_meta(r)}")
        filhos.append(r.json()["id"])
    r = requests.post(f"{INSTAGRAM_API}/me/media",
                      data={"media_type": "CAROUSEL", "children": ",".join(filhos),
                            "caption": legenda[:2200], "access_token": token}, timeout=60)
    if not r.ok:
        raise ErroPublicacao(f"Instagram carrossel: {_erro_meta(r)}")
    container = r.json()["id"]
    for _ in range(24):
        time.sleep(5)
        st = requests.get(f"{INSTAGRAM_API}/{container}",
                          params={"fields": "status_code", "access_token": token}, timeout=30)
        status = st.json().get("status_code") if st.ok else None
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise ErroPublicacao(f"Instagram não processou o carrossel ({status}).")
    return _instagram_publicar(container, token, "Instagram carrossel (publicar)")


def instagram_seguidores() -> int | None:
    r = requests.get(f"{INSTAGRAM_API}/me", params={"fields": "followers_count",
                                                    "access_token": _env("INSTAGRAM_TOKEN")}, timeout=30)
    return r.json().get("followers_count") if r.ok else None


def instagram_reel(url_video: str, legenda: str) -> str:
    """Publica um Reel (o Instagram busca o vídeo pelo link público)."""
    token = _env("INSTAGRAM_TOKEN")
    r = requests.post(
        f"{INSTAGRAM_API}/me/media",
        data={"media_type": "REELS", "video_url": url_video, "caption": legenda[:2200],
              "share_to_feed": "true", "access_token": token},
        timeout=60,
    )
    if not r.ok:
        raise ErroPublicacao(f"Instagram Reel (container): {_erro_meta(r)}")
    container = r.json()["id"]
    for _ in range(30):  # vídeo demora mais para processar (até ~5 min)
        time.sleep(10)
        s = requests.get(f"{INSTAGRAM_API}/{container}",
                         params={"fields": "status_code", "access_token": token}, timeout=30)
        status = s.json().get("status_code") if s.ok else None
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise ErroPublicacao(f"Instagram não processou o Reel ({status}).")
    return _instagram_publicar(container, token, "Instagram Reel (publicar)")


def publicar_reel(caminho_video: str, legenda: str, data: dt.date) -> str:
    if not redes_ativas().get("instagram"):
        return "instagram inativo"
    url = hospedar(caminho_video, data)
    return instagram_reel(url, legenda + config.HASHTAGS_INSTAGRAM)


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


def x_texto(texto: str) -> str:
    """Post só de texto no X (sem link, para não pagar a taxa de link)."""
    r = requests.post(f"{X_API}/tweets", auth=_oauth_x(), json={"text": texto}, timeout=60)
    if not r.ok:
        raise ErroPublicacao(f"X (post): HTTP {r.status_code} {r.text[:300]}")
    return r.json()["data"]["id"]


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
def publicar_todos(lista: list, data: dt.date, limite_por_rede: dict | None = None,
                   excluir: set | None = None) -> dict:
    """Publica a lista de posts nas redes ativas.

    Retorna {rede: {"ok": n, "erros": [mensagens]}}.
    """
    ativas = {r for r, ok in redes_ativas().items() if ok} - (excluir or set())
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
                    mid = threads(url, post.texto, getattr(post, "topico", None))
                    from . import agenda
                    agenda.registrar_publicacao(mid, post.tipo)
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
