"""Reels automáticos (vídeo vertical 9:16) a partir dos posts do dia.

Estrutura: capa (2 s) → cada post (2,6 s) → chamada "siga" (2,2 s),
com transição suave. Sem música (evita problema de direitos autorais);
leva uma faixa de áudio silenciosa porque o Instagram espera áudio AAC.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
import tempfile

from PIL import Image

from . import arte

L, A = 1080, 1920
FPS = 30
DUR_CAPA, DUR_POST, DUR_FIM, TRANS = 2.0, 2.6, 2.2, 0.4


def _etiqueta_centro(t, y, txt, cor, cor_txt, tam):
    w = t.largura_txt(txt, arte.fonte("black", tam)) + tam * 1.6
    arte._etiqueta(t, L / 2 - w / 2, y, txt, cor, cor_txt, tam=tam)


def _capa(data: dt.date, titulo: list[str], caminho: str) -> str:
    tema = arte.TEMAS["azul"]
    t = arte.Tela(L, A, tema["fundo"])
    arte.aneis(t, L / 2, A / 2, arte.misturar(tema["fundo"], tema["txt"], 0.10), r0=120, passo=120, n=10)
    arte.simbolo(t, L / 2, 520, 150, fundo=arte.AMARELO, frente=tema["fundo"], ponto=arte.CORAL)
    f = arte.fonte("black", 116)
    for i, linha in enumerate(titulo):
        t.texto((L / 2, 880 + i * 124), linha, f, tema["txt"], "ma")
    _etiqueta_centro(t, 1220, arte._data_curta(data), arte.AMARELO, arte.TINTA, 30)
    t.texto((L / 2, A - 200), "@radardatela", arte.fonte("black", 40), tema["txt"], "ma")
    t.final().save(caminho, quality=94)
    return caminho


def _slide(imagem: str, caminho: str, indice: int, total: int) -> str:
    tema = arte.TEMAS["noite"]
    t = arte.Tela(L, A, tema["fundo"])
    arte.assinatura(t, 70, 150, tema, 34)
    t.texto((L - 70, 150), f"{indice}/{total}", arte.fonte("bold", 30), tema["sec"], "rm")
    t.texto((L / 2, A - 230), "siga pra não perder nada", arte.fonte("bold", 40), tema["txt"], "ma")
    base = t.final()
    post = Image.open(imagem).convert("RGB").resize((1000, 1250), Image.LANCZOS)
    base.paste(post, ((L - 1000) // 2, 300))
    base.save(caminho, quality=94)
    return caminho


def _fim(caminho: str) -> str:
    tema = arte.TEMAS["amarelo"]
    t = arte.Tela(L, A, tema["fundo"])
    arte.aneis(t, L / 2, A / 2 - 100, arte.misturar(tema["fundo"], tema["txt"], 0.10), r0=120, passo=120, n=10)
    arte.simbolo(t, L / 2, 640, 180, fundo=arte.TINTA, frente=tema["fundo"], ponto=arte.CORAL)
    f = arte.fonte("black", 104)
    for i, linha in enumerate(["Siga o", "radar da tela"]):
        t.texto((L / 2, 960 + i * 112), linha, f, tema["txt"], "ma")
    t.texto((L / 2, 1260), "todo dia o que entra e sai do streaming", arte.fonte("bold", 38), tema["txt"], "ma")
    _etiqueta_centro(t, 1380, "@radardatela", arte.TINTA, arte.AMARELO, 34)
    t.final().save(caminho, quality=94)
    return caminho


def gerar(imagens: list[str], data: dt.date, caminho: str,
          titulo: list[str] | None = None) -> str:
    """Gera o MP4 do Reel. `imagens` = posts (1080x1350) na ordem."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg não encontrado")
    titulo = titulo or ["Chegou hoje", "no streaming"]
    imagens = imagens[:6]
    with tempfile.TemporaryDirectory() as tmp:
        quadros = [_capa(data, titulo, os.path.join(tmp, "0.jpg"))]
        for i, img in enumerate(imagens, 1):
            quadros.append(_slide(img, os.path.join(tmp, f"{i}.jpg"), i, len(imagens)))
        quadros.append(_fim(os.path.join(tmp, "fim.jpg")))
        duracoes = [DUR_CAPA] + [DUR_POST] * len(imagens) + [DUR_FIM]

        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for q, d in zip(quadros, duracoes):
            cmd += ["-loop", "1", "-t", f"{d + TRANS:.2f}", "-i", q]
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]

        filtros, deslocamento = [], 0.0
        for i in range(len(quadros)):
            filtros.append(f"[{i}:v]scale={L}:{A},fps={FPS},format=yuv420p,setsar=1[v{i}]")
        anterior = "[v0]"
        for i in range(1, len(quadros)):
            deslocamento += duracoes[i - 1]
            saida = f"[x{i}]"
            filtros.append(f"{anterior}[v{i}]xfade=transition=fade:duration={TRANS}:"
                           f"offset={deslocamento:.2f}{saida}")
            anterior = saida
        total = sum(duracoes) + TRANS
        cmd += ["-filter_complex", ";".join(filtros), "-map", anterior,
                "-map", f"{len(quadros)}:a", "-t", f"{total:.2f}",
                "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-r", str(FPS), "-b:v", "5M", "-maxrate", "8M", "-bufsize", "10M",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                "-movflags", "+faststart", caminho]
        subprocess.run(cmd, check=True)
    return caminho
