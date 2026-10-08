"""Identidade visual do Radar da Tela: logo, capa e posts (Pillow).

Estilo "limpo e moderno": fundo creme, tinta quase preta, um único
destaque em coral. Fonte Inter (SIL Open Font License).
"""

from __future__ import annotations

import datetime as dt
import os

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTES = os.path.join(RAIZ, "assets", "fonts")

# Paleta
CREME = (245, 242, 235)
TINTA = (17, 17, 17)
CINZA = (107, 104, 98)
LINHA = (217, 212, 200)
CORAL = (229, 64, 42)
BRANCO = (255, 255, 255)

# Formato dos posts: vertical 4:5 (Instagram e X)
LARGURA, ALTURA = 1080, 1350
MARGEM = 84

MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

ESCALA = 2  # desenha em 2x e reduz, para bordas suaves


def fonte(peso: str, tamanho: int) -> ImageFont.FreeTypeFont:
    arquivos = {
        "black": "InterDisplay-Black.otf",
        "bold": "InterDisplay-Bold.otf",
        "semibold": "Inter-SemiBold.otf",
        "medium": "Inter-Medium.otf",
        "regular": "Inter-Regular.otf",
    }
    return ImageFont.truetype(os.path.join(FONTES, arquivos[peso]), tamanho * ESCALA)


class Tela:
    """Canvas em escala 2x com coordenadas em pixels finais."""

    def __init__(self, largura: int, altura: int, fundo=CREME):
        self.l, self.a = largura, altura
        self.img = Image.new("RGB", (largura * ESCALA, altura * ESCALA), fundo)
        self.d = ImageDraw.Draw(self.img)

    def s(self, *v):
        return [int(x * ESCALA) for x in v]

    def texto(self, xy, txt, f, cor=TINTA, anchor="la"):
        self.d.text(self.s(*xy), txt, font=f, fill=cor, anchor=anchor)

    def largura_txt(self, txt, f) -> float:
        return self.d.textlength(txt, font=f) / ESCALA

    def ret(self, caixa, cor, raio=0):
        if raio:
            self.d.rounded_rectangle(self.s(*caixa), radius=raio * ESCALA, fill=cor)
        else:
            self.d.rectangle(self.s(*caixa), fill=cor)

    def linha(self, xy, cor=LINHA, esp=2):
        self.d.line(self.s(*xy), fill=cor, width=esp * ESCALA)

    def final(self) -> Image.Image:
        return self.img.resize((self.l, self.a), Image.LANCZOS)


# ----------------------------------------------------------------------
# Marca
# ----------------------------------------------------------------------
def simbolo(t: Tela, cx: float, cy: float, r: float, fundo=TINTA, frente=CREME):
    """Símbolo: disco escuro com anéis de radar e um ponto coral."""
    d, s = t.d, ESCALA
    d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], fill=fundo)
    esp = max(r * 0.075, 1.5)
    for k in (0.72, 0.46):
        rr = r * k
        d.ellipse(
            [(cx - rr) * s, (cy - rr) * s, (cx + rr) * s, (cy + rr) * s],
            outline=frente,
            width=int(esp * s),
        )
    rc = r * 0.16
    d.ellipse([(cx - rc) * s, (cy - rc) * s, (cx + rc) * s, (cy + rc) * s], fill=frente)
    # ponto detectado
    px, py, rp = cx + r * 0.42, cy - r * 0.42, r * 0.15
    d.ellipse([(px - rp) * s, (py - rp) * s, (px + rp) * s, (py + rp) * s], fill=CORAL)


def assinatura(t: Tela, x: float, y: float, tamanho: int = 30, cor=TINTA):
    """Símbolo + 'radar da tela' (y = centro vertical)."""
    r = tamanho * 0.62
    simbolo(t, x + r, y, r)
    t.texto((x + 2 * r + tamanho * 0.42, y), "radar da tela", fonte("black", tamanho), cor, "lm")


def gerar_logo(caminho: str, tamanho: int = 800) -> str:
    """Foto de perfil (quadrada; as redes recortam em círculo)."""
    t = Tela(tamanho, tamanho, CREME)
    simbolo(t, tamanho / 2, tamanho / 2, tamanho * 0.36)
    t.final().save(caminho, quality=95)
    return caminho


