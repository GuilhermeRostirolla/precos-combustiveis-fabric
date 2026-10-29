"""Medidas da página "Visão geral": preço no posto do Brasil ou de um estado e por que ele mudou.

O estado vem do filtro de dim_uf (sem escolha = Brasil, uf "BR") e a semana vem de semana_referencia (sem escolha =
a mais recente). As medidas olham para trás a partir dessa semana, por isso ignoram os filtros de dim_semana e dim_uf
e filtram a composição diretamente.
"""

C = "composicao_preco_semana"
UF = 'VAR u = SELECTEDVALUE ( dim_uf[uf], "BR" )'
REAIS = '"R$" #,0.00'
VARIACAO_REAIS = '+"R$" 0.00;-"R$" 0.00;"R$" 0.00'
PCT_SINAL = "+0.0%;-0.0%"
CORES = {"alta": "#E8833A", "baixa": "#3BA3D9", "neutra": "#8B95A9", "refinaria": "#3BA3D9", "impostos": "#8A7CF0",
         "outros": "#E8833A", "etanol": "#4CC38A"}
IMPOSTOS = f"AVERAGE ( {C}[tributos_federais] ) + AVERAGE ( {C}[icms] )"
LITRO_A = f"AVERAGEX ( {C}, {C}[refinaria] / {C}[fracao_fossil] )"


def seta(d: str) -> str:
    """Texto "▲ R$ 0,30" / "▼ R$ 0,04" / "= R$ 0,00" para uma variação em reais."""
    return (f'IF ( {d} > 0.005, "▲ ", IF ( {d} < -0.005, "▼ ", "= " ) ) & "R$ " & FORMAT ( ABS ( {d} ), "0.00" )')


def com_sinal(d: str) -> str:
    """Texto "+R$ 0,34" / "-R$ 0,04" para uma variação em reais."""
    return f'IF ( {d} < 0, "-", "+" ) & "R$ " & FORMAT ( ABS ( {d} ), "0.00" )'


def na_semana(expr: str, dias: int = 0) -> str:
    return (f"{UF}\nVAR s = [Semana de Referência] - {dias}\nRETURN\n    CALCULATE (\n        {expr},\n"
            f"        REMOVEFILTERS ( dim_semana ),\n        REMOVEFILTERS ( dim_uf ),\n"
            f"        {C}[uf] = u,\n        {C}[semana] = s\n    )")


def variacao(atual: str, antes: str) -> str:
    return f"VAR a = {atual}\nVAR b = {antes}\nRETURN\n    IF ( NOT ISBLANK ( a ) && NOT ISBLANK ( b ), a / b - 1 )"


def no_grafico(expr: str) -> str:
    """Valor do mês no eixo do gráfico, só para os 12 meses que terminam na semana de referência."""
    return (f"{UF}\nVAR ref = [Semana de Referência]\nVAR inicio = DATE ( YEAR ( ref ), MONTH ( ref ) - 11, 1 )\n"
            f"VAR m = MAX ( dim_semana[mes_inicio] )\nRETURN\n    IF (\n        m >= inicio && m <= ref,\n"
            f"        CALCULATE ( {expr}, REMOVEFILTERS ( dim_uf ), {C}[uf] = u, {C}[semana] <= ref )\n    )")


def no_mes(expr: str, anterior: bool = False) -> str:
    """Média das semanas do mês explicado (ou do mês anterior a ele)."""
    mes = "EDATE ( [Mês Explicado], -1 )" if anterior else "[Mês Explicado]"
    return (f"{UF}\nVAR ref = [Semana de Referência]\nVAR m = {mes}\nRETURN\n    CALCULATE (\n        {expr},\n"
            f"        REMOVEFILTERS ( dim_semana ),\n        REMOVEFILTERS ( dim_uf ),\n        {C}[uf] = u,\n"
            f"        {C}[semana] >= m,\n        {C}[semana] <= EOMONTH ( m, 0 ),\n        {C}[semana] <= ref\n    )")


