"""Posições da página "Visão geral" (1280 x 720), usadas pela imagem de fundo e pelo relatório.

A imagem de fundo (tools/gerar_fundo.py) desenha o que não muda: molduras, títulos e rótulos.
O relatório (tools/gerar_relatorio.py) coloca os visuais do Power BI nas mesmas posições, sem fundo próprio.
"""

COR = {"pagina": "#090E1A", "cartao": "#111A2B", "borda": "#1F2A40", "texto": "#E6EAF2", "suave": "#8B95A9",
       "apagado": "#4A5570", "caixa": "#0D1424", "refinaria": "#3BA3D9", "impostos": "#8A7CF0", "outros": "#E8833A",
       "alta": "#E8833A", "baixa": "#3BA3D9"}

MARGEM = 28
LARGURA_UTIL = 1280 - 2 * MARGEM

TITULO = {"texto": "Preço dos combustíveis", "x": MARGEM, "y": 20}
SUBTITULO = {"texto": "Quanto custa hoje, quanto mudou e por quê", "x": MARGEM, "y": 56}

# filtros: moldura com o rótulo à esquerda; a lista do Power BI fica à direita do rótulo
FILTROS = [
    {"rotulo": "Combustível", "x": MARGEM, "y": 88, "w": 230, "h": 36, "rotulo_w": 86},
    {"rotulo": "Estado", "x": MARGEM + 240, "y": 88, "w": 170, "h": 36, "rotulo_w": 56},
    {"rotulo": "Semana", "x": MARGEM + 420, "y": 88, "w": 200, "h": 36, "rotulo_w": 62},
]
NOTA = {"x": 700, "y": 96, "w": 552, "h": 22}

CARTOES_Y, CARTOES_H, CARTOES_GAP = 140, 92, 12
CARTOES = ["Preço médio no posto", "Refinaria no litro (sem impostos)", "Diferença posto − refinaria",
           "Postos pesquisados na semana"]
CARTAO_W = (LARGURA_UTIL - CARTOES_GAP * (len(CARTOES) - 1)) / len(CARTOES)


def cartao_x(i: int) -> float:
    return MARGEM + i * (CARTAO_W + CARTOES_GAP)


MEIO_Y, MEIO_H = 248, 448
PAINEL_W = 388
GRAFICO = {"x": MARGEM, "y": MEIO_Y, "w": LARGURA_UTIL - PAINEL_W - 12, "h": MEIO_H,
           "titulo": "Do que é feito o preço, mês a mês",
           "subtitulo": "R$ por litro no posto · clique num mês para ver por que o preço mudou"}
PAINEL = {"x": MARGEM + GRAFICO["w"] + 12, "y": MEIO_Y, "w": PAINEL_W, "h": MEIO_H,
          "rotulo": "Preço no posto · média do mês contra o mês anterior"}
CONCLUSAO = {"x": PAINEL["x"] + 16, "y": 560, "w": PAINEL_W - 32, "h": 122}
