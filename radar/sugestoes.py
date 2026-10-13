"""Sugestões de resposta: posts em alta no X sobre títulos que acabaram
de chegar no streaming, com uma resposta pronta para você copiar.

O robô NÃO responde sozinho (as regras do X proíbem respostas
automáticas a posts de outras pessoas). Ele só monta a lista e manda no
seu Telegram; você abre o link e responde manualmente.

Custo: cada post lido na busca custa ~US$ 0,005 (3 buscas x 10 posts
≈ US$ 0,15 por dia).
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import random

import requests

from . import arte, config
from .publicar import X_API, _oauth_x, redes_ativas

TITULOS_POR_DIA = 3
SUGESTOES_MAX = 3
MIN_SEGUIDORES_AUTOR = 3000
MIN_CURTIDAS = 20

MODELOS = [
    "Pra quem quiser assistir: {t} chegou {onde} esses dias 🍿",
    "Inclusive já tá {onde} 👀",
    "Dica: {t} entrou {onde} essa semana, dá pra ver hoje mesmo 🍿",
    "Quem ainda não viu: tá {onde} 📺",
]


def _onde(plataformas: list[str]) -> str:
    return f"{arte.preposicao(plataformas[0])} {plataformas[0]}"


def titulos_recentes(arquivo: str, dias: int = 2) -> list[dict]:
    try:
        with open(arquivo, encoding="utf-8") as f:
            todas = json.load(f)
    except (OSError, ValueError):
        return []
    vistos, itens = set(), []
    for data in sorted(todas, reverse=True)[:dias]:
        for it in todas[data]:
            if it["t"] not in vistos and len(it["t"]) >= 4:
                vistos.add(it["t"])
                itens.append(it)
    return sorted(itens, key=lambda i: i.get("p", 0), reverse=True)


def buscar(titulo: str) -> list[dict]:
    """Posts recentes em português que citam o título."""
    consulta = f'"{titulo}" lang:pt -is:retweet -is:reply -from:radardatela'
    r = requests.get(
        f"{X_API}/tweets/search/recent",
        auth=_oauth_x(),
        params={
            "query": consulta[:512],
            "max_results": 10,
            "sort_order": "relevancy",
            "tweet.fields": "public_metrics,created_at,author_id",
            "expansions": "author_id",
            "user.fields": "username,public_metrics",
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"busca no X: HTTP {r.status_code} {r.text[:200]}")
    dados = r.json()
    autores = {u["id"]: u for u in dados.get("includes", {}).get("users", [])}
    saida = []
    for t in dados.get("data", []):
        u = autores.get(t["author_id"], {})
        seg = u.get("public_metrics", {}).get("followers_count", 0)
        cur = t.get("public_metrics", {}).get("like_count", 0)
        if seg < MIN_SEGUIDORES_AUTOR and cur < MIN_CURTIDAS:
            continue
        saida.append({
            "url": f"https://x.com/{u.get('username', 'i')}/status/{t['id']}",
            "autor": u.get("username", "?"),
            "seguidores": seg,
            "curtidas": cur,
            "texto": t.get("text", "")[:160],
            "peso": seg / 1000 + cur,
        })
    return sorted(saida, key=lambda s: s["peso"], reverse=True)


def montar(arquivo_novidades: str, data: dt.date) -> list[dict]:
    if not redes_ativas().get("x"):
        return []
    sorteio = random.Random(data.isoformat())
    sugestoes = []
    for item in titulos_recentes(arquivo_novidades)[:TITULOS_POR_DIA]:
        try:
            achados = buscar(item["t"])
        except Exception as e:
            print(e)
            continue
        if not achados:
            continue
        melhor = achados[0]
        resposta = sorteio.choice(MODELOS).format(t=item["t"], onde=_onde(item["plataformas"]))
        sugestoes.append({**melhor, "titulo": item["t"], "resposta": resposta})
        if len(sugestoes) >= SUGESTOES_MAX:
            break
    return sugestoes


def mensagem(sugestoes: list[dict]) -> str:
    if not sugestoes:
        return ("💬 <b>Sugestões de resposta</b>\nHoje não achei posts grandes sobre as "
                "novidades. Aproveite para responder comentários nos seus posts 😉")
    linhas = ["💬 <b>Sugestões de resposta de hoje</b>",
              "Abra o link, entre como @radardatela e responda. Leva 1 minuto cada.\n"]
    for i, s in enumerate(sugestoes, 1):
        linhas += [
            f"<b>{i}. {html.escape(s['titulo'])}</b>: @{html.escape(s['autor'])} "
            f"({s['seguidores']:,} seguidores, {s['curtidas']} curtidas)".replace(",", "."),
            f"<i>{html.escape(s['texto'])}</i>",
            f"🔗 {s['url']}",
            f"✍️ Sugestão: <code>{html.escape(s['resposta'])}</code>",
            "",
        ]
    linhas.append("Toque na sugestão para copiar. Ajuste com o seu jeito antes de enviar 😉")
    return "\n".join(linhas)
