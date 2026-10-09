"""Indicação de fim de semana (sexta, sábado e domingo, por volta das 18h).

- Sexta: filme de guerra baseado em fatos reais
- Sábado: filme de romance
- Domingo: filme de comédia

Só indica filmes bem avaliados, disponíveis por assinatura no Brasil
numa das plataformas acompanhadas, e nunca repete uma indicação.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random

from . import arte, config
from .posts import Post, cabe_no_x, peso_x, _cortar
from .tmdb import ClienteTMDB

ARQUIVO_HISTORICO = os.path.join(os.path.dirname(config.ARQUIVO_RETRATO), "indicacoes.json")

# Gêneros TMDB: 10752 Guerra, 36 História, 10749 Romance, 35 Comédia, 16 Animação
# Palavra-chave TMDB 9672 = "based on true story"
TEMAS = {
    4: {  # sexta
        "nome": "guerra",
        "rotulo": "SEXTA DE GUERRA",
        "frase": "baseado em fatos reais",
        "emoji": "🎖️",
        "abertura": "Sexta de guerra",
        "fecho": "História real, do jeito que só o cinema conta. Vai encarar? 🍿",
        "buscas": [
            {"with_genres": "10752", "with_keywords": "9672"},
            {"with_genres": "10752,36"},  # reserva: guerra + história
        ],
        "tema_visual": "noite",
    },
    5: {  # sábado
        "nome": "romance",
        "rotulo": "SÁBADO ROMÂNTICO",
        "frase": "pra ver a dois",
        "emoji": "💘",
        "abertura": "Sábado romântico",
        "fecho": "Separa a pipoca e chama o mozão. 💕",
        "buscas": [{"with_genres": "10749", "without_genres": "16"}],
        "tema_visual": "coral",
    },
    6: {  # domingo
        "nome": "comédia",
        "rotulo": "DOMINGO DE COMÉDIA",
        "frase": "pra fechar o fim de semana rindo",
        "emoji": "😂",
        "abertura": "Domingo de comédia",
        "fecho": "Melhor remédio pra segunda-feira que vem aí. 😅",
        "buscas": [{"with_genres": "35", "without_genres": "16"}],
        "tema_visual": "amarelo",
    },
}

VOTOS_MINIMOS = 400
NOTA_MINIMA = 7.0
CANDIDATOS = 60  # sorteia entre os mais populares que passam no filtro


def carregar_historico() -> list[dict]:
    if not os.path.exists(ARQUIVO_HISTORICO):
        return []
    with open(ARQUIVO_HISTORICO, encoding="utf-8") as f:
        return json.load(f)


def salvar_historico(historico: list[dict]) -> None:
    with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=1)


def _candidatos(cliente: ClienteTMDB, busca: dict, plataformas: dict[str, int]) -> list[dict]:
    params = {
        "watch_region": config.REGIAO,
        "with_watch_providers": "|".join(str(p) for p in plataformas.values()),
        "with_watch_monetization_types": "flatrate",
        "language": config.IDIOMA,
        "sort_by": "popularity.desc",
        "vote_count.gte": VOTOS_MINIMOS,
        "vote_average.gte": NOTA_MINIMA,
        "include_adult": "false",
        **busca,
    }
    itens = []
    for pagina in (1, 2, 3):
        dados = cliente.get("/discover/movie", {**params, "page": pagina})
        itens += dados.get("results", [])
        if pagina >= dados.get("total_pages", 1) or len(itens) >= CANDIDATOS:
            break
    return itens[:CANDIDATOS]


def _onde_assistir(cliente: ClienteTMDB, filme_id: int, plataformas: dict[str, int]) -> list[str]:
    dados = cliente.get(f"/movie/{filme_id}/watch/providers")
    br = dados.get("results", {}).get(config.REGIAO, {})
    ids = {p["provider_id"] for p in br.get("flatrate", [])}
    return [nome for nome, pid in plataformas.items() if pid in ids]


def escolher(cliente: ClienteTMDB, dia_semana: int, data: dt.date) -> dict | None:
    """Escolhe o filme do dia. Retorna None se não for sexta/sábado/domingo."""
    tema = TEMAS.get(dia_semana)
    if not tema:
        return None
    plataformas, _ = cliente.resolver_plataformas()
    ja_indicados = {h["id"] for h in carregar_historico()}
    sorteio = random.Random(data.isoformat())  # mesmo dia = mesma escolha

    for busca in tema["buscas"]:
        candidatos = [c for c in _candidatos(cliente, busca, plataformas) if c["id"] not in ja_indicados]
        sorteio.shuffle(candidatos)
        for c in candidatos[:10]:
            onde = _onde_assistir(cliente, c["id"], plataformas)
            if not onde:
                continue
            det = cliente.get(f"/movie/{c['id']}", {"language": config.IDIOMA})
            return {
                "id": c["id"],
                "chave": f"movie:{c['id']}",
                "t": det.get("title") or c.get("title"),
                "a": (det.get("release_date") or "")[:4],
                "n": round(det.get("vote_average") or 0, 1),
                "v": det.get("vote_count") or 0,
                "g": [g["name"] for g in det.get("genres", [])][:2],
                "duracao": det.get("runtime") or 0,
                "sinopse": (det.get("overview") or "").strip(),
                "plataformas": onde,
                "plataforma": onde[0],
                "tema": tema,
            }
    return None


def _duracao(min_: int) -> str:
    if not min_:
        return ""
    h, m = divmod(min_, 60)
    return f"{h}h{m:02d}" if h else f"{m}min"


def texto(filme: dict) -> str:
    tema = filme["tema"]
    plats = filme["plataformas"]
    onde = plats[0] if len(plats) == 1 else ", ".join(plats[:-1]) + " e " + plats[-1]
    ficha = " · ".join(p for p in (
        f"⭐ {filme['n']:.1f}".replace(".", ",") if filme.get("v", 0) >= 20 else "",
        _duracao(filme["duracao"]),
        "baseado em fatos reais" if tema["nome"] == "guerra" else "",
    ) if p)
    topo = [f"{tema['emoji']} {tema['abertura']}: {filme['t']} ({filme['a']})", ficha, f"📺 {onde}"]
    fecho = tema["fecho"]
    base = "\n".join(l for l in topo if l)
    sinopse = filme.get("sinopse", "")
    # sinopse entra se couber no limite do X; senão é encurtada por palavra
    palavras = sinopse.split()
    while palavras:
        trecho = " ".join(palavras)
        if trecho != sinopse:
            trecho = trecho.rstrip(",.;:") + "…"
        candidato = f"{base}\n\n{trecho}\n\n{fecho}"
        if cabe_no_x(candidato) and len(palavras) >= 6:
            return candidato
        palavras.pop()
    return _cortar(f"{base}\n\n{fecho}")


def montar(filme: dict, data: dt.date, pasta: str) -> Post:
    os.makedirs(pasta, exist_ok=True)
    tema = filme["tema"]
    onde = f"{arte.preposicao(filme['plataforma'])} {filme['plataforma']}"
    caminho = os.path.join(pasta, f"indicacao_{data.isoformat()}.jpg")
    arte.post_alerta(
        filme, filme["plataforma"], data, caminho,
        rotulo=tema["rotulo"], frase=f"{tema['frase']} · {onde}",
        tema=arte.TEMAS[tema["tema_visual"]],
    )
    return Post("indicacao", caminho, texto(filme))


def registrar(filme: dict, data: dt.date) -> None:
    historico = carregar_historico()
    historico.append({"data": data.isoformat(), "id": filme["id"], "titulo": filme["t"],
                      "tema": filme["tema"]["nome"]})
    salvar_historico(historico)
