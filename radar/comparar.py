"""Compara o catálogo de hoje com o anterior e monta o relatório."""

import html

from . import config

ROTULO_TIPO = {"movie": "🎬", "tv": "📺"}


def comparar(anterior: dict, atual: dict, incompletas: set | None = None) -> dict:
    """Compara dois retratos {plataforma: {chave: item}}.

    Retorna {plataforma: {"entrou": [...], "saiu": [...], "suspeito": bool}}.
    Plataformas sem retrato anterior são tratadas como "base inicial".
    Em plataformas com coleta incompleta, saídas não são reportadas
    (o título pode só não ter sido alcançado pela consulta).
    """
    incompletas = incompletas or set()
    resultado = {}
    for plataforma, itens_hoje in atual.items():
        itens_antes = anterior.get(plataforma)
        if itens_antes is None:
            resultado[plataforma] = {"base_inicial": True, "total": len(itens_hoje)}
            continue

        entrou = [k for k in itens_hoje if k not in itens_antes]
        saiu = [] if plataforma in incompletas else [
            k for k in itens_antes if k not in itens_hoje
        ]

        suspeito = (
            bool(itens_antes)
            and len(saiu) >= config.REMOCAO_MINIMA_SUSPEITA
            and len(saiu) / len(itens_antes) > config.LIMITE_REMOCAO_SUSPEITA
        )

        resultado[plataforma] = {
            "entrou": _ordenar(entrou, itens_hoje),
            "saiu": _ordenar(saiu, itens_antes),
            "suspeito": suspeito,
            "total": len(itens_hoje),
        }
    return resultado


def _ordenar(chaves, itens):
    return sorted(
        ({"chave": k, **itens[k]} for k in chaves),
        key=lambda i: i["p"],
        reverse=True,
    )


def _linha(item: dict) -> str:
    tipo = item["chave"].split(":")[0]
    ano = f" ({item['a']})" if item.get("a") else ""
    nota = (
        f" ⭐ {item['n']:.1f}".replace(".", ",")
        if item.get("v", 0) >= 20 and item.get("n")
        else ""
    )
    return f"{ROTULO_TIPO.get(tipo, '•')} {html.escape(item['t'])}{ano}{nota}"


def montar_relatorio(diferencas: dict, avisos: list[str], data_txt: str) -> str:
    """Texto do relatório diário (HTML do Telegram)."""
    partes = [f"<b>📡 Radar de Filmes — {data_txt}</b>"]

    if all(d.get("base_inicial") for d in diferencas.values()) and diferencas:
        partes.append(
            "Primeira coleta: base de comparação criada. "
            "A partir de amanhã chegam as novidades."
        )
        for plataforma, d in diferencas.items():
            partes.append(f"• {html.escape(plataforma)}: {d['total']:,} títulos".replace(",", "."))
    else:
        sem_novidade = []
        for plataforma, d in diferencas.items():
            if d.get("base_inicial"):
                partes.append(
                    f"\n<b>{html.escape(plataforma)}</b>: base criada hoje ({d['total']} títulos)."
                )
                continue
            if d["suspeito"]:
                partes.append(
                    f"\n⚠️ <b>{html.escape(plataforma)}</b>: {len(d['saiu'])} títulos "
                    "teriam saído de uma vez. Parece falha da fonte; ignorado hoje."
                )
                continue
            if not d["entrou"] and not d["saiu"]:
                sem_novidade.append(plataforma)
                continue

            bloco = [f"\n<b>{html.escape(plataforma)}</b>"]
            if d["entrou"]:
                bloco.append(f"✅ Entraram {len(d['entrou'])}:")
                destaque = d["entrou"][: config.DESTAQUES_POR_PLATAFORMA]
                bloco += [_linha(i) for i in destaque]
                resto = len(d["entrou"]) - len(destaque)
                if resto > 0:
                    bloco.append(f"   …e mais {resto}")
            if d["saiu"]:
                bloco.append(f"❌ Saíram {len(d['saiu'])}:")
                destaque = d["saiu"][:5]
                bloco += [_linha(i) for i in destaque]
                resto = len(d["saiu"]) - len(destaque)
                if resto > 0:
                    bloco.append(f"   …e mais {resto}")
            partes.append("\n".join(bloco))

        if sem_novidade:
            partes.append("\nSem mudanças: " + ", ".join(html.escape(p) for p in sem_novidade))

    if avisos:
        partes.append("\n<i>Avisos:</i>\n" + "\n".join(f"• {html.escape(a)}" for a in avisos))

    partes.append("\n<i>Dados: TMDB / JustWatch</i>")
    return "\n".join(partes)


def aplicar_retrato(
    anterior: dict, atual: dict, diferencas: dict, incompletas: set | None = None
) -> dict:
    """Retrato a ser salvo.

    - Plataformas suspeitas mantêm o retrato anterior.
    - Plataformas com coleta incompleta somam o de antes com o de hoje,
      para não "reaparecerem" títulos amanhã.
    """
    incompletas = incompletas or set()
    novo = {}
    for plataforma, itens in atual.items():
        if diferencas.get(plataforma, {}).get("suspeito"):
            novo[plataforma] = anterior[plataforma]
        elif plataforma in incompletas and plataforma in anterior:
            novo[plataforma] = {**anterior[plataforma], **itens}
        else:
            novo[plataforma] = itens
    # Plataformas que falharam hoje mantêm o retrato anterior
    for plataforma, itens in anterior.items():
        novo.setdefault(plataforma, itens)
    return novo