def gerar_capa(caminho: str) -> str:
    """Capa do X (1500x500)."""
    t = Tela(1500, 500, CREME)
    simbolo(t, 1500 - 250, 250, 170)
    t.texto((110, 160), "radar da tela", fonte("black", 92))
    t.texto(
        (112, 290),
        "o que entra e sai do streaming, todo dia",
        fonte("medium", 34),
        CINZA,
    )
    t.ret((112, 360, 112 + 64, 366), CORAL)
    t.final().save(caminho, quality=95)
    return caminho


# ----------------------------------------------------------------------
# Elementos dos posts
# ----------------------------------------------------------------------
FEMININAS = {"Netflix", "HBO Max"}


def preposicao(plataforma: str) -> str:
    """'na Netflix', 'no Prime Video'."""
    return "na" if plataforma in FEMININAS else "no"


def _data_curta(data: dt.date) -> str:
    return f"{data.day:02d} {MESES[data.month - 1]} {data.year}"


def _cabecalho(t: Tela, data: dt.date):
    assinatura(t, MARGEM, 110, 30)
    t.texto((LARGURA - MARGEM, 110), _data_curta(data), fonte("semibold", 24), CINZA, "rm")
    t.linha((MARGEM, 168, LARGURA - MARGEM, 168))


def _rodape(t: Tela):
    y = ALTURA - 96
    t.linha((MARGEM, y - 40, LARGURA - MARGEM, y - 40))
    t.texto((MARGEM, y), "@radardatela", fonte("bold", 26), TINTA, "lm")
    t.texto((LARGURA - MARGEM, y), "dados: TMDB / JustWatch", fonte("regular", 22), CINZA, "rm")


def _etiqueta(t: Tela, x: float, y: float, txt: str, cor=CORAL, cor_txt=BRANCO) -> float:
    f = fonte("bold", 24)
    w = t.largura_txt(txt, f)
    t.ret((x, y, x + w + 40, y + 50), cor, raio=25)
    t.texto((x + 20, y + 25), txt, f, cor_txt, "lm")
    return x + w + 40


def _quebrar(t: Tela, txt: str, f, largura_max: float, max_linhas: int):
    palavras, linhas, atual = txt.split(), [], ""
    for p in palavras:
        teste = f"{atual} {p}".strip()
        if t.largura_txt(teste, f) <= largura_max:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        while linhas[-1] and t.largura_txt(linhas[-1] + "…", f) > largura_max:
            linhas[-1] = linhas[-1][:-1].rstrip()
        linhas[-1] += "…"
    # palavra isolada maior que a linha
    return linhas


def _titulo_ajustado(t: Tela, txt: str, largura: float, altura_max: float):
    """Escolhe o maior corpo que cabe (até 4 linhas)."""
    for tam in (128, 116, 104, 94, 84, 76, 68, 60):
        f = fonte("black", tam)
        linhas = _quebrar(t, txt, f, largura, 4)
        alto = len(linhas) * tam * 1.04
        cabe = all(t.largura_txt(l, f) <= largura for l in linhas)
        if cabe and alto <= altura_max and not linhas[-1].endswith("…"):
            return f, tam, linhas
    f = fonte("black", 60)
    return f, 60, _quebrar(t, txt, f, largura, 4)


def _nota_txt(item: dict) -> str | None:
    if item.get("v", 0) >= 20 and item.get("n"):
        return f"{item['n']:.1f}".replace(".", ",")
    return None


def _tipo_txt(item: dict) -> str:
    return "Série" if item.get("chave", "").startswith("tv:") else "Filme"


