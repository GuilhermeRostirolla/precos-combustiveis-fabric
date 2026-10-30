"""Gera a imagem de fundo da página "Visão geral" (tools/recursos/fundo_visao_geral.png).

Desenha em HTML as molduras, títulos, rótulos e trilhos das barras do desenho e tira um print com o Chromium do
Playwright, em resolução dobrada para ficar nítido no Power BI.

    python tools/gerar_fundo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_visao_geral as L  # noqa: E402

DESTINO = Path(__file__).resolve().parent / "recursos" / "fundo_visao_geral.png"
C = L.COR


def caixa(x, y, w, h, fundo=C["cartao"], borda=True, raio=10):
    b = f"border:1px solid {C['borda']};" if borda else ""
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background:{fundo};{b}border-radius:{raio}px;box-sizing:border-box"></div>')


def texto(t, x, y, tamanho, peso, cor):
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;white-space:nowrap;font-size:{tamanho}px;'
            f'font-weight:{peso};color:{cor};line-height:1.2">{t}</div>')


def html() -> str:
    partes = [texto(L.TITULO, 28, 24, 26, 700, C["texto"]), texto(L.SUBTITULO, 28, 59, 13, 400, C["suave"])]
    # filtros
    for f in (L.COMBUSTIVEL, L.ESTADO, L.SEMANA):
        partes.append(caixa(f["x"], f["y"], f["w"], f["h"], raio=8))
        partes.append(texto(f["rotulo"], f["x"] + 12, f["y"] + 8, 12, 500, C["suave"]))
    # cartões
    for i, titulo in enumerate(L.CARTOES):
        x, y = L.cartao_x(i), L.CARTAO_Y
        partes += [caixa(x, y, L.CARTAO_W, L.CARTAO_H), texto(titulo, x + 16, y + 16, 12, 500, C["suave"])]
        if i in (0, 2):
            partes.append(texto("/litro", x + L.SUFIXO_LITRO_X, y + 54, 13, 500, C["suave"]))
        if i == 1:
            partes += [texto("no posto", x + 16, y + 76, 11, 400, C["suave"]),
                       texto("na refinaria", x + 112, y + 76, 11, 400, C["suave"])]
        if i == 4:
            marca = x + L.BARRA_X + round(0.7 * L.BARRA_W)
            partes.append(f'<div style="position:absolute;left:{marca}px;top:{y + L.BARRA_Y - 4}px;width:2px;'
                          f'height:{L.BARRA_H + 8}px;background:{C["texto"]}"></div>')
    # gráfico
    g = L.GRAFICO
    partes += [caixa(g["x"], g["y"], g["w"], g["h"]),
               texto(g["titulo"], g["x"] + 16, g["y"] + 15, 14, 600, C["texto"]),
               texto(g["subtitulo"], g["x"] + 16, g["y"] + 35, 12, 400, C["suave"]),
               caixa(L.PONTE["x"], L.PONTE["y"], L.PONTE["w"], L.PONTE["h"]),
               texto(L.PONTE["titulo"], L.PONTE["x"] + 16, L.PONTE["y"] + 15, 14, 600, C["texto"]),
               caixa(L.CONCLUSAO["x"], L.CONCLUSAO["y"], L.CONCLUSAO["w"], L.CONCLUSAO["h"]),
               texto(L.CONCLUSAO["titulo"], L.CONCLUSAO["x"] + 16, L.CONCLUSAO["y"] + 15, 14, 600, C["texto"])]
    return ('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0}'
            f'body{{width:1280px;height:720px;background:{C["pagina"]};position:relative;'
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
