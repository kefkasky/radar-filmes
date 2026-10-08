"""Coleta dos catálogos de streaming no Brasil pela API do TMDB.

Dados de disponibilidade fornecidos pelo JustWatch, via TMDB.
"""

import datetime as dt
import time

import requests

from . import config

API = "https://api.themoviedb.org/3"


class ErroTMDB(Exception):
    pass


class ClienteTMDB:
    def __init__(self, token: str):
        if not token:
            raise ErroTMDB("TMDB_TOKEN não configurado.")
        self.sessao = requests.Session()
        self.sessao.headers.update(
            {"Authorization": f"Bearer {token}", "accept": "application/json"}
        )
        self.chamadas = 0

    def get(self, caminho: str, params: dict | None = None) -> dict:
        for tentativa in range(6):
            resp = self.sessao.get(f"{API}{caminho}", params=params, timeout=30)
            self.chamadas += 1
            if resp.status_code == 429:
                espera = int(resp.headers.get("Retry-After", "2"))
                time.sleep(max(espera, 1))
                continue
            if resp.status_code >= 500:
                time.sleep(2 * (tentativa + 1))
                continue
            if resp.status_code == 401:
                raise ErroTMDB("Token do TMDB recusado (401). Confira o TMDB_TOKEN.")
            resp.raise_for_status()
            return resp.json()
        raise ErroTMDB(f"TMDB não respondeu após várias tentativas: {caminho}")

    # ------------------------------------------------------------------
    # Provedores
    # ------------------------------------------------------------------
    def provedores_brasil(self) -> dict[str, int]:
        """Retorna {nome_minusculo: provider_id} dos provedores no Brasil."""
        nomes: dict[str, int] = {}
        for tipo in config.TIPOS:
            dados = self.get(
                f"/watch/providers/{tipo}",
                {"watch_region": config.REGIAO, "language": config.IDIOMA},
            )
            for p in dados.get("results", []):
                nomes.setdefault(p["provider_name"].strip().lower(), p["provider_id"])
        return nomes

    def resolver_plataformas(self) -> tuple[dict[str, int], list[str]]:
        """Associa cada plataforma configurada ao seu ID no TMDB.

        Retorna (plataformas_encontradas, plataformas_nao_encontradas).
        """
        disponiveis = self.provedores_brasil()
        encontradas, faltando = {}, []
        for nome_exibido, apelidos in config.PLATAFORMAS.items():
            pid = next((disponiveis[a] for a in apelidos if a in disponiveis), None)
            if pid is None:
                faltando.append(nome_exibido)
            else:
                encontradas[nome_exibido] = pid
        return encontradas, faltando

    def generos(self) -> dict[str, str]:
        """{id_do_genero: nome em português} para filmes e séries."""
        nomes = {}
        for tipo in config.TIPOS:
            dados = self.get(f"/genre/{tipo}/list", {"language": config.IDIOMA})
            for g in dados.get("genres", []):
                nomes.setdefault(str(g["id"]), g["name"])
        return nomes

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------
    def _paginar(self, tipo: str, params: dict) -> tuple[list[dict], bool]:
        """Percorre todas as páginas. Retorna (itens, estourou_limite)."""
        itens, pagina, total = [], 1, 1
        while pagina <= min(total, config.MAX_PAGINAS):
            dados = self.get(f"/discover/{tipo}", {**params, "page": pagina})
            total = dados.get("total_pages", 1)
            itens.extend(dados.get("results", []))
            pagina += 1
        return itens, total > config.MAX_PAGINAS

    def catalogo(self, tipo: str, provider_id: int) -> tuple[dict, bool]:
        """Catálogo de assinatura (flatrate) de uma plataforma no Brasil.

        Retorna ({chave: dados_resumidos}, incompleto).
        """
        base = {
            "watch_region": config.REGIAO,
            "with_watch_providers": provider_id,
            "with_watch_monetization_types": "flatrate",
            "language": config.IDIOMA,
            "sort_by": "popularity.desc",
            "include_adult": "false",
        }
        itens, estourou = self._paginar(tipo, base)
        incompleto = False

        if estourou:
            # Catálogo grande demais para uma consulta: divide por períodos.
            itens = []
            campo = "primary_release_date" if tipo == "movie" else "first_air_date"
            for inicio, fim in _faixas_de_datas():
                params = {**base, f"{campo}.gte": inicio, f"{campo}.lte": fim}
                parte, estourou_parte = self._paginar(tipo, params)
                itens.extend(parte)
                incompleto = incompleto or estourou_parte

        return {_chave(tipo, i): _resumo(tipo, i) for i in itens}, incompleto


def _faixas_de_datas():
    ano_final = dt.date.today().year + 2
    yield "1800-01-01", "1979-12-31"
    yield "1980-01-01", "1989-12-31"
    yield "1990-01-01", "1999-12-31"
    yield "2000-01-01", "2004-12-31"
    yield "2005-01-01", "2009-12-31"
    for ano in range(2010, ano_final + 1):
        yield f"{ano}-01-01", f"{ano}-06-30"
        yield f"{ano}-07-01", f"{ano}-12-31"


def _chave(tipo: str, item: dict) -> str:
    return f"{tipo}:{item['id']}"


def _resumo(tipo: str, item: dict) -> dict:
    titulo = item.get("title") if tipo == "movie" else item.get("name")
    data = item.get("release_date") if tipo == "movie" else item.get("first_air_date")
    return {
        "t": titulo or item.get("original_title") or item.get("original_name") or "?",
        "a": (data or "")[:4],
        "p": round(item.get("popularity") or 0, 1),
        "n": round(item.get("vote_average") or 0, 1),
        "v": item.get("vote_count") or 0,
        "g": [str(g) for g in (item.get("genre_ids") or [])[:3]],
    }
