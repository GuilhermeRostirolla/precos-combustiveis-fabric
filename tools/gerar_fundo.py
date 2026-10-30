"""Gera a imagem de fundo da página "Visão geral" (tools/recursos/fundo_visao_geral.png).

Desenha em HTML as molduras e os textos fixos do desenho e tira um print com o Chromium do Playwright,
em resolução dobrada para ficar nítido no Power BI.

    python tools/gerar_fundo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_visao_geral as L  # noqa: E402

DESTINO = Path(__file__).resolve().parent / "recursos" / "fundo_visao_geral.png"


def caixa(x, y, w, h, fundo=L.COR["cartao"], borda=True, raio=10):
    b = f"border:1px solid {L.COR['borda']};" if borda else ""
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background:{fundo};{b}border-radius:{raio}px;box-sizing:border-box"></div>')


def texto(t, x, y, tamanho, peso, cor, w=None):
    largura = f"width:{w}px;" if w else "white-space:nowrap;"
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;{largura}font-size:{tamanho}px;'
            f'font-weight:{peso};color:{cor};line-height:1.25">{t}</div>')


def html() -> str:
    partes = [texto(L.TITULO["texto"], L.TITULO["x"], L.TITULO["y"], 26, 700, L.COR["texto"]),
              texto(L.SUBTITULO["texto"], L.SUBTITULO["x"], L.SUBTITULO["y"], 13, 400, L.COR["suave"])]
    for f in L.FILTROS:
        partes.append(caixa(f["x"], f["y"], f["w"], f["h"], raio=8))
        partes.append(texto(f["rotulo"], f["x"] + 12, f["y"] + 10, 12, 500, L.COR["suave"]))
    for i, titulo in enumerate(L.CARTOES):
        x = L.cartao_x(i)
        partes.append(caixa(x, L.CARTOES_Y, L.CARTAO_W, L.CARTOES_H))
        partes.append(texto(titulo, x + 16, L.CARTOES_Y + 14, 12, 500, L.COR["suave"]))
    g, p, c = L.GRAFICO, L.PAINEL, L.CONCLUSAO
    partes += [caixa(g["x"], g["y"], g["w"], g["h"]),
               texto(g["titulo"], g["x"] + 16, g["y"] + 14, 14, 600, L.COR["texto"]),
               texto(g["subtitulo"], g["x"] + 16, g["y"] + 34, 12, 400, L.COR["suave"]),
               caixa(p["x"], p["y"], p["w"], p["h"]),
               texto(p["rotulo"], p["x"] + 16, p["y"] + 48, 12, 400, L.COR["suave"]),
               caixa(c["x"], c["y"], c["w"], c["h"], fundo=L.COR["caixa"], borda=False, raio=8)]
    return ('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0}'
            f'body{{width:1280px;height:720px;background:{L.COR["pagina"]};position:relative;'
            'font-family:Inter,sans-serif;-webkit-font-smoothing:antialiased}</style></head><body>'
            + "".join(partes) + "</body></html>")


def gerar(destino: Path = DESTINO) -> Path:
    from playwright.sync_api import sync_playwright
    destino.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        pagina.set_content(html())
        pagina.screenshot(path=str(destino))
        navegador.close()
    return destino


if __name__ == "__main__":
    print(f"fundo gerado em {gerar()}")
