"""Agenda do Threads: posts espalhados ao longo do dia + funil para o Instagram.

Manhã (06:47)  resumo do dia em FIO (imagem + 1 resposta por título com sinopse)
               e chamada para o Reel do dia no Instagram
12:20          2 destaques; sexta a domingo, prévia da indicação das 18h;
               domingo, gancho do Top 10 da semana (completo só no Instagram)
19:00          enquete "qual desses você assiste primeiro?" + destaque + despedida
21:00          "deixe uma dica" de filme que vale a pena

A rotina da manhã monta tudo e guarda numa fila (data/fila_threads.json);
o fluxo "Agenda do Threads" publica o que estiver no horário.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from . import arte, config, posts

FUSO = ZoneInfo("America/Sao_Paulo")
DADOS = os.path.dirname(config.ARQUIVO_RETRATO)
ARQUIVO_FILA = os.path.join(DADOS, "fila_threads.json")
ARQUIVO_LOG = os.path.join(DADOS, "threads_log.json")

HORARIOS = {"almoco": (12, 20), "noite": (19, 0), "dica": (21, 0)}

DICAS = [
    "💬 Deixa aqui uma dica pra galera: qual filme você assistiu e acha que vale a pena todo mundo ver? 🍿",
    "🎬 Bora montar a lista da semana juntos: comenta um filme que você recomenda de olhos fechados 👇",
    "🍿 Qual filme você indicaria pra alguém que não sabe o que assistir hoje? Deixa a dica aqui 👇",
    "📺 Vale série também: qual você acha que todo mundo deveria ver? Comenta aí que a gente monta a lista 👇",
    "💡 Dica de ouro: um filme que pouca gente conhece mas que vale muito a pena. Qual é o seu? 👇",
    "🎞️ Aquele filme que você assistiu e ficou pensando dias depois. Indica aqui pra galera 👇",
    "🛋️ Plano pra hoje à noite: deixa a sua indicação de filme que vale o play 👇",
]

PREVIAS = {
    4: "🎖️ Hoje às 18h tem indicação: um filme de guerra baseado em fatos reais, direto do streaming.",
    5: "💘 Hoje às 18h tem indicação de sábado: um romance pra ver a dois.",
    6: "😂 Hoje às 18h tem indicação de domingo: uma comédia pra fechar o fim de semana rindo.",
}
FIM_PREVIA = "Sai aqui e no Insta @radardatela 👀"
CHAMADA_REEL = "🎬 Hoje às 19h tem o resumo em vídeo no Reels do @radardatela"


# ----------------------------------------------------------------------
# Arquivos
# ----------------------------------------------------------------------
def _ler(caminho: str, padrao):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _gravar(caminho: str, dados) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)


def registrar_publicacao(media_id: str, tipo: str, quando: dt.datetime | None = None) -> None:
    """Guarda o id de cada post do Threads para o relatório semanal."""
    quando = quando or dt.datetime.now(FUSO)
    log = _ler(ARQUIVO_LOG, [])
    log.append({"id": media_id, "tipo": tipo, "quando": quando.isoformat(timespec="minutes")})
    limite = (quando - dt.timedelta(days=35)).isoformat()
    _gravar(ARQUIVO_LOG, [l for l in log if l["quando"] >= limite])


# ----------------------------------------------------------------------
# Textos
# ----------------------------------------------------------------------
def _opcao(titulo: str) -> str:
    return titulo if len(titulo) <= 25 else titulo[:24].rstrip() + "…"


def texto_enquete(entradas: list[dict]) -> tuple[str, dict] | None:
    titulos, vistos = [], set()
    for it in entradas:
        op = _opcao(it["t"])
        if op.lower() not in vistos:
            vistos.add(op.lower())
            titulos.append(op)
        if len(titulos) == 4:
            break
    if len(titulos) < 2:
        return None
    letras = ["option_a", "option_b", "option_c", "option_d"]
    texto = "📊 Chegou hoje no streaming. Qual desses você assiste primeiro? Vota aí 👇"
    return texto, dict(zip(letras, titulos))


def resposta_fio(i: int, total: int, item: dict, sinopse: str) -> str:
    plats = item.get("plataformas") or [item.get("plataforma", "")]
    nota = f" · ⭐ {item['n']:.1f}".replace(".", ",") if item.get("v", 0) >= 20 and item.get("n") else ""
    ano = f" ({item['a']})" if item.get("a") else ""
    cab = f"{i}/{total} {'📺' if item['chave'].startswith('tv:') else '🎬'} {item['t']}{ano}\n📍 {', '.join(plats)}{nota}"
    if sinopse:
        return f"{cab}\n\n{sinopse}"
    return cab


def dica_do_dia(data: dt.date) -> str:
    return DICAS[data.toordinal() % len(DICAS)]


# ----------------------------------------------------------------------
# Montagem do dia
# ----------------------------------------------------------------------
def _sinopses(cliente, itens: list[dict]) -> dict[str, str]:
    saida = {}
    for it in itens:
        tipo, ident = it["chave"].split(":")
        try:
            d = cliente.get(f"/{tipo}/{ident}", {"language": config.IDIOMA})
            texto = (d.get("overview") or "").strip()
        except Exception:
            texto = ""
        if len(texto) > 330:
            texto = texto[:330].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
        saida[it["chave"]] = texto
    return saida


def _quando(data: dt.date, chave: str) -> str:
    h, m = HORARIOS[chave]
    return dt.datetime(data.year, data.month, data.day, h, m, tzinfo=FUSO).isoformat()


def montar_dia(lista: list, entradas: list[dict], cliente, data: dt.date,
               com_reel: bool, top_semana: list[dict] | None = None) -> tuple[dict | None, list[dict]]:
    """Retorna (fio_da_manha, itens_agendados).

    fio_da_manha = {"imagem": caminho, "textos": [...]} ou None.
    """
    por_tipo: dict[str, list] = {}
    for p in lista:
        por_tipo.setdefault(p.tipo, []).append(p)
    agendados: list[dict] = []

    # Manhã: resumo em fio
    fio = None
    resumo = (por_tipo.get("resumo") or [None])[0]
    if resumo:
        top = entradas[:5]
        sin = _sinopses(cliente, top)
        textos = [resumo.texto] + [resposta_fio(i, len(top), it, sin.get(it["chave"], ""))
                                   for i, it in enumerate(top, 1)]
        if com_reel:
            textos[-1] = f"{textos[-1]}\n\n{CHAMADA_REEL}"
        fio = {"imagem": resumo.imagem, "textos": textos, "topico": "Streaming"}

    alertas = por_tipo.get("alerta", [])
    # Almoço: 2 destaques
    for p in alertas[:2]:
        agendados.append({"quando": _quando(data, "almoco"), "tipo": "alerta", "texto": p.texto,
                          "imagem": p.imagem, "topico": p.topico})

    # Almoço: prévia da indicação (sexta a domingo) ou gancho do top 10 (domingo)
    dia = data.weekday()
    if dia in PREVIAS:
        agendados.append({"quando": _quando(data, "almoco"), "tipo": "previa_indicacao",
                          "texto": f"{PREVIAS[dia]}\n\n{FIM_PREVIA}", "topico": "Filmes"})
    if dia == 6 and top_semana:
        linhas = [f"{i}. {it['t']} · {it['plataformas'][0]}" for i, it in enumerate(top_semana[:3], 1)]
        agendados.append({"quando": _quando(data, "almoco"), "tipo": "gancho_top10",
                          "texto": "🔟 O que mais bombou no streaming essa semana:\n\n" + "\n".join(linhas)
                          + "\n\n…o top 10 completo tá no nosso Insta @radardatela 👀",
                          "topico": "Streaming"})

    # Noite: enquete + destaque + despedida
    enquete = texto_enquete(entradas)
    if enquete:
        texto, opcoes = enquete
        agendados.append({"quando": _quando(data, "noite"), "tipo": "enquete", "texto": texto,
                          "poll": opcoes, "topico": "Streaming"})
    for p in alertas[2:3] + por_tipo.get("saiu", [])[:1]:
        agendados.append({"quando": _quando(data, "noite"), "tipo": p.tipo, "texto": p.texto,
                          "imagem": p.imagem, "topico": p.topico})

    # 21h: dica da galera
    agendados.append({"quando": _quando(data, "dica"), "tipo": "dica", "texto": dica_do_dia(data),
                      "topico": "Filmes"})
    return fio, agendados


# ----------------------------------------------------------------------
# Fila
# ----------------------------------------------------------------------
def enfileirar(itens: list[dict], data: dt.date, hospedar_fn=None) -> list[str]:
    """Substitui a fila do dia pelos itens novos. As imagens são hospedadas
    agora (o arquivo local some quando a rotina da manhã termina)."""
    erros = []
    prontos = []
    for item in itens:
        try:
            if item.get("imagem"):
                item["imagem_url"] = hospedar_fn(item.pop("imagem"), data)
            if item.get("imagens"):
                item["imagens_url"] = [hospedar_fn(c, data) for c in item.pop("imagens")]
            if item.get("video"):
                item["video_url"] = hospedar_fn(item.pop("video"), data)
        except Exception as e:
            erros.append(f"{item.get('rede', 'threads')} {item['tipo']}: {str(e)[:150]}")
            continue
        prontos.append(item)
    itens = prontos
    fila = [f for f in _ler(ARQUIVO_FILA, []) if not f["quando"].startswith(data.isoformat())]
    _gravar(ARQUIVO_FILA, sorted(fila + itens, key=lambda f: f["quando"]))
    return erros


def publicar_vencidos(agora: dt.datetime, executar) -> tuple[dict, list[str]]:
    """Publica o que já passou do horário (com 10 min de folga).

    `executar(item)` publica um item e devolve o id. Itens de dias anteriores
    que não saíram são descartados para não postar coisa velha.
    Retorna ({rede: quantidade}, erros).
    """
    fila = _ler(ARQUIVO_FILA, [])
    restante, ok, erros = [], {}, []
    limite = (agora + dt.timedelta(minutes=10)).isoformat()
    hoje = agora.date().isoformat()
    for item in fila:
        if item["quando"] > limite:
            restante.append(item)
            continue
        if not item["quando"].startswith(hoje):
            continue  # vencido de outro dia: descarta
        rede = item.get("rede", "threads")
        try:
            media_id = executar(item)
            if media_id is None:  # rede desligada: descarta sem erro
                continue
            if rede == "threads":
                registrar_publicacao(media_id, item["tipo"], agora)
            ok[rede] = ok.get(rede, 0) + 1
        except Exception as e:
            erros.append(f"{rede} {item['tipo']}: {str(e)[:200]}")
            item["tentativas"] = item.get("tentativas", 0) + 1
            if item["tentativas"] < 3:
                restante.append(item)
    _gravar(ARQUIVO_FILA, restante)
    return ok, erros


# ----------------------------------------------------------------------
# Top 10 da semana (exclusivo do Instagram)
# ----------------------------------------------------------------------
def top_da_semana(arquivo_novidades: str, data: dt.date, n: int = 10) -> list[dict]:
    todas = _ler(arquivo_novidades, {})
    inicio = (data - dt.timedelta(days=6)).isoformat()
    vistos, itens = set(), []
    for d in sorted(todas):
        if d < inicio:
            continue
        for it in todas[d]:
            if it["t"] in vistos:
                continue
            vistos.add(it["t"])
            itens.append(it)
    return sorted(itens, key=lambda i: i.get("p", 0), reverse=True)[:n]


def imagens_top10(top: list[dict], data: dt.date, pasta: str) -> list[str]:
    os.makedirs(pasta, exist_ok=True)
    caminhos = []
    for k, it in enumerate(top, 1):
        item = {"chave": it.get("chave") or f"{it.get('tipo', 'movie')}:{it['t']}", "t": it["t"],
                "a": it.get("a"), "n": it.get("n"), "v": it.get("v", 0), "g": it.get("g") or []}
        plat = it["plataformas"][0]
        c = os.path.join(pasta, f"top10_{k:02d}.jpg")
        arte.post_alerta(item, plat, data, c, rotulo=f"TOP 10 DA SEMANA · Nº {k}",
                         frase=f"{arte.preposicao(plat)} {plat}")
        caminhos.append(c)
    return caminhos


def legenda_top10(top: list[dict]) -> str:
    linhas = [f"{i}. {it['t']} · {it['plataformas'][0]}" for i, it in enumerate(top, 1)]
    return ("🔟 Top 10 que chegaram no streaming essa semana\n\n" + "\n".join(linhas)
            + "\n\nSalva pra não esquecer e marca quem precisa ver 👀")