def preco_uf(produto: str) -> str:
    """Preço médio de um produto no estado escolhido (ou no Brasil), na semana de referência."""
    return (f"{UF}\nVAR s = [Semana de Referência]\nRETURN\n    CALCULATE (\n"
            "        DIVIDE (\n            SUMX ( fato_preco_uf_semana, fato_preco_uf_semana[preco_medio] "
            "* fato_preco_uf_semana[coletas] ),\n            SUM ( fato_preco_uf_semana[coletas] )\n        ),\n"
            "        REMOVEFILTERS ( dim_semana ),\n        REMOVEFILTERS ( dim_uf ),\n"
            f'        dim_produto[produto] = "{produto}",\n        fato_preco_uf_semana[semana] = s,\n'
            '        FILTER ( ALL ( fato_preco_uf_semana[uf] ), u = "BR" || fato_preco_uf_semana[uf] = u )\n    )')


def delta(componente: str, expr: str) -> list[tuple]:
    return [
        (f"{componente} Mês Explicado", "Por que mudou", REAIS, no_mes(expr)),
        (f"{componente} Mês Anterior", "Por que mudou", REAIS, no_mes(expr, anterior=True)),
        (f"Δ {componente}", "Por que mudou", VARIACAO_REAIS,
         f"VAR a = [{componente} Mês Explicado]\nVAR b = [{componente} Mês Anterior]\nRETURN\n"
         "    IF ( NOT ISBLANK ( a ) && NOT ISBLANK ( b ), a - b )"),
    ]


