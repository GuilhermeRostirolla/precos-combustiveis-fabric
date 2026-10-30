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
# alta/baixa: subiu (vermelho) ou caiu (verde); as partes do preço têm cores próprias
CORES = {"alta": "#E5534B", "baixa": "#3FB950", "neutra": "#8B95A9", "refinaria": "#3BA3D9", "impostos": "#8A7CF0",
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


def na_linha(expr: str) -> str:
    """Valor da semana no eixo do gráfico, só nas 52 semanas que terminam na semana de referência."""
    return (f"{UF}\nVAR ref = [Semana de Referência]\nVAR s = MAX ( dim_semana[semana] )\nRETURN\n"
            f"    IF ( s > ref - 364 && s <= ref, CALCULATE ( {expr}, REMOVEFILTERS ( dim_uf ), {C}[uf] = u ) )")


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
            "        REMOVEFILTERS ( dim_semana ),\n        REMOVEFILTERS ( dim_uf ),\n        REMOVEFILTERS ( dim_produto ),\n"
            f'        dim_produto[produto] = "{produto}",\n        fato_preco_uf_semana[semana] = s,\n'
            '        FILTER ( ALL ( fato_preco_uf_semana[uf] ), u = "BR" || fato_preco_uf_semana[uf] = u )\n    )')


def postos(coluna: str) -> str:
    """Postos ou municípios pesquisados na semana de referência, no estado escolhido (ou no Brasil)."""
    return (f"{UF}\nVAR s = [Semana de Referência]\nRETURN\n    CALCULATE (\n"
            f"        SUM ( fato_preco_uf_semana[{coluna}] ),\n"
            "        REMOVEFILTERS ( dim_semana ),\n        REMOVEFILTERS ( dim_uf ),\n"
            "        fato_preco_uf_semana[semana] = s,\n"
            '        FILTER ( ALL ( fato_preco_uf_semana[uf] ), u = "BR" || fato_preco_uf_semana[uf] = u )\n    )')


def variacao_mensal(expr: str, em_reais: bool = False) -> str:
    """Variação da média do mês no eixo contra a do mês anterior, só nos 12 meses até a semana de referência."""
    return (f"{UF}\nVAR ref = [Semana de Referência]\nVAR inicio = DATE ( YEAR ( ref ), MONTH ( ref ) - 11, 1 )\n"
            "VAR m = MAX ( dim_semana[mes_inicio] )\n"
            f"VAR atual = CALCULATE ( {expr}, REMOVEFILTERS ( dim_semana ), REMOVEFILTERS ( dim_uf ), {C}[uf] = u,\n"
            f"    {C}[semana] >= m, {C}[semana] <= EOMONTH ( m, 0 ), {C}[semana] <= ref )\n"
            f"VAR antes = CALCULATE ( {expr}, REMOVEFILTERS ( dim_semana ), REMOVEFILTERS ( dim_uf ), {C}[uf] = u,\n"
            f"    {C}[semana] >= EDATE ( m, -1 ), {C}[semana] < m )\n"
            "RETURN\n    IF ( m >= inicio && m <= ref && NOT ISBLANK ( atual ) && NOT ISBLANK ( antes ), "
            + ("ROUND ( atual - antes, 2 ) )" if em_reais else "atual / antes - 1 )"))


def delta(componente: str, expr: str) -> list[tuple]:
    return [
        (f"{componente} Mês Explicado", "Por que mudou", REAIS, no_mes(expr)),
        (f"{componente} Mês Anterior", "Por que mudou", REAIS, no_mes(expr, anterior=True)),
        (f"Δ {componente}", "Por que mudou", VARIACAO_REAIS,
         f"VAR a = [{componente} Mês Explicado]\nVAR b = [{componente} Mês Anterior]\nRETURN\n"
         "    IF ( NOT ISBLANK ( a ) && NOT ISBLANK ( b ), ROUND ( a - b, 2 ) )"),
    ]


