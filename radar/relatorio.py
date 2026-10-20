"""Relatório semanal no Telegram (segunda de manhã).

- Seguidores no Instagram e no Threads e quanto cada um cresceu na semana
- Desempenho dos posts do Threads por tipo e por horário
- Os 3 posts do Threads que mais renderam

Os números por post exigem a permissão threads_manage_insights no app da
Meta; sem ela, o relatório mostra só os seguidores do Instagram.
"""

from __future__ import annotations

import datetime as dt
import html
import os
from collections import defaultdict
from zoneinfo import ZoneInfo

from . import agenda, publicar, telegram

FUSO = ZoneInfo("America/Sao_Paulo")
ARQUIVO_SEGUIDORES = os.path.join(agenda.DADOS, "seguidores.json")

NOMES = {
    "resumo_fio": "Resumo em fio", "fio_resposta": "Respostas do fio", "alerta": "Destaque",
    "saiu": "Saiu do catálogo", "enquete": "Enquete", "dica": "Dica da galera",
    "previa_indicacao": "Prévia da indicação", "gancho_top10": "Gancho Top 10",
    "indicacao": "Indicação do fim de semana", "resumo": "Resumo",
}


def _faixa(hora: int) -> str:
    if hora < 11:
        return "manhã"
    if hora < 17:
        return "almoço/tarde"
    if hora < 20:
        return "início da noite"
    return "noite"


def coletar(agora: dt.datetime) -> dict:
    inicio = (agora - dt.timedelta(days=7)).isoformat()
    log = [l for l in agenda._ler(agenda.ARQUIVO_LOG, []) if l["quando"] >= inicio]
    posts, sem_permissao = [], False
    for l in log:
        try:
            m = publicar.threads_insights(l["id"])
        except Exception as e:
            if "permission" in str(e).lower() or "(código 10)" in str(e) or "(código 200)" in str(e):
                sem_permissao = True
                break
            continue
        engaj = m.get("likes", 0) + m.get("replies", 0) * 2 + m.get("reposts", 0) * 2 + m.get("quotes", 0) * 2
        posts.append({**l, **m, "engaj": engaj})

    seguidores = {"instagram": publicar.instagram_seguidores(),
                  "threads": None if sem_permissao else publicar.threads_seguidores()}
    historico = agenda._ler(ARQUIVO_SEGUIDORES, [])
    anterior = historico[-1] if historico else {}
    historico.append({"data": agora.date().isoformat(), **seguidores})
    agenda._gravar(ARQUIVO_SEGUIDORES, historico[-60:])
    return {"posts": posts, "sem_permissao": sem_permissao, "seguidores": seguidores,
            "anterior": anterior}


def _media(itens, campo):
    return sum(i.get(campo, 0) or 0 for i in itens) / len(itens) if itens else 0


def mensagem(dados: dict) -> str:
    linhas = ["📈 <b>Relatório semanal do Radar da Tela</b>", ""]
    seg, ant = dados["seguidores"], dados["anterior"]
    linhas.append("<b>Seguidores</b>")
    for rede, nome in (("instagram", "Instagram"), ("threads", "Threads")):
        atual = seg.get(rede)
        if atual is None:
            linhas.append(f"• {nome}: —")
            continue
        antes = ant.get(rede)
        delta = f" ({atual - antes:+d} na semana)" if isinstance(antes, int) else ""
        linhas.append(f"• {nome}: {atual}{delta}")

    if dados["sem_permissao"]:
        linhas += ["", "⚠️ Para ver o desempenho de cada post do Threads, ative a permissão "
                   "<b>threads_manage_insights</b> no app da Meta e gere um token novo."]
        return "\n".join(linhas)

    posts = dados["posts"]
    if not posts:
        linhas += ["", "Ainda não há posts do Threads registrados nesta semana."]
        return "\n".join(linhas)

    total_views = sum(p.get("views", 0) or 0 for p in posts)
    linhas += ["", f"<b>Threads na semana</b>: {len(posts)} posts · {total_views:,} visualizações".replace(",", ".")]

    por_tipo = defaultdict(list)
    for p in posts:
        por_tipo[p["tipo"]].append(p)
    linhas += ["", "<b>Por tipo de post</b> (média por post)"]
    for tipo, itens in sorted(por_tipo.items(), key=lambda kv: -_media(kv[1], "engaj")):
        linhas.append(f"• {NOMES.get(tipo, tipo)}: {_media(itens, 'views'):.0f} views · "
                      f"{_media(itens, 'likes'):.1f} curtidas · {_media(itens, 'replies'):.1f} respostas")

    por_faixa = defaultdict(list)
    for p in posts:
        por_faixa[_faixa(int(p["quando"][11:13]))].append(p)
    melhor = max(por_faixa.items(), key=lambda kv: _media(kv[1], "engaj"))
    linhas += ["", f"<b>Melhor horário</b>: {melhor[0]} ({_media(melhor[1], 'views'):.0f} views em média)"]

    top = sorted(posts, key=lambda p: (p["engaj"], p.get("views", 0)), reverse=True)[:3]
    linhas += ["", "<b>Top 3 posts</b>"]
    for i, p in enumerate(top, 1):
        quando = dt.datetime.fromisoformat(p["quando"]).strftime("%d/%m %Hh%M")
        linhas.append(f"{i}. {NOMES.get(p['tipo'], p['tipo'])} ({quando}): "
                      f"{p.get('views', 0)} views · {p.get('likes', 0)} curtidas · {p.get('replies', 0)} respostas")
    return "\n".join(linhas)


def rodar() -> int:
    agora = dt.datetime.now(FUSO)
    dados = coletar(agora)
    texto = mensagem(dados)
    print(texto)
    telegram.enviar(os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""), texto)
    return 0


__all__ = ["rodar", "mensagem", "coletar", "html"]