def medidas_visao_geral() -> dict[str, list[tuple]]:
    composicao = [
        ("Semana de Referência", "Visão geral", "dd/MM/yyyy",
         "VAR s = SELECTEDVALUE ( semana_referencia[semana] )\nRETURN\n"
         f"    IF ( ISBLANK ( s ), CALCULATE ( MAX ( {C}[semana] ), REMOVEFILTERS () ), s )"),
        ("Texto Semana de Referência", "Visão geral", None,
         '"Dados até a semana de " & FORMAT ( [Semana de Referência], "dd/MM/yyyy" ) & " · Fonte: ANP"'),
        ("Preço no Posto", "Visão geral", REAIS, na_semana(f"AVERAGE ( {C}[preco_posto] )")),
        ("Preço no Posto Semana Anterior", "Visão geral", REAIS, na_semana(f"AVERAGE ( {C}[preco_posto] )", 7)),
        ("Preço no Posto 4 Semanas Antes", "Visão geral", REAIS, na_semana(f"AVERAGE ( {C}[preco_posto] )", 28)),
        ("Preço no Posto 12 Meses Antes", "Visão geral", REAIS, na_semana(f"AVERAGE ( {C}[preco_posto] )", 364)),
        ("Refinaria por Litro", "Visão geral", REAIS,
         "// produtores e importadores, sem tributos, por litro de gasolina A ou diesel A\n" + na_semana(LITRO_A)),
        ("Refinaria 4 Semanas Antes", "Visão geral", REAIS, na_semana(LITRO_A, 28)),
        ("Refinaria 12 Meses Antes", "Visão geral", REAIS, na_semana(LITRO_A, 364)),
        ("Impostos no Litro", "Visão geral", REAIS, na_semana(IMPOSTOS)),
        ("ICMS no Litro", "Visão geral", REAIS, na_semana(f"AVERAGE ( {C}[icms] )")),
        ("Variação 12 Meses Posto", "Visão geral", PCT_SINAL,
         variacao("[Preço no Posto]", "[Preço no Posto 12 Meses Antes]")),
        ("Variação 12 Meses Refinaria", "Visão geral", PCT_SINAL,
         variacao("[Refinaria por Litro]", "[Refinaria 12 Meses Antes]")),
        ("Variação Refinaria 4 Semanas", "Visão geral", PCT_SINAL,
         variacao("[Refinaria por Litro]", "[Refinaria 4 Semanas Antes]")),
        ("Preço Etanol", "Visão geral", REAIS, preco_uf("ETANOL")),
        ("Preço Gasolina", "Visão geral", REAIS, preco_uf("GASOLINA")),
        ("Etanol ÷ Gasolina", "Visão geral", "0%", "DIVIDE ( [Preço Etanol], [Preço Gasolina] )"),
        ("Apoio Preço no Posto", "Visão geral", None,
         "VAR d = [Preço no Posto] - [Preço no Posto Semana Anterior]\nRETURN\n"
         f"    IF ( NOT ISBLANK ( [Preço no Posto Semana Anterior] ), {seta('d')} & \" vs semana anterior\", \"\" )"),
        ("Apoio Variação 12 Meses", "Visão geral", None,
         'IF ( ISBLANK ( [Variação 12 Meses Refinaria] ), "", '
         '"Refinaria no mesmo período: " & FORMAT ( [Variação 12 Meses Refinaria], "+0.0%;-0.0%" ) )'),
        ("Apoio Impostos", "Visão geral", None,
         'FORMAT ( DIVIDE ( [Impostos no Litro], [Preço no Posto] ), "0%" ) & " do preço · ICMS R$ " '
         '& FORMAT ( [ICMS no Litro], "0.00" )'),
        ("Apoio Refinaria 4 Semanas", "Visão geral", None,
         "VAR d = [Preço no Posto] - [Preço no Posto 4 Semanas Antes]\nRETURN\n"
         f'    IF ( ISBLANK ( [Preço no Posto 4 Semanas Antes] ), "", "No posto: " & {seta("d")} & " no mesmo período" )'),
        ("Apoio Etanol", "Visão geral", None,
         'IF ( [Etanol ÷ Gasolina] < 0.7, "Abaixo de 70%: etanol compensa", "Acima de 70%: gasolina compensa" )'),
        ("Cor Variação 12 Meses", "Cores", None,
         f'IF ( [Variação 12 Meses Posto] >= 0, "{CORES["alta"]}", "{CORES["baixa"]}" )'),
        ("Cor Refinaria 4 Semanas", "Cores", None,
         f'IF ( [Variação Refinaria 4 Semanas] >= 0, "{CORES["alta"]}", "{CORES["baixa"]}" )'),
        ("Cor Etanol", "Cores", None, f'IF ( [Etanol ÷ Gasolina] < 0.7, "{CORES["etanol"]}", "{CORES["alta"]}" )'),
        # gráfico: do que é feito o preço, mês a mês
        ("Refinaria no Mês", "Gráfico", REAIS, no_grafico(f"AVERAGE ( {C}[refinaria] )")),
        ("Impostos no Mês", "Gráfico", REAIS, no_grafico(IMPOSTOS)),
        ("Outros no Mês", "Gráfico", REAIS, no_grafico(f"AVERAGE ( {C}[outros] )")),
        ("Posto no Mês", "Gráfico", REAIS, no_grafico(f"AVERAGE ( {C}[preco_posto] )")),
        # por que mudou
        ("Mês Explicado", "Por que mudou", "mmmm yyyy",
         "// o mês clicado no gráfico; sem clique, o mês da semana de referência\nVAR ref = [Semana de Referência]\n"
         "RETURN\n    IF ( ISFILTERED ( dim_semana ), MAX ( dim_semana[mes_inicio] ), "
         "DATE ( YEAR ( ref ), MONTH ( ref ), 1 ) )"),
        *delta("Posto", f"AVERAGE ( {C}[preco_posto] )"),
        *delta("Refinaria", f"AVERAGE ( {C}[refinaria] )"),
        *delta("Impostos", IMPOSTOS),
        *delta("Outros", f"AVERAGE ( {C}[outros] )"),
        ("Título Por Que Mudou", "Por que mudou", None,
         'VAR m = [Mês Explicado]\nRETURN\n    "Por que o preço mudou em " & FORMAT ( m, "mmmm" ) & " de " & YEAR ( m ) & "?"'),
        ("Texto Δ Posto", "Por que mudou", None, f"VAR d = [Δ Posto]\nRETURN\n    IF ( NOT ISBLANK ( d ), {seta('d')}, \"sem mês anterior\" )"),
        ("Cor Δ Posto", "Cores", None,
         f'VAR d = [Δ Posto]\nRETURN\n    IF ( d > 0.005, "{CORES["alta"]}", IF ( d < -0.005, "{CORES["baixa"]}", '
         f'"{CORES["neutra"]}" ) )'),
        ("Texto De Para", "Por que mudou", None,
         'IF (\n    NOT ISBLANK ( [Δ Posto] ),\n    "Média do mês: de R$ " & FORMAT ( [Posto Mês Anterior], "0.00" ) '
         '& " para R$ " & FORMAT ( [Posto Mês Explicado], "0.00" ) & " por litro",\n    ""\n)'),
        ("Conclusão", "Por que mudou", None,
         "VAR d = [Δ Posto]\nVAR s = IF ( d < 0, -1, 1 )\nVAR r = [Δ Refinaria] * s\nVAR i = [Δ Impostos] * s\n"
         "VAR o = [Δ Outros] * s\nVAR maior =\n    SWITCH (\n        TRUE (),\n        r >= i && r >= o, \"da refinaria\",\n"
         "        i >= o, \"dos impostos\",\n        \"do etanol/biodiesel, do frete e das margens\"\n    )\nRETURN\n"
         "    SWITCH (\n        TRUE (),\n        ISBLANK ( d ), \"\",\n"
         "        ABS ( d ) < 0.02, \"O preço no posto ficou praticamente estável.\",\n"
         "        IF ( d > 0, \"A alta\", \"A queda\" ) & \" veio principalmente \" & maior & \".\"\n    )"),
        ("Conclusão Detalhe", "Por que mudou", None,
         'VAR p = SELECTEDVALUE ( dim_produto[produto], "GASOLINA" )\nVAR m = [Mês Explicado]\nVAR eventos =\n'
         "    CONCATENATEX (\n        FILTER (\n            evento,\n"
         "            evento[data] >= m && evento[data] <= EOMONTH ( m, 0 )\n"
         '                && ( evento[produto] = p || evento[produto] = "TODOS" )\n        ),\n'
         '        evento[descricao],\n        ". ",\n        evento[data], ASC\n    )\n'
         f"VAR partes =\n    \"Refinaria \" & {com_sinal('[Δ Refinaria]')} & \", impostos \" & {com_sinal('[Δ Impostos]')}\n"
         f"        & \" e etanol/biodiesel, frete e margens \" & {com_sinal('[Δ Outros]')} & \" por litro.\"\n"
         "RETURN\n    IF (\n        ISBLANK ( [Δ Posto] ),\n        \"\",\n"
         '        IF ( eventos <> "", eventos & ". " & partes, partes )\n    )'),
    ]
    componente = [
        ("Variação do Componente", "Por que mudou", VARIACAO_REAIS,
         "SWITCH (\n    SELECTEDVALUE ( componente[componente] ),\n    \"Refinaria\", [Δ Refinaria],\n"
         "    \"Impostos\", [Δ Impostos],\n    [Δ Outros]\n)"),
        ("Cor do Componente", "Cores", None,
         f"SWITCH (\n    SELECTEDVALUE ( componente[componente] ),\n    \"Refinaria\", \"{CORES['refinaria']}\",\n"
         f"    \"Impostos\", \"{CORES['impostos']}\",\n    \"{CORES['outros']}\"\n)"),
    ]
    return {C: composicao, "componente": componente}