# ----------------------------------------------------------------------
# Posts
# ----------------------------------------------------------------------
def post_alerta(item: dict, plataforma: str, data: dt.date, caminho: str,
                saiu: bool = False) -> str:
    """Um título em destaque: 'Chegou hoje' ou 'Saiu do catálogo'."""
    t = Tela(LARGURA, ALTURA)
    _cabecalho(t, data)

    y = 250
    if saiu:
        _etiqueta(t, MARGEM, y, "SAIU DO CATÁLOGO", TINTA, CREME)
    else:
        _etiqueta(t, MARGEM, y, "CHEGOU HOJE")
    onde = f"{preposicao(plataforma)} {plataforma}"
    frase = f"não está mais {onde}" if saiu else f"agora {onde}"
    t.texto((MARGEM, y + 112), frase, fonte("medium", 34), CINZA, "lm")

    # título
    topo, base = y + 190, 1000
    f, tam, linhas = _titulo_ajustado(t, item["t"], LARGURA - 2 * MARGEM, base - topo)
    alto = len(linhas) * tam * 1.04
    inicio = topo + max(0, (base - topo - alto) * 0.45)
    for i, l in enumerate(linhas):
        t.texto((MARGEM - 4, inicio + i * tam * 1.04), l, f, TINTA, "la")

    # ficha
    y2 = 1060
    partes = [p for p in (item.get("a"), _tipo_txt(item), *(item.get("g") or [])[:2]) if p]
    t.texto((MARGEM, y2 + 38), "  ·  ".join(partes), fonte("medium", 32), TINTA, "lm")
    nota = _nota_txt(item)
    if nota:
        fx = fonte("black", 76)
        t.texto((LARGURA - MARGEM, y2 + 34), nota, fx, CORAL if not saiu else TINTA, "rm")
        w = t.largura_txt(nota, fx)
        t.texto((LARGURA - MARGEM - w - 16, y2 + 38), "★", fonte("bold", 40),
                CORAL if not saiu else TINTA, "rm")
        t.texto((LARGURA - MARGEM, y2 + 98), "nota TMDB", fonte("regular", 22), CINZA, "rm")

    _rodape(t)
    t.final().save(caminho, quality=92)
    return caminho


def post_lista(itens: list[dict], data: dt.date, caminho: str, saiu: bool = False) -> str:
    """Resumo: até 7 títulos. Cada item precisa da chave 'plataforma'."""
    t = Tela(LARGURA, ALTURA)
    _cabecalho(t, data)

    y = 230
    if saiu:
        _etiqueta(t, MARGEM, y, "SAÍRAM DO CATÁLOGO", TINTA, CREME)
        titulo = ["Saiu do", "streaming"]
    else:
        _etiqueta(t, MARGEM, y, "RESUMO DO DIA")
        titulo = ["Chegou hoje", "no streaming"]
    f = fonte("black", 84)
    for i, l in enumerate(titulo):
        t.texto((MARGEM - 3, y + 80 + i * 86), l, f)

    itens = itens[:7]
    topo, fim = 570, ALTURA - 160
    passo = min(118, (fim - topo) / max(len(itens), 1))
    larg_titulo = LARGURA - 2 * MARGEM - 70 - 130
    for i, it in enumerate(itens):
        yc = topo + i * passo + passo / 2
        t.texto((MARGEM, yc), f"{i + 1:02d}", fonte("bold", 26), CORAL if not saiu else CINZA, "lm")
        ft = fonte("bold", 38)
        nome = it["t"]
        while t.largura_txt(nome, ft) > larg_titulo and len(nome) > 3:
            nome = nome[:-2].rstrip() + "…" if not nome.endswith("…") else nome[:-2].rstrip() + "…"
        t.texto((MARGEM + 70, yc - 15), nome, ft, TINTA, "lm")
        sub = "  ·  ".join(p for p in (it.get("plataforma"), it.get("a"), _tipo_txt(it)) if p)
        t.texto((MARGEM + 70, yc + 26), sub, fonte("regular", 25), CINZA, "lm")
        nota = _nota_txt(it)
        if nota:
            t.texto((LARGURA - MARGEM, yc), f"★ {nota}", fonte("bold", 32), TINTA, "rm")
        if i < len(itens) - 1:
            t.linha((MARGEM + 70, yc + passo / 2, LARGURA - MARGEM, yc + passo / 2), LINHA, 1)

    _rodape(t)
    t.final().save(caminho, quality=92)
    return caminho
