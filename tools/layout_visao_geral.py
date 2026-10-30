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
DADOS_ATE = {"x": 1060, "y": 78, "rotulo": "Dados até"}

# cartões
CARTAO_Y, CARTAO_W, CARTAO_H, CARTAO_GAP = 118, 235, 100, 12
CARTOES = ["Preço no posto", "Variação em 4 semanas", "Variação em 12 meses", "Impostos no litro", None]  # o último muda com o combustível
BARRA_Y, BARRA_H = 72, 8          # barra do etanol (relativo ao cartão)
BARRA_X, BARRA_W = 16, 203
SUFIXO_LITRO_X = 128              # "/litro" depois de "R$ 0,00" (largura fixa: um dígito antes da vírgula)


def cartao_x(i: int) -> int:
    return 28 + i * (CARTAO_W + CARTAO_GAP)


# área empilhada: as partes do preço semana a semana (somadas dão o preço no posto)
GRAFICO = {"x": 28, "y": 230, "w": 1224, "h": 234, "titulo": "Do que é feito o preço do litro · últimas 52 semanas · R$"}

# faixa de baixo: o que mudou em cada parte do litro e o ranking dos estados
PONTE = {"x": 28, "y": 476, "w": 606, "h": 220, "titulo": "O que mudou em 12 meses · R$/litro"}
RANKING = {"x": 646, "y": 476, "w": 606, "h": 220, "titulo": "Preço no posto por região · R$/litro"}
