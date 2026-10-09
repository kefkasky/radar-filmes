"""Escolhe os destaques do dia e monta os posts (imagem + legenda).

Tom: leve, com emoji. Legendas sem link (link no X custa 13x mais).
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from . import arte, config

LIMITE_X = 280


@dataclass
class Post:
    tipo: str        # "alerta", "saiu", "resumo", "resumo_saiu"
    imagem: str
    texto: str


# ----------------------------------------------------------------------
# Seleção
# ----------------------------------------------------------------------
def relevante(item: dict) -> bool:
    if item.get("p", 0) >= config.POP_MINIMA:
        return True
    return item.get("v", 0) >= config.VOTOS_MINIMOS and item.get("n", 0) >= config.NOTA_MINIMA


def _juntar(diferencas: dict, campo: str) -> list[dict]:
    """Junta entradas (ou saídas) de todas as plataformas, sem repetir título."""
    vistos, itens = {}, []
    for plataforma, d in diferencas.items():
        if d.get("base_inicial") or d.get("suspeito"):
            continue
        for it in d.get(campo, []):
            if not relevante(it):
                continue
            chave = it["chave"]
            if chave in vistos:  # mesmo título em 2 plataformas: junta os nomes
                vistos[chave]["plataformas"].append(plataforma)
                continue
            novo = {**it, "plataforma": plataforma, "plataformas": [plataforma]}
            vistos[chave] = novo
            itens.append(novo)
    return sorted(itens, key=lambda i: i["p"], reverse=True)


def _com_generos(item: dict, generos: dict) -> dict:
    nomes = [generos[g] for g in item.get("g", []) if g in generos]
    return {**item, "g": nomes}


# ----------------------------------------------------------------------
# Legendas
# ----------------------------------------------------------------------
def _nota(item: dict) -> str:
    if item.get("v", 0) >= 20 and item.get("n"):
        return f"⭐ {item['n']:.1f}".replace(".", ",")
    return ""


def _onde(item: dict) -> str:
    plats = item.get("plataformas") or [item["plataforma"]]
    if len(plats) == 1:
        return f"{arte.preposicao(plats[0])} {plats[0]}"
    return "em " + ", ".join(plats[:-1]) + " e " + plats[-1]


def _ano(item: dict) -> str:
    return f" ({item['a']})" if item.get("a") else ""


def _ficha(item: dict) -> str:
    partes = [p for p in (_nota(item), ", ".join(item.get("g", [])[:2])) if p]
    return " · ".join(partes)


def texto_alerta(item: dict) -> str:
    tipo = "Série nova" if item["chave"].startswith("tv:") else "Chegou hoje"
    linhas = [f"🍿 {tipo} {_onde(item)}: {item['t']}{_ano(item)}"]
    ficha = _ficha(item)
    if ficha:
        linhas.append(ficha)
    linhas += ["", "Já tá liberado pra dar o play. Vai assistir? 👀"]
    return _cortar("\n".join(linhas))


def texto_saiu(item: dict) -> str:
    linhas = [f"👋 Saiu {_onde(item).replace('na ', 'da ', 1).replace('no ', 'do ', 1)}: "
              f"{item['t']}{_ano(item)}"]
    ficha = _ficha(item)
    if ficha:
        linhas.append(ficha)
    linhas += ["", "Quem viu, viu. Vai fazer falta? 💔"]
    return _cortar("\n".join(linhas))


def texto_resumo(itens: list[dict], saiu: bool = False) -> str:
    cabeca = "📡 Saiu do streaming hoje:" if saiu else "📡 Chegou hoje no streaming:"
    fecho = "Algum desses tava na sua lista? 😬" if saiu else "Qual vai pra sua lista? 🍿"
    linhas = [f"{i + 1}. {it['t']} · {it['plataforma']}" for i, it in enumerate(itens)]
    # tira linhas do fim até caber no X
    while linhas:
        texto = "\n".join([cabeca, "", *linhas, "", fecho])
        if cabe_no_x(texto):
            return texto
        linhas.pop()
    return _cortar(f"{cabeca}\n\n{fecho}")


def peso_x(texto: str) -> int:
    """Tamanho do texto como o X conta: emojis e caracteres especiais valem 2."""
    return sum(1 if ord(c) <= 0x10FF or 0x2000 <= ord(c) <= 0x200D else 2 for c in texto)


def cabe_no_x(texto: str) -> bool:
    return peso_x(texto) <= LIMITE_X


def _cortar(texto: str) -> str:
    if cabe_no_x(texto):
        return texto
    while texto and not cabe_no_x(texto + "…"):
        texto = texto[:-1]
    return texto.rstrip() + "…"


# ----------------------------------------------------------------------
# Montagem
# ----------------------------------------------------------------------
def montar(diferencas: dict, generos: dict, data: dt.date, pasta: str) -> list[Post]:
    os.makedirs(pasta, exist_ok=True)
    posts: list[Post] = []

    entradas = [_com_generos(i, generos) for i in _juntar(diferencas, "entrou")]
    saidas = [_com_generos(i, generos) for i in _juntar(diferencas, "saiu")]

    if len(entradas) >= config.MIN_ITENS_RESUMO:
        caminho = os.path.join(pasta, "resumo.jpg")
        arte.post_lista(entradas[:7], data, caminho)
        posts.append(Post("resumo", caminho, texto_resumo(entradas[:7])))

    for n, item in enumerate(entradas[: config.ALERTAS_ENTRADA_POR_DIA], 1):
        caminho = os.path.join(pasta, f"alerta_{n}.jpg")
        arte.post_alerta(item, item["plataforma"], data, caminho)
        posts.append(Post("alerta", caminho, texto_alerta(item)))

    for n, item in enumerate(saidas[: config.ALERTAS_SAIDA_POR_DIA], 1):
        caminho = os.path.join(pasta, f"saiu_{n}.jpg")
        arte.post_alerta(item, item["plataforma"], data, caminho, saiu=True)
        posts.append(Post("saiu", caminho, texto_saiu(item)))

    if len(saidas) >= config.MIN_ITENS_RESUMO + 1:
        caminho = os.path.join(pasta, "resumo_saiu.jpg")
        arte.post_lista(saidas[:7], data, caminho, saiu=True)
        posts.append(Post("resumo_saiu", caminho, texto_resumo(saidas[:7], saiu=True)))

    return posts
