"""Configurações do Radar de Filmes."""

import os

# Região dos catálogos (Brasil)
REGIAO = "BR"
IDIOMA = "pt-BR"

# Plataformas acompanhadas: nome exibido -> nomes possíveis no TMDB.
# Os nomes são comparados (sem diferenciar maiúsculas) com a lista oficial
# de provedores do TMDB para o Brasil, e os IDs são descobertos
# automaticamente a cada execução. Vários apelidos porque as plataformas
# mudam de nome (ex.: Max voltou a se chamar HBO Max).
PLATAFORMAS = {
    "Netflix": ["netflix"],
    "Prime Video": ["amazon prime video", "prime video"],
    "Disney+": ["disney plus", "disney+"],
    "HBO Max": ["hbo max", "max"],
    "Globoplay": ["globoplay"],
    "Apple TV+": ["apple tv plus", "apple tv+", "apple tv"],
    "Paramount+": ["paramount plus", "paramount+"],
}

# Tipos de conteúdo coletados
TIPOS = ["movie", "tv"]

# Limite de páginas por consulta (o TMDB não passa de 500 páginas de 20 itens)
MAX_PAGINAS = 500

# Trava de segurança: se uma plataforma "perder" mais que esse percentual
# do catálogo de um dia para o outro, provavelmente é falha da fonte.
LIMITE_REMOCAO_SUSPEITA = 0.30
# ...e só vale quando forem pelo menos tantos títulos (evita falso alarme)
REMOCAO_MINIMA_SUSPEITA = 50

# Quantos destaques mostrar por plataforma no relatório
DESTAQUES_POR_PLATAFORMA = 8

# Caminho do último retrato dos catálogos
ARQUIVO_RETRATO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "catalogo.json"
)

# ----------------------------------------------------------------------
# Posts (Fase 2)
# ----------------------------------------------------------------------
# Um título só vira post se for minimamente conhecido:
POP_MINIMA = 12          # popularidade TMDB
VOTOS_MINIMOS = 40       # ou ter pelo menos tantos votos...
NOTA_MINIMA = 6.0        # ...com nota mínima

ALERTAS_ENTRADA_POR_DIA = 3   # posts individuais "chegou hoje"
ALERTAS_SAIDA_POR_DIA = 1     # posts individuais "saiu do catálogo"
MIN_ITENS_RESUMO = 3          # resumo só sai se houver pelo menos tantos

ARROBA = "@radardatela"
