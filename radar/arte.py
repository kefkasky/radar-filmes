"""Identidade visual do Radar da Tela: logo, capa e posts (Pillow).

Estilo "vivo": fundos de cor forte que variam a cada post, anéis de radar
como elemento gráfico e a nota em forma de selo. Fonte Inter (SIL OFL).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTES = os.path.join(RAIZ, "assets", "fonts")

# Paleta
CREME = (255, 247, 233)
TINTA = (18, 18, 20)
AMARELO = (255, 210, 63)
CORAL = (255, 75, 51)
AZUL = (45, 91, 255)
LILAS = (190, 170, 255)
VERDE = (0, 200, 140)
BRANCO = (255, 255, 255)

# Temas: fundo, texto, texto secundário, destaque (etiqueta/selo), texto do destaque
TEMAS = {
    "amarelo": dict(fundo=AMARELO, txt=TINTA, sec=(70, 58, 20), dest=TINTA, dest_txt=AMARELO, selo=CORAL, selo_txt=BRANCO),
    "azul": dict(fundo=AZUL, txt=BRANCO, sec=(205, 215, 255), dest=AMARELO, dest_txt=TINTA, selo=AMARELO, selo_txt=TINTA),
    "coral": dict(fundo=CORAL, txt=BRANCO, sec=(255, 222, 214), dest=TINTA, dest_txt=BRANCO, selo=AMARELO, selo_txt=TINTA),
    "lilas": dict(fundo=LILAS, txt=TINTA, sec=(60, 45, 110), dest=AZUL, dest_txt=BRANCO, selo=CORAL, selo_txt=BRANCO),
    "noite": dict(fundo=TINTA, txt=CREME, sec=(170, 166, 158), dest=CORAL, dest_txt=BRANCO, selo=CREME, selo_txt=TINTA),
}
ROTACAO = ["amarelo", "azul", "coral", "lilas"]

# Formato dos posts: vertical 4:5 (Instagram e X)
LARGURA, ALTURA = 1080, 1350
MARGEM = 84

MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
FEMININAS = {"Netflix", "HBO Max"}

ESCALA = 2  # desenha em 2x e reduz, para bordas suaves


def preposicao(plataforma: str) -> str:
    """'na Netflix', 'no Prime Video'."""
    return "na" if plataforma in FEMININAS else "no"


def tema_para(chave: str) -> dict:
    """Cor estável por título (o mesmo filme sempre na mesma cor)."""
    n = int(hashlib.md5(chave.encode()).hexdigest(), 16)
    return TEMAS[ROTACAO[n % len(ROTACAO)]]


def fonte(peso: str, tamanho: int) -> ImageFont.FreeTypeFont:
    arquivos = {
        "black": "InterDisplay-Black.otf",
        "bold": "InterDisplay-Bold.otf",
        "semibold": "Inter-SemiBold.otf",
        "medium": "Inter-Medium.otf",
        "regular": "Inter-Regular.otf",
    }
    return ImageFont.truetype(os.path.join(FONTES, arquivos[peso]), int(tamanho * ESCALA))


def misturar(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


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
            self.d.rounded_rectangle(self.s(*caixa), radius=int(raio * ESCALA), fill=cor)
        else:
            self.d.rectangle(self.s(*caixa), fill=cor)

    def circulo(self, cx, cy, r, cor=None, contorno=None, esp=0):
        caixa = self.s(cx - r, cy - r, cx + r, cy + r)
        self.d.ellipse(caixa, fill=cor, outline=contorno, width=int(esp * ESCALA) if esp else 0)

    def linha(self, xy, cor, esp=2):
        self.d.line(self.s(*xy), fill=cor, width=int(esp * ESCALA))

    def colar_girado(self, camada: Image.Image, cx: float, cy: float, graus: float):
        girada = camada.rotate(graus, resample=Image.BICUBIC, expand=True)
        x = int(cx * ESCALA - girada.width / 2)
        y = int(cy * ESCALA - girada.height / 2)
        self.img.paste(girada, (x, y), girada)

    def final(self) -> Image.Image:
        return self.img.resize((self.l, self.a), Image.LANCZOS)


# ----------------------------------------------------------------------
# Marca
# ----------------------------------------------------------------------
def simbolo(t: Tela, cx: float, cy: float, r: float, fundo=TINTA, frente=CREME, ponto=CORAL):
    """Símbolo: disco com anéis de radar e um ponto detectado."""
    t.circulo(cx, cy, r, fundo)
    esp = max(r * 0.075, 1.5)
    for k in (0.72, 0.46):
        t.circulo(cx, cy, r * k, contorno=frente, esp=esp)
    t.circulo(cx, cy, r * 0.16, frente)
    t.circulo(cx + r * 0.42, cy - r * 0.42, r * 0.15, ponto)


def aneis(t: Tela, cx: float, cy: float, cor, r0=140, passo=115, n=9, esp=10):
    """Anéis de radar ao fundo (elemento gráfico da marca)."""
    for i in range(n):
        t.circulo(cx, cy, r0 + i * passo, contorno=cor, esp=esp)


def assinatura(t: Tela, x: float, y: float, tema: dict, tamanho: int = 30):
    """Símbolo + 'radar da tela' (y = centro vertical)."""
    r = tamanho * 0.62
    escuro = sum(tema["fundo"]) < 380
    simbolo(t, x + r, y, r,
            fundo=tema["txt"], frente=tema["fundo"],
            ponto=AMARELO if tema["fundo"] == CORAL else CORAL)
    t.texto((x + 2 * r + tamanho * 0.42, y), "radar da tela", fonte("black", tamanho), tema["txt"], "lm")
    return escuro


def gerar_logo(caminho: str, tamanho: int = 800) -> str:
    """Foto de perfil (quadrada; as redes recortam em círculo)."""
    t = Tela(tamanho, tamanho, AMARELO)
    simbolo(t, tamanho / 2, tamanho / 2, tamanho * 0.36, fundo=TINTA, frente=AMARELO, ponto=CORAL)
    t.final().save(caminho, quality=95)
    return caminho


def gerar_capa(caminho: str) -> str:
    """Capa do X (1500x500)."""
    t = Tela(1500, 500, AZUL)
    aneis(t, 1290, 250, misturar(AZUL, BRANCO, 0.14), r0=90, passo=95, n=10, esp=9)
    simbolo(t, 1290, 250, 150, fundo=AMARELO, frente=AZUL, ponto=CORAL)
    t.texto((110, 160), "radar da tela", fonte("black", 96), BRANCO)
    t.texto((114, 292), "o que entra e sai do streaming, todo dia", fonte("medium", 36), (215, 224, 255))
    for i, cor in enumerate((AMARELO, CORAL, LILAS)):
        t.circulo(124 + i * 40, 372, 12, cor)
    t.final().save(caminho, quality=95)
    return caminho


# ----------------------------------------------------------------------
# Elementos dos posts
# ----------------------------------------------------------------------
def _data_curta(data: dt.date) -> str:
    return f"{data.day:02d} {MESES[data.month - 1]} {data.year}"


def _cabecalho(t: Tela, data: dt.date, tema: dict):
    assinatura(t, MARGEM, 104, tema, 30)
    t.texto((LARGURA - MARGEM, 104), _data_curta(data), fonte("bold", 24), tema["txt"], "rm")


def _rodape(t: Tela, tema: dict):
    y = ALTURA - 84
    t.texto((MARGEM, y), "@radardatela", fonte("black", 28), tema["txt"], "lm")
    t.texto((LARGURA - MARGEM, y), "dados: TMDB / JustWatch", fonte("medium", 22), tema["sec"], "rm")


def _etiqueta(t: Tela, x: float, y: float, txt: str, cor, cor_txt, tam=26) -> float:
    f = fonte("black", tam)
    w = t.largura_txt(txt, f)
    alto = tam * 2.1
    t.ret((x, y, x + w + tam * 1.6, y + alto), cor, raio=alto / 2)
    t.texto((x + tam * 0.8, y + alto / 2), txt, f, cor_txt, "lm")
    return x + w + tam * 1.6


def _selo_nota(t: Tela, nota: str, cx: float, cy: float, cor, cor_txt, r=118, graus=10):
    """Selo redondo, levemente girado, com a nota."""
    lado = int(r * 2 * ESCALA) + 8
    camada = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    c = lado / 2
    # borda serrilhada de selo
    import math
    pontos = []
    dentes = 28
    for i in range(dentes * 2):
        ang = math.pi * i / dentes
        rr = (r if i % 2 == 0 else r * 0.92) * ESCALA
        pontos.append((c + rr * math.cos(ang), c + rr * math.sin(ang)))
    d.polygon(pontos, fill=cor)
    d.text((c, c - 0.20 * r * ESCALA), "★", font=fonte("bold", r * 0.30), fill=cor_txt, anchor="mm")
    d.text((c, c + 0.16 * r * ESCALA), nota, font=fonte("black", r * 0.62), fill=cor_txt, anchor="mm")
    d.text((c, c + 0.58 * r * ESCALA), "NOTA TMDB", font=fonte("bold", r * 0.13), fill=cor_txt, anchor="mm")
    t.colar_girado(camada, cx, cy, graus)


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
    return linhas


def _titulo_ajustado(t: Tela, txt: str, largura: float, altura_max: float):
    """Escolhe o maior corpo que cabe (até 4 linhas)."""
    for tam in (150, 136, 122, 110, 98, 88, 78, 70, 62):
        f = fonte("black", tam)
        linhas = _quebrar(t, txt, f, largura, 4)
        alto = len(linhas) * tam * 0.98
        cabe = all(t.largura_txt(l, f) <= largura for l in linhas)
        if cabe and alto <= altura_max and not linhas[-1].endswith("…"):
            return f, tam, linhas
    f = fonte("black", 62)
    return f, 62, _quebrar(t, txt, f, largura, 4)


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
                saiu: bool = False, rotulo: str | None = None, frase: str | None = None,
                tema: dict | None = None) -> str:
    """Um título em destaque: 'Chegou hoje', 'Saiu do catálogo' ou indicação."""
    tema = tema or (TEMAS["noite"] if saiu else tema_para(item.get("chave", item["t"])))
    t = Tela(LARGURA, ALTURA, tema["fundo"])
    aneis(t, LARGURA + 40, ALTURA - 120, misturar(tema["fundo"], tema["txt"], 0.10))
    _cabecalho(t, data, tema)

    y = 230
    rotulo = rotulo or ("SAIU DO CATÁLOGO" if saiu else ("SÉRIE NOVA" if _tipo_txt(item) == "Série" else "CHEGOU HOJE"))
    _etiqueta(t, MARGEM, y, rotulo, tema["dest"], tema["dest_txt"])
    onde = f"{preposicao(plataforma)} {plataforma}"
    frase = frase or (f"não está mais {onde}" if saiu else f"agora {onde}")
    t.texto((MARGEM, y + 116), frase, fonte("bold", 40), tema["txt"], "lm")

    # título
    topo, base = y + 190, 1000
    f, tam, linhas = _titulo_ajustado(t, item["t"], LARGURA - 2 * MARGEM, base - topo)
    alto = len(linhas) * tam * 0.98
    inicio = topo + max(0, (base - topo - alto) * 0.35)
    for i, l in enumerate(linhas):
        t.texto((MARGEM - 5, inicio + i * tam * 0.98), l, f, tema["txt"], "la")

    # ficha (chips)
    x = MARGEM
    for parte in [p for p in (item.get("a"), _tipo_txt(item), *(item.get("g") or [])[:2]) if p]:
        fc = fonte("bold", 28)
        w = t.largura_txt(parte, fc)
        if x + w + 44 > LARGURA - MARGEM - 250:
            break
        t.ret((x, 1080, x + w + 44, 1140), misturar(tema["fundo"], tema["txt"], 0.14), raio=30)
        t.texto((x + 22, 1110), parte, fc, tema["txt"], "lm")
        x += w + 56

    nota = _nota_txt(item)
    if nota:
        _selo_nota(t, nota, LARGURA - MARGEM - 100, 1100, tema["selo"], tema["selo_txt"])

    _rodape(t, tema)
    t.final().save(caminho, quality=92)
    return caminho


def post_lista(itens: list[dict], data: dt.date, caminho: str, saiu: bool = False) -> str:
    """Resumo: até 7 títulos num cartão. Cada item precisa da chave 'plataforma'."""
    tema = TEMAS["noite"] if saiu else TEMAS["azul"]
    t = Tela(LARGURA, ALTURA, tema["fundo"])
    aneis(t, LARGURA - 60, 120, misturar(tema["fundo"], tema["txt"], 0.10), r0=90, passo=95, n=7, esp=8)
    _cabecalho(t, data, tema)

    y = 200
    if saiu:
        _etiqueta(t, MARGEM, y, "DESPEDIDAS DO DIA", tema["dest"], tema["dest_txt"])
        titulo = ["Saiu do", "streaming"]
    else:
        _etiqueta(t, MARGEM, y, "RESUMO DO DIA", tema["dest"], tema["dest_txt"])
        titulo = ["Chegou hoje", "no streaming"]
    f = fonte("black", 92)
    for i, l in enumerate(titulo):
        t.texto((MARGEM - 4, y + 82 + i * 92), l, f, tema["txt"])

    # cartão
    itens = itens[:7]
    c_topo, c_fim = 500, ALTURA - 140
    t.ret((MARGEM - 20, c_topo, LARGURA - MARGEM + 20, c_fim), CREME, raio=36)
    topo, fim = c_topo + 24, c_fim - 24
    passo = min(112, (fim - topo) / max(len(itens), 1))
    larg_titulo = LARGURA - 2 * MARGEM - 90 - 120
    cores_num = [CORAL, AZUL, AMARELO, VERDE, LILAS, CORAL, AZUL]
    for i, it in enumerate(itens):
        yc = topo + i * passo + passo / 2
        cor_num = TINTA if saiu else cores_num[i % len(cores_num)]
        num_txt = BRANCO if cor_num in (CORAL, AZUL, TINTA, VERDE) else TINTA
        t.circulo(MARGEM + 26, yc, 26, cor_num)
        t.texto((MARGEM + 26, yc), str(i + 1), fonte("black", 26), num_txt, "mm")
        ft = fonte("black", 36)
        nome = it["t"]
        while t.largura_txt(nome, ft) > larg_titulo and len(nome) > 3:
            nome = nome.rstrip("…")[:-1].rstrip() + "…"
        t.texto((MARGEM + 76, yc - 15), nome, ft, TINTA, "lm")
        sub = "  ·  ".join(p for p in (it.get("plataforma"), it.get("a"), _tipo_txt(it)) if p)
        t.texto((MARGEM + 76, yc + 25), sub, fonte("medium", 24), (110, 104, 96), "lm")
        nota = _nota_txt(it)
        if nota:
            t.texto((LARGURA - MARGEM, yc), f"★ {nota}", fonte("black", 30), TINTA, "rm")

    _rodape(t, tema)
    t.final().save(caminho, quality=92)
    return caminho
