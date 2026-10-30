"""Gera a imagem de fundo da página "Visão geral" (tools/recursos/fundo_visao_geral.png).

Desenha em HTML as molduras do desenho (os textos fixos são caixas de texto do relatório, na fonte dos visuais) e tira um print com o Chromium do
Playwright, em resolução dobrada para ficar nítido no Power BI.

    python tools/gerar_fundo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_visao_geral as L  # noqa: E402

DESTINO = Path(__file__).resolve().parent / "recursos" / "fundo_visao_geral.png"
C = {**L.COR, "caixa": "#0D1424"}


def caixa(x, y, w, h, fundo=C["cartao"], borda=True, raio=10):
    b = f"border:1px solid {C['borda']};" if borda else ""
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background:{fundo};{b}border-radius:{raio}px;box-sizing:border-box"></div>')


def texto(t, x, y, tamanho, peso, cor):
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;white-space:nowrap;font-size:{tamanho}px;'
            f'font-weight:{peso};color:{cor};line-height:1.2">{t}</div>')


def html() -> str:
    partes = []
    for f in (L.COMBUSTIVEL, L.ESTADO):
        partes.append(caixa(f["x"], f["y"], f["w"], f["h"], raio=8))
    for i in range(len(L.CARTOES)):
        x, y = L.cartao_x(i), L.CARTAO_Y
        partes.append(caixa(x, y, L.CARTAO_W, L.CARTAO_H))
    for q in (L.GRAFICO, L.PONTE, L.RANKING):
        partes.append(caixa(q["x"], q["y"], q["w"], q["h"]))
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