PARTES = [("Posto", f"AVERAGE ( {C}[preco_posto] )"), ("Refinaria", f"AVERAGE ( {C}[refinaria] )"),
          ("Impostos", IMPOSTOS), ("Outros", f"AVERAGE ( {C}[outros] )")]


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
        # quatro indicadores do topo
        ("Refinaria no Litro do Posto", "Visão geral", REAIS,
         "// parte da refinaria em um litro vendido no posto (só a parcela fóssil, sem tributos)\n"
         + na_semana(f"AVERAGE ( {C}[refinaria] )")),
        ("Refinaria no Litro 4 Semanas Antes", "Visão geral", REAIS, na_semana(f"AVERAGE ( {C}[refinaria] )", 28)),
        ("Diferença Posto Refinaria", "Visão geral", REAIS,
         "// tudo o que vem depois da refinaria: impostos, etanol ou biodiesel, frete e margens\n"
         "VAR p = [Preço no Posto]\nVAR r = [Refinaria no Litro do Posto]\nRETURN\n"
         "    IF ( NOT ISBLANK ( p ) && NOT ISBLANK ( r ), p - r )"),
        ("Diferença Média 12 Meses", "Visão geral", REAIS,
         f"{UF}\nVAR s = [Semana de Referência]\nRETURN\n    CALCULATE (\n"
         f"        AVERAGEX ( {C}, {C}[preco_posto] - {C}[refinaria] ),\n"
         "        REMOVEFILTERS ( dim_semana ),\n        REMOVEFILTERS ( dim_uf ),\n"
         f"        {C}[uf] = u,\n        {C}[semana] > s - 364,\n        {C}[semana] <= s\n    )"),
        ("Postos Pesquisados", "Visão geral", "#,0", postos("postos")),
        ("Municípios Pesquisados", "Visão geral", "#,0", postos("municipios")),
        ("Apoio Refinaria", "Visão geral", None,
         "VAR d = [Refinaria no Litro do Posto] - [Refinaria no Litro 4 Semanas Antes]\nRETURN\n"
         f'    IF ( ISBLANK ( [Refinaria no Litro 4 Semanas Antes] ), "", {seta("d")} & " vs 4 semanas atrás" )'),
        ("Apoio Diferença", "Visão geral", None,
         'IF ( ISBLANK ( [Diferença Média 12 Meses] ), "", "Média de 12 meses: R$ " '
         '& FORMAT ( [Diferença Média 12 Meses], "0.00" ) )'),
        ("Apoio Postos", "Visão geral", None,
         '"em " & FORMAT ( [Municípios Pesquisados], "#,0" ) & " municípios"'),
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
        ("Cor Etanol", "Cores", None, f'IF ( [Etanol ÷ Gasolina] < 0.7, "{CORES["etanol"]}", "{CORES["outros"]}" )'),
        # desenho "o que aconteceu com o preço"
        ("Texto Dados Até a Semana", "Visão geral", None,
         '"Dados até a semana de " & FORMAT ( [Semana de Referência], "dd/MM/yyyy" )'),
        ("Texto Postos e Fonte", "Visão geral", None,
         'FORMAT ( [Postos Pesquisados], "#,0" ) & " postos pesquisados em " & FORMAT ( [Municípios Pesquisados], "#,0" ) '
         '& " municípios · Fonte: ANP"'),
        ("Cor Variação 12 Meses Refinaria", "Cores", None,
         f'IF ( [Variação 12 Meses Refinaria] >= 0, "{CORES["alta"]}", "{CORES["baixa"]}" )'),
        ("Cor Apoio Preço no Posto", "Cores", None,
         "VAR d = [Preço no Posto] - [Preço no Posto Semana Anterior]\nRETURN\n"
         f'    IF ( d > 0.005, "{CORES["alta"]}", IF ( d < -0.005, "{CORES["baixa"]}", "{CORES["neutra"]}" ) )'),
        ("Posto x Refinaria 12 Meses", "Visão geral", None,
         "VAR p = [Variação 12 Meses Posto]\nVAR r = [Variação 12 Meses Refinaria]\nRETURN\n"
         "    SWITCH (\n        TRUE (),\n        ISBLANK ( p ) || ISBLANK ( r ), \"\",\n"
         "        p >= 0 && r < 0, \"Posto subiu enquanto a refinaria caiu\",\n"
         "        p < 0 && r >= 0, \"Posto caiu enquanto a refinaria subiu\",\n"
         "        p >= 0, IF ( p > r, \"Posto subiu mais que a refinaria\", \"Posto subiu menos que a refinaria\" ),\n"
         "        IF ( p < r, \"Posto caiu mais que a refinaria\", \"Posto caiu menos que a refinaria\" )\n    )"),
        ("Apoio Diferença Refinaria", "Visão geral", None,
         'IF ( ISBLANK ( [Refinaria no Litro do Posto] ), "", "Refinaria: R$ " '
         '& FORMAT ( [Refinaria no Litro do Posto], "0.00" ) & " no litro" )'),
        ("Apoio Diferença Média", "Visão geral", None,
         "VAR d = [Diferença Posto Refinaria]\nVAR m = [Diferença Média 12 Meses]\nRETURN\n"
         '    IF ( ISBLANK ( m ), "", IF ( d >= m, "Acima", "Abaixo" ) & " da média de 12 meses (R$ " '
         '& FORMAT ( m, "0.00" ) & ")" )'),
        ("Repasse 4 Semanas", "Visão geral", "0%",
         "// quanto da mudança da refinaria (no litro do posto) apareceu no posto em 4 semanas\n"
         "VAR r = [Refinaria no Litro do Posto] - [Refinaria no Litro 4 Semanas Antes]\n"
         "VAR p = [Preço no Posto] - [Preço no Posto 4 Semanas Antes]\nRETURN\n"
         "    IF ( ABS ( r ) >= 0.02, MAX ( 0, MIN ( 1, DIVIDE ( p, r ) ) ) )"),
        ("Barra Repasse 4 Semanas", "Visão geral", "0%", "COALESCE ( [Repasse 4 Semanas], 0 )"),
        ("Apoio Repasse 4 Semanas", "Visão geral", None,
         'IF ( ISBLANK ( [Repasse 4 Semanas] ), "A refinaria quase não mudou", '
         '"Já chegou ao posto: " & FORMAT ( [Repasse 4 Semanas], "0%" ) )'),
        ("Barra Etanol", "Visão geral", "0%", "MAX ( 0, MIN ( 1, [Etanol ÷ Gasolina] ) )"),
        ("Texto Barra Repasse", "Visão geral", None,
         "// barra de progresso feita de traços (o trilho está na imagem de fundo)\n"
         'REPT ( "█", ROUND ( [Barra Repasse 4 Semanas] * 30, 0 ) )'),
        ("Texto Barra Etanol", "Visão geral", None,
         'IF ( SELECTEDVALUE ( dim_produto[produto] ) = "DIESEL S10", "", '
         'REPT ( "█", ROUND ( COALESCE ( [Barra Etanol], 0 ) * 30, 0 ) ) )'),
        # ponte de preço: o que mudou em cada parte do litro em 12 meses
        *[(f"Ponte {nome} 12 Meses Antes", "Ponte", REAIS, na_semana(expr, 364)) for nome, expr in PARTES],
        *[(f"Ponte {nome} Hoje", "Ponte", REAIS, na_semana(expr)) for nome, expr in PARTES],
        *[(f"Δ12 {nome}", "Ponte", VARIACAO_REAIS,
           f"VAR a = [Ponte {nome} Hoje]\nVAR b = [Ponte {nome} 12 Meses Antes]\nRETURN\n"
           "    IF ( NOT ISBLANK ( a ) && NOT ISBLANK ( b ), ROUND ( a - b, 2 ) )") for nome, _ in PARTES],
        ("Texto Ponte De Para", "Ponte", None,
         "VAR s = [Semana de Referência]\nRETURN\n    IF (\n        ISBLANK ( [Δ12 Posto] ),\n        \"\",\n"
         '        "De R$ " & FORMAT ( [Ponte Posto 12 Meses Antes], "0.00" ) & " para R$ " & FORMAT ( [Ponte Posto Hoje], "0.00" )\n'
         '            & " por litro (" & FORMAT ( s - 364, "dd/MM/yy" ) & " a " & FORMAT ( s, "dd/MM/yy" ) & ")"\n    )'),
        ("Conclusão 12 Meses", "Ponte", None,
         "VAR d = [Δ12 Posto]\nRETURN\n    SWITCH (\n        TRUE (),\n        ISBLANK ( d ), \"\",\n"
         f"        d >= 0.02, \"Subiu R$ \" & FORMAT ( d, \"0.00\" ) & \" por litro em 12 meses.\",\n"
         f"        d <= -0.02, \"Caiu R$ \" & FORMAT ( -d, \"0.00\" ) & \" por litro em 12 meses.\",\n"
         "        \"Ficou praticamente estável em 12 meses.\"\n    )"),
        ("Cor Conclusão 12 Meses", "Cores", None,
         f'VAR d = [Δ12 Posto]\nRETURN\n    IF ( d >= 0.02, "{CORES["alta"]}", IF ( d <= -0.02, "{CORES["baixa"]}", "{CORES["neutra"]}" ) )'),
        ("Detalhe 12 Meses", "Ponte", None,
         "VAR d = [Δ12 Posto]\nVAR r = [Δ12 Refinaria]\nVAR i = [Δ12 Impostos]\nVAR o = [Δ12 Outros]\n"
         "VAR s = IF ( d < 0, -1, 1 )\n"
         "VAR principal =\n    SWITCH (\n        TRUE (),\n        o * s >= r * s && o * s >= i * s, \"de etanol/biodiesel, frete e margens\",\n"
         "        r * s >= i * s, \"da refinaria\",\n        \"dos impostos\"\n    )\n"
         "VAR valor = SWITCH ( principal, \"da refinaria\", r, \"dos impostos\", i, o )\n"
         "VAR refinaria =\n    SWITCH (\n        TRUE (),\n"
         "        r <= -0.01, \"A refinaria baixou R$ \" & FORMAT ( -r, \"0.00\" ),\n"
         "        r >= 0.01, \"A refinaria subiu R$ \" & FORMAT ( r, \"0.00\" ),\n"
         "        \"A refinaria ficou estável\"\n    )\n"
         'VAR p = SELECTEDVALUE ( dim_produto[produto], "GASOLINA" )\nVAR ref = [Semana de Referência]\n'
         "VAR eventos =\n    CONCATENATEX (\n        TOPN ( 2, FILTER ( evento, evento[data] > ref - 364 && evento[data] <= ref\n"
         '            && ( evento[produto] = p || evento[produto] = "TODOS" ) ), evento[data], DESC ),\n'
         '        FORMAT ( evento[data], "mmm/yy" ) & ": " & evento[descricao],\n        " · ",\n        evento[data], DESC\n    )\n'
         "RETURN\n    IF (\n        ISBLANK ( d ),\n        \"\",\n"
         "        refinaria & \". \" & IF ( d >= 0, \"O aumento\", \"A queda\" ) & \" veio principalmente \" & principal\n"
         f"            & \" (\" & {com_sinal('valor')} & \").\" & IF ( eventos <> \"\", \" No período: \" & eventos & \".\" )\n    )"),
        ("Resto Barra Repasse", "Visão geral", "0%", "1 - [Barra Repasse 4 Semanas]"),
        ("Resto Barra Etanol", "Visão geral", "0%", "1 - COALESCE ( [Barra Etanol], 0 )"),
        ("Variação Mensal Posto", "Gráfico", "+0.0%;-0.0%;0.0%", variacao_mensal(f"AVERAGE ( {C}[preco_posto] )")),
        ("Variação Mensal Refinaria", "Gráfico", "+0.0%;-0.0%;0.0%", variacao_mensal(LITRO_A)),
        ("Variação Mensal Posto R$", "Gráfico", VARIACAO_REAIS,
         variacao_mensal(f"AVERAGE ( {C}[preco_posto] )", em_reais=True)),
        ("Variação Mensal Refinaria R$", "Gráfico", VARIACAO_REAIS,
         "// a parte da refinaria dentro do litro vendido no posto, para comparar na mesma régua\n"
         + variacao_mensal(f"AVERAGE ( {C}[refinaria] )", em_reais=True)),
        ("Apoio Diferença Curto", "Visão geral", None,
         'IF ( ISBLANK ( [Diferença Média 12 Meses] ), "", "Refinaria R$ " & FORMAT ( [Refinaria no Litro do Posto], "0.00" ) '
         '& " · média 12 meses R$ " & FORMAT ( [Diferença Média 12 Meses], "0.00" ) )'),
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
        # blocos da conta: preço há 12 meses + refinaria + impostos + outros = preço hoje
        ("Principal Motivo 12 Meses", "Ponte", None,
         "VAR d = [Δ12 Posto]\nVAR s = IF ( d < 0, -1, 1 )\nVAR r = [Δ12 Refinaria] * s\nVAR i = [Δ12 Impostos] * s\n"
         "VAR o = [Δ12 Outros] * s\nRETURN\n    SWITCH ( TRUE (), o >= r && o >= i, \"Outros\", r >= i, \"Refinaria\", "
         "\"Impostos\" )"),
        ("Manchete 12 Meses", "Ponte", None,
         "VAR d = [Δ12 Posto]\nVAR r = [Δ12 Refinaria]\nVAR m = [Principal Motivo 12 Meses]\n"
         "VAR motivo = SWITCH ( m, \"Refinaria\", \"da refinaria\", \"Impostos\", \"dos impostos\", "
         "\"de etanol, frete e margens\" )\n"
         "VAR refinaria =\n    SWITCH ( TRUE (), r <= -0.01, \"A refinaria baixou R$ \" & FORMAT ( -r, \"0.00\" ),\n"
         "        r >= 0.01, \"A refinaria subiu R$ \" & FORMAT ( r, \"0.00\" ), \"A refinaria ficou estável\" )\n"
         "RETURN\n    IF (\n        ISBLANK ( d ),\n        \"\",\n        [Conclusão 12 Meses] & \" \" & refinaria & \"; \"\n"
         "            & IF ( d >= 0, \"o aumento\", \"a queda\" ) & \" veio principalmente \" & motivo & \".\"\n    )"),
        ("Texto Preço 12 Meses Antes", "Ponte", None,
         'IF ( ISBLANK ( [Ponte Posto 12 Meses Antes] ), "", "R$ " & FORMAT ( [Ponte Posto 12 Meses Antes], "0.00" ) )'),
        ("Texto Preço Hoje", "Ponte", None,
         'IF ( ISBLANK ( [Ponte Posto Hoje] ), "", "R$ " & FORMAT ( [Ponte Posto Hoje], "0.00" ) )'),
        ("Data 12 Meses Antes", "Ponte", None, '"semana de " & FORMAT ( [Semana de Referência] - 364, "dd/MM/yy" )'),
        ("Data Hoje", "Ponte", None, '"semana de " & FORMAT ( [Semana de Referência], "dd/MM/yy" )'),
        *[x for parte in ("Refinaria", "Impostos", "Outros") for x in (
            (f"Texto Δ12 {parte}", "Ponte", None,
             f"VAR d = [Δ12 {parte}]\nRETURN\n    IF ( ISBLANK ( d ), \"\", {com_sinal('d')} )"),
            (f"Cor Δ12 {parte}", "Cores", None,
             f'VAR d = [Δ12 {parte}]\nRETURN\n    IF ( d >= 0.01, "{CORES["alta"]}", IF ( d <= -0.01, "{CORES["baixa"]}", '
             f'"{CORES["neutra"]}" ) )'),
            (f"Legenda Δ12 {parte}", "Ponte", None,
             f"VAR d = [Δ12 {parte}]\nRETURN\n    SWITCH (\n        TRUE (),\n        ISBLANK ( d ), \"\",\n"
             f"        [Principal Motivo 12 Meses] = \"{parte}\" && ABS ( [Δ12 Posto] ) >= 0.02, \"▲ principal motivo\",\n"
             "        d >= 0.01, \"subiu\",\n        d <= -0.01, \"caiu\",\n        \"ficou estável\"\n    )"),
        )],
        ("Cor Variação 12 Meses do Componente", "Cores", None,
         f'VAR d = [Variação 12 Meses do Componente]\nRETURN\n    IF ( d >= 0, "{CORES["alta"]}", "{CORES["baixa"]}" )'),
        ("Componente Há 12 Meses", "Ponte", REAIS,
         "SWITCH (\n    SELECTEDVALUE ( componente[componente] ),\n    \"Refinaria\", [Ponte Refinaria 12 Meses Antes],\n"
         "    \"Impostos\", [Ponte Impostos 12 Meses Antes],\n    [Ponte Outros 12 Meses Antes]\n)"),
        ("Componente Hoje", "Ponte", REAIS,
         "SWITCH (\n    SELECTEDVALUE ( componente[componente] ),\n    \"Refinaria\", [Ponte Refinaria Hoje],\n"
         "    \"Impostos\", [Ponte Impostos Hoje],\n    [Ponte Outros Hoje]\n)"),
        ("Variação 12 Meses do Componente", "Ponte", VARIACAO_REAIS,
         "SWITCH (\n    SELECTEDVALUE ( componente[componente] ),\n    \"Refinaria\", [Δ12 Refinaria],\n"
         "    \"Impostos\", [Δ12 Impostos],\n    \"Etanol/biodiesel, frete e margens\", [Δ12 Outros],\n"
         "    \"Preço no posto\", [Δ12 Posto]\n)"),
        ("Variação do Componente", "Por que mudou", VARIACAO_REAIS,
         "SWITCH (\n    SELECTEDVALUE ( componente[componente] ),\n    \"Refinaria\", [Δ Refinaria],\n"
         "    \"Impostos\", [Δ Impostos],\n    [Δ Outros]\n)"),
        ("Cor do Componente", "Cores", None,
         f"SWITCH (\n    SELECTEDVALUE ( componente[componente] ),\n    \"Refinaria\", \"{CORES['refinaria']}\",\n"
         f"    \"Impostos\", \"{CORES['impostos']}\",\n    \"Preço no posto\", \"#E6EAF2\",\n    \"{CORES['outros']}\"\n)"),
        ("Variação Semana Posto", "Visão geral", VARIACAO_REAIS,
         "VAR a = [Preço no Posto]\nVAR b = [Preço no Posto Semana Anterior]\nRETURN\n"
         "    IF ( NOT ISBLANK ( a ) && NOT ISBLANK ( b ), ROUND ( a - b, 2 ) )"),
        ("Variação Semana Posto %", "Visão geral", PCT_SINAL,
         variacao("[Preço no Posto]", "[Preço no Posto Semana Anterior]")),
        ("Cor Variação Semana", "Cores", None,
         f'VAR d = [Variação Semana Posto]\nRETURN\n    IF ( d > 0, "{CORES["alta"]}", IF ( d < 0, "{CORES["baixa"]}", "{CORES["neutra"]}" ) )'),
        ("Impostos % do Preço", "Visão geral", '0% "do preço"', "DIVIDE ( [Impostos no Litro], [Preço no Posto] )"),
        ("Refinaria na Semana", "Gráfico", REAIS, na_linha(f"AVERAGE ( {C}[refinaria] )")),
        ("Impostos na Semana", "Gráfico", REAIS, na_linha(IMPOSTOS)),
        ("Outros na Semana", "Gráfico", REAIS, na_linha(f"AVERAGE ( {C}[outros] )")),
        ("Preço por Região", "Gráfico", '#,0.00',
         "// média dos postos pesquisados nos estados da região (ou do Brasil), na semana de referência\n"
         "VAR r = SELECTEDVALUE ( regiao_comparacao[regiao] )\nVAR s = [Semana de Referência]\n"
         "VAR atuais = VALUES ( regiao_comparacao[uf] )\n"
         'VAR ufs = FILTER ( ALL ( regiao_comparacao[uf] ), r = "Brasil" || regiao_comparacao[uf] IN atuais )\nRETURN\n'
         "    CALCULATE (\n        DIVIDE (\n            SUMX ( fato_preco_uf_semana, fato_preco_uf_semana[preco_medio] "
         "* fato_preco_uf_semana[coletas] ),\n            SUM ( fato_preco_uf_semana[coletas] )\n        ),\n"
         "        REMOVEFILTERS ( dim_semana ),\n        REMOVEFILTERS ( dim_uf ),\n"
         "        TREATAS ( ufs, fato_preco_uf_semana[uf] ),\n        fato_preco_uf_semana[semana] = s\n    )"),
        ("Cor da Região", "Cores", None,
         'VAR u = SELECTEDVALUE ( dim_uf[uf], "BR" )\n'
         'VAR escolhida = IF ( u = "BR", "Brasil", LOOKUPVALUE ( regiao_comparacao[regiao], regiao_comparacao[uf], u ) )\n'
         'VAR r = SELECTEDVALUE ( regiao_comparacao[regiao] )\nRETURN\n'
         f'    IF ( r = escolhida, "{CORES["outros"]}", IF ( r = "Brasil", "#8B95A9", "#3A4660" ) )'),
        # cartões
        ("Variação 4 Semanas Posto", "Visão geral", VARIACAO_REAIS,
         "VAR a = [Preço no Posto]\nVAR b = [Preço no Posto 4 Semanas Antes]\nRETURN\n"
         "    IF ( NOT ISBLANK ( a ) && NOT ISBLANK ( b ), ROUND ( a - b, 2 ) )"),
        ("Variação 4 Semanas Posto %", "Visão geral", PCT_SINAL,
         variacao("[Preço no Posto]", "[Preço no Posto 4 Semanas Antes]")),
        ("Cor Variação 4 Semanas", "Cores", None,
         f'VAR d = [Variação 4 Semanas Posto]\nRETURN\n    IF ( d > 0, "{CORES["alta"]}", IF ( d < 0, "{CORES["baixa"]}", "{CORES["neutra"]}" ) )'),
        ("Impostos 12 Meses Antes", "Visão geral", REAIS, na_semana(IMPOSTOS, 364)),
        ("Apoio Impostos Curto", "Visão geral", None,
         'FORMAT ( DIVIDE ( [Impostos no Litro], [Preço no Posto] ), "0%" ) & " do preço · há 12 meses R$ " '
         '& FORMAT ( [Impostos 12 Meses Antes], "0.00" )'),
        # último cartão: etanol ÷ gasolina; com diesel escolhido, a refinaria do diesel em 12 meses
        ("Título Cartão 5", "Visão geral", None,
         'IF ( SELECTEDVALUE ( dim_produto[produto] ) = "DIESEL S10", "Refinaria em 12 meses", "Etanol ÷ gasolina" )'),
        ("Valor Cartão 5", "Visão geral", None,
         'IF ( SELECTEDVALUE ( dim_produto[produto] ) = "DIESEL S10", '
         'FORMAT ( [Variação 12 Meses Refinaria], "+0.0%;-0.0%" ), FORMAT ( [Etanol ÷ Gasolina], "0%" ) )'),
        ("Cor Cartão 5", "Cores", None,
         'IF ( SELECTEDVALUE ( dim_produto[produto] ) = "DIESEL S10", [Cor Variação 12 Meses Refinaria], [Cor Etanol] )'),
        ("Marca 70%", "Visão geral", None,
         'IF ( SELECTEDVALUE ( dim_produto[produto] ) = "DIESEL S10", "", "▲ 70%" )'),
        ("Região da Refinaria", "Visão geral", None,
         "// a ANP publica o preço da refinaria só por região: um estado usa o da região dele\n"
         'VAR u = SELECTEDVALUE ( dim_uf[uf], "BR" )\nRETURN\n'
         '    IF ( u = "BR", "Brasil", "região " & LOOKUPVALUE ( regiao_comparacao[regiao], regiao_comparacao[uf], u ) )'),
        ("Diferença para o Brasil", "Gráfico", VARIACAO_REAIS,
         "// preço da região (ou do estado escolhido) menos o do Brasil, na semana de referência\n"
         "VAR item = SELECTEDVALUE ( comparacao_item[item] )\nVAR tipo = SELECTEDVALUE ( comparacao_item[tipo] )\n"
         'VAR escolhido = SELECTEDVALUE ( dim_uf[uf], "BR" )\nVAR s = [Semana de Referência]\n'
         "VAR ufs =\n    SELECTCOLUMNS (\n        FILTER ( ALL ( regiao_comparacao ),\n"
         '            IF ( tipo = "Estado", regiao_comparacao[uf] = item, regiao_comparacao[regiao] = item ) ),\n'
         '        "uf", regiao_comparacao[uf]\n    )\n'
         "VAR preco =\n    CALCULATE (\n        DIVIDE ( SUMX ( fato_preco_uf_semana, fato_preco_uf_semana[preco_medio] "
         "* fato_preco_uf_semana[coletas] ), SUM ( fato_preco_uf_semana[coletas] ) ),\n"
         "        REMOVEFILTERS ( dim_semana ), REMOVEFILTERS ( dim_uf ),\n"
         "        TREATAS ( ufs, fato_preco_uf_semana[uf] ), fato_preco_uf_semana[semana] = s\n    )\n"
         "VAR brasil =\n    CALCULATE (\n        DIVIDE ( SUMX ( fato_preco_uf_semana, fato_preco_uf_semana[preco_medio] "
         "* fato_preco_uf_semana[coletas] ), SUM ( fato_preco_uf_semana[coletas] ) ),\n"
         "        REMOVEFILTERS ( dim_semana ), REMOVEFILTERS ( dim_uf ), fato_preco_uf_semana[semana] = s\n    )\n"
         "RETURN\n"
         '    IF ( tipo = "Estado" && item <> escolhido, BLANK (), IF ( NOT ISBLANK ( preco ), ROUND ( preco - brasil, 2 ) ) )'),
        ("Cor Diferença para o Brasil", "Cores", None,
         'VAR d = [Diferença para o Brasil]\nRETURN\n'
         f'    IF ( SELECTEDVALUE ( comparacao_item[tipo] ) = "Estado", "{CORES["outros"]}", '
         f'IF ( d > 0, "{CORES["alta"]}", "{CORES["baixa"]}" ) )'),
        ("Texto Preço Brasil", "Visão geral", None,
         '"Brasil R$ " & FORMAT ( CALCULATE ( [Preço no Posto], REMOVEFILTERS ( dim_uf ) ), "0.00" )'),
        ("Cor Fundo Barra", "Cores", None,
         'IF ( SELECTEDVALUE ( dim_produto[produto] ) = "DIESEL S10", "#111A2B", "#1F2A40" )'),
    ]
    return {C: composicao, "componente": componente}
