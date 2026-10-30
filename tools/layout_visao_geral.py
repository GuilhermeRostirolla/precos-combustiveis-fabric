"""Posições da página "Visão geral" (1280 x 720), usadas pela imagem de fundo e pelo relatório.

Segue o desenho do Figma (arquivo "Preços de Combustíveis · Relatório"). A imagem de fundo
(tools/gerar_fundo.py) desenha o que não muda: molduras, títulos, rótulos e trilhos das barras. O relatório
(tools/gerar_relatorio.py) coloca os visuais do Power BI nas mesmas posições, sem fundo próprio.
"""

COR = {"pagina": "#090E1A", "cartao": "#111A2B", "borda": "#1F2A40", "texto": "#E6EAF2", "suave": "#8B95A9",
       "nota": "#6B7590", "apagado": "#4A5570", "trilho": "#1F2A40", "grade": "#1A2438",
       "alta": "#E8833A", "baixa": "#3BA3D9", "etanol": "#4CC38A", "posto": "#E8833A", "refinaria": "#3BA3D9"}

TITULO = "Preço dos combustíveis"

# filtros
COMBUSTIVEL = {"x": 28, "y": 72, "w": 230, "h": 30, "rotulo": "Combustível", "rotulo_w": 88}
ESTADO = {"x": 268, "y": 72, "w": 150, "h": 30, "rotulo": "Estado", "rotulo_w": 54}
SEMANA = {"x": 428, "y": 72, "w": 176, "h": 30, "rotulo": "Semana", "rotulo_w": 62}

# cartões
CARTAO_Y, CARTAO_W, CARTAO_H, CARTAO_GAP = 118, 235, 100, 12
CARTOES = ["Preço no posto", "Variação em 12 meses", "Posto − refinaria",
           "Refinaria · 4 semanas", "Etanol ÷ gasolina"]
BARRA_Y, BARRA_H = 76, 8          # trilho das barras de progresso (relativo ao cartão)
BARRA_X, BARRA_W = 16, 203
SUFIXO_LITRO_X = 128              # "/litro" depois de "R$ 0,00" (largura fixa: um dígito antes da vírgula)


def cartao_x(i: int) -> int:
    return 28 + i * (CARTAO_W + CARTAO_GAP)


# gráfico
GRAFICO = {"x": 28, "y": 230, "w": 1224, "h": 234, "titulo": "Variação mensal · R$/litro"}

# variação de cada parte do litro em 12 meses
PONTE = {"x": 28, "y": 476, "w": 1224, "h": 220, "titulo": "Variação em 12 meses por parte do preço · R$/litro"}
