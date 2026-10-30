"""Gera o relatório (PBIR) em fabric/PrecosCombustiveis.Report, sobre o modelo PrecosCombustiveis.

    python tools/gerar_fundo.py      # imagem de fundo (molduras e textos fixos)
    python tools/gerar_relatorio.py

A página segue o desenho: a imagem de fundo traz o que não muda e os visuais do Power BI ficam por cima, sem fundo
próprio, nas posições de tools/layout_visao_geral.py. Campos: "tabela.coluna" para colunas e o nome da medida
para medidas (as medidas vêm de tools/gerar_modelo.py).
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_visao_geral as L  # noqa: E402
from gerar_modelo import MEDIDAS, NOME, TABELAS  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "fabric" / f"{NOME}.Report"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
TEMA_BASE = "CY26SU04"
TEMA = "TemaPrecosCombustiveis.json"
FUNDO = "fundo_visao_geral.png"
LARGURA, ALTURA = 1280, 720
COR = L.COR
FONTE, FONTE_FORTE = "Segoe UI", "Segoe UI Semibold"

TABELA_DA_MEDIDA = {m[0]: tabela for tabela, medidas in MEDIDAS.items() for m in medidas}


# --- blocos do formato PBIR ---------------------------------------------------------------------------------------

def lit(valor) -> dict:
    if isinstance(valor, bool):
        texto = "true" if valor else "false"
    elif isinstance(valor, int):
        texto = f"{valor}L"
    elif isinstance(valor, float):
        texto = f"{valor}D"
    else:
        texto = "'" + str(valor).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": texto}}}


def cor(hexa: str) -> dict:
    return {"solid": {"color": lit(hexa)}}


def cor_da_medida(medida: str) -> dict:
    return {"solid": {"color": {"expr": campo(medida)}}}


def campo(ref: str) -> dict:
    if ref in TABELA_DA_MEDIDA:
        return {"Measure": {"Expression": {"SourceRef": {"Entity": TABELA_DA_MEDIDA[ref]}}, "Property": ref}}
    tabela, coluna = ref.split(".", 1)
    if tabela not in TABELAS or coluna not in {c for c, _ in TABELAS[tabela]}:
        raise KeyError(f"campo desconhecido: {ref}")
    return {"Column": {"Expression": {"SourceRef": {"Entity": tabela}}, "Property": coluna}}


def projecao(ref: str, rotulo: str | None = None, ativo: bool = False) -> dict:
    f = campo(ref)
    tipo = "Column" if "Column" in f else "Measure"
    entidade, propriedade = f[tipo]["Expression"]["SourceRef"]["Entity"], f[tipo]["Property"]
    p = {"field": f, "queryRef": f"{entidade}.{propriedade}", "nativeQueryRef": rotulo or propriedade}
    if rotulo:
        p["displayName"] = rotulo
    if ativo:
        p["active"] = True
    return p


def campos(refs) -> list[dict]:
    return [projecao(*(r if isinstance(r, tuple) else (r,))) for r in refs]


def _literal_filtro(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return f"{v}L" if isinstance(v, int) else "'" + str(v).replace("'", "''") + "'"


def condicao_em(tabela: str, coluna: str, valores: list) -> dict:
    return {"Version": 2, "From": [{"Name": "t", "Entity": tabela, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": coluna}}],
                "Values": [[{"Literal": {"Value": _literal_filtro(v)}}] for v in valores]}}}]}


def filtro(ref: str, valores, nome: str) -> dict:
    tabela, coluna = ref.split(".", 1)
    valores = valores if isinstance(valores, list) else [valores]
    return {"name": nome, "field": campo(ref), "type": "Categorical",
            "filter": condicao_em(tabela, coluna, valores), "howCreated": "User"}


def transparente() -> dict:
    """Sem título, fundo, borda nem cabeçalho: o visual fica por cima da imagem de fundo."""
    return {"title": [{"properties": {"show": lit(False)}}],
            "background": [{"properties": {"show": lit(False)}}],
            "border": [{"properties": {"show": lit(False)}}],
            "dropShadow": [{"properties": {"show": lit(False)}}],
            "visualHeader": [{"properties": {"show": lit(False)}}],
            "padding": [{"properties": {k: lit(0.0) for k in ("top", "bottom", "left", "right")}}]}


# --- página -------------------------------------------------------------------------------------------------------

class Pagina:

    def __init__(self, nome: str, titulo: str, fundo: str | None = None):
        self.nome, self.titulo, self.fundo = nome, titulo, fundo
        self.visuais: list[dict] = []
        self.interacoes: list[dict] = []

    def _add(self, x, y, w, h, visual: dict, filtros: list | None = None) -> str:
        z = len(self.visuais) * 100
        nome = hashlib.sha1(f"{self.nome}/{len(self.visuais)}".encode()).hexdigest()[:20]
        conteiner = {
            "$schema": f"{SCHEMA}/visualContainer/2.11.0/schema.json",
            "name": nome,
            "position": {"x": round(x, 1), "y": round(y, 1), "z": z, "height": round(h, 1), "width": round(w, 1),
                         "tabOrder": z},
            "visual": {**visual, "visualContainerObjects": transparente(), "drillFilterOtherVisuals": True},
        }
        if filtros:
            conteiner["filterConfig"] = {"filters": [
                filtro(ref, valores, nome=hashlib.sha1(f"{nome}/{i}".encode()).hexdigest()[:20])
                for i, (ref, valores) in enumerate(filtros)]}
        self.visuais.append(conteiner)
        return nome

    def texto_dinamico(self, medida, x, y, w, h, tamanho, cor_texto=COR["texto"], medida_cor=None, forte=False,
                       fundo=COR["cartao"]):
        """Texto alinhado à esquerda (cartão de várias linhas, sem moldura nem rótulo)."""
        rotulos = {"fontSize": lit(float(tamanho)), "fontFamily": lit(FONTE_FORTE if forte else FONTE),
                   "color": cor_da_medida(medida_cor) if medida_cor else cor(cor_texto)}
        # num cartão de várias linhas, um texto aparece como título do cartão e um número como valor:
        # os dois recebem o mesmo estilo
        return self._add(x, y, w, h, {
            "visualType": "multiRowCard",
            "query": {"queryState": {"Values": {"projections": campos([medida])}}},
            "objects": {"dataLabels": [{"properties": rotulos}],
                        "categoryLabels": [{"properties": {"show": lit(False)}}],
                        "cardTitle": [{"properties": rotulos}],
                        "card": [{"properties": {"outline": lit("None"), "barShow": lit(False),
                                                 "cardPadding": lit(0.0), "cardBackground": cor(fundo)}}]}})

    def texto_longo(self, medida, x, y, w, h, tamanho, cor_texto):
        """Texto com quebra de linha (cartão simples)."""
        return self._add(x, y, w, h, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": campos([medida])}}},
            "objects": {"labels": [{"properties": {"fontSize": lit(float(tamanho)), "fontFamily": lit(FONTE),
                                                   "color": cor(cor_texto)}}],
                        "categoryLabels": [{"properties": {"show": lit(False)}}],
                        "wordWrap": [{"properties": {"show": lit(True)}}]}})

    def lista(self, coluna, x, y, w, h, padrao=None, filtros=None, obrigatorio=True, decrescente=False):
        """Filtro em lista suspensa, sem cabeçalho (o rótulo está na imagem de fundo)."""
        selecao = ({"strictSingleSelect": lit(True)} if obrigatorio
                   else {"strictSingleSelect": lit(False), "singleSelect": lit(True)})
        objetos = {"data": [{"properties": {"mode": lit("Dropdown")}}],
                   "general": [{"properties": {"outlineColor": cor(COR["cartao"]), "outlineWeight": lit(0.0)}}],
                   "selection": [{"properties": selecao}],
                   "header": [{"properties": {"show": lit(False)}}],
                   "items": [{"properties": {"fontColor": cor(COR["texto"]), "background": cor(COR["cartao"]),
                                             "textSize": lit(10.0), "fontFamily": lit(FONTE), "outline": lit("None")}}]}
        if padrao is not None:
            tabela, col = coluna.split(".", 1)
            objetos["general"][0]["properties"]["filter"] = {"filter": condicao_em(tabela, col, [padrao])}
        return self._add(x, y, w, h, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [projecao(coluna, ativo=True)]}},
                      "sortDefinition": {"sort": [{"field": campo(coluna),
                                                   "direction": "Descending" if decrescente else "Ascending"}]}},
            "objects": objetos}, filtros)

    def colunas_empilhadas(self, x, y, w, h, eixo, medidas, cores):
        pontos = [{"properties": {"fill": cor(c)}, "selector": {"metadata": projecao(m)["queryRef"]}}
                  for m, c in zip([m[0] for m in medidas], cores, strict=True)]
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "labelColor": cor(COR["suave"]),
                                             "fontFamily": lit(FONTE), "showAxisTitle": lit(False),
                                             "gridlineShow": lit(False), "axisType": lit("Categorical")}}],
            "valueAxis": [{"properties": {"show": lit(False), "showAxisTitle": lit(False),
                                          "gridlineShow": lit(False)}}],
            "legend": [{"properties": {"show": lit(True), "position": lit("Top"), "showTitle": lit(False),
                                       "fontSize": lit(9.0), "labelColor": cor(COR["suave"]),
                                       "fontFamily": lit(FONTE)}}],
            "labels": [{"properties": {"show": lit(False)}}],
            "totals": [{"properties": {"show": lit(True), "color": cor(COR["texto"]), "fontSize": lit(9.0),
                                       "fontFamily": lit(FONTE_FORTE)}}],
            "dataPoint": pontos,
        }
        return self._add(x, y, w, h, {
            "visualType": "columnChart",
            "query": {"queryState": {"Category": {"projections": [projecao(eixo, ativo=True)]},
                                     "Y": {"projections": campos(medidas)}},
                      "sortDefinition": {"sort": [{"field": campo(eixo), "direction": "Ascending"}]}},
            "objects": objetos})

    def barras_coloridas(self, x, y, w, h, categoria, medida, medida_cor):
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(10.0), "labelColor": cor(COR["texto"]),
                                             "fontFamily": lit(FONTE), "showAxisTitle": lit(False),
                                             "maxMarginFactor": lit(30), "innerPadding": lit(35.0)}}],
            "valueAxis": [{"properties": {"show": lit(False), "showAxisTitle": lit(False), "gridlineShow": lit(False)}}],
            "labels": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "color": cor(COR["texto"]),
                                       "fontFamily": lit(FONTE_FORTE)}}],
            "dataPoint": [{"properties": {"fill": cor_da_medida(medida_cor)},
                           "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}],
        }
        return self._add(x, y, w, h, {
            "visualType": "clusteredBarChart",
            "query": {"queryState": {"Category": {"projections": [projecao(categoria, ativo=True)]},
                                     "Y": {"projections": campos([medida])}},
                      "sortDefinition": {"sort": [{"field": campo(categoria), "direction": "Ascending"}]}},
            "objects": objetos})

    def botoes(self, coluna, x, y, w, h, padrao=None, filtros=None):
        """Filtro em botões lado a lado (um selecionado)."""
        tabela, col = coluna.split(".", 1)
        objetos = {"data": [{"properties": {"mode": lit("Basic")}}],
                   "general": [{"properties": {"orientation": lit(1.0),
                                               **({"filter": {"filter": condicao_em(tabela, col, [padrao])}}
                                                  if padrao else {})}}],
                   "selection": [{"properties": {"strictSingleSelect": lit(True)}}],
                   "header": [{"properties": {"show": lit(False)}}],
                   "items": [{"properties": {"fontColor": cor(COR["texto"]), "background": cor(COR["cartao"]),
                                             "textSize": lit(8.5), "fontFamily": lit(FONTE_FORTE),
                                             "outline": lit("None")}}]}
        return self._add(x, y, w, h, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [projecao(coluna, ativo=True)]}},
                      "sortDefinition": {"sort": [{"field": campo(coluna), "direction": "Ascending"}]}},
            "objects": objetos}, filtros)

    def barra(self, medida, resto, x, y, w, h, cor_barra):
        """Barra de progresso: parte preenchida e o restante (trilho), empilhadas em 100%."""
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(False)}}],
            "valueAxis": [{"properties": {"show": lit(False), "gridlineShow": lit(False)}}],
            "labels": [{"properties": {"show": lit(False)}}],
            "legend": [{"properties": {"show": lit(False)}}],
            "dataPoint": [{"properties": {"fill": cor(cor_barra)}, "selector": {"metadata": projecao(medida)["queryRef"]}},
                          {"properties": {"fill": cor(COR["trilho"])}, "selector": {"metadata": projecao(resto)["queryRef"]}}],
            "layout": [{"properties": {"innerPadding": lit(50.0)}}],
        }
        # o Power BI não desenha barras em visuais muito baixos: o visual é mais alto que a barra e o
        # espaçamento interno deixa a barra fina, centrada na altura pedida
        y, h = y - 9, h + 18
        return self._add(x, y, w, h, {
            "visualType": "hundredPercentStackedBarChart",
            # uma categoria qualquer com um valor só (o combustível escolhido): sem categoria o gráfico fica vazio
            "query": {"queryState": {"Category": {"projections": [projecao("dim_produto.nome", ativo=True)]},
                                     "Y": {"projections": campos([medida, resto])}}},
            "objects": objetos})

    def colunas_lado_a_lado(self, x, y, w, h, eixo, medidas, cores, rotulos_em=None):
        pontos = [{"properties": {"fill": cor(c)}, "selector": {"metadata": projecao(m)["queryRef"]}}
                  for m, c in zip([m[0] for m in medidas], cores, strict=True)]
        rotulos = [{"properties": {"show": lit(bool(rotulos_em)), "color": cor(COR["posto"]), "fontSize": lit(8.0),
                                   "fontFamily": lit(FONTE_FORTE), "labelPosition": lit("OutsideEnd")}}]
        if rotulos_em:  # rótulos só na série escolhida
            rotulos += [{"properties": {"showSeries": lit(m != rotulos_em)},
                         "selector": {"metadata": projecao(m)["queryRef"]}} for m in [x[0] for x in medidas]]
            rotulos = [rotulos[0]] + [{"properties": {"showSeries": lit(False)},
                                       "selector": {"metadata": projecao(m)["queryRef"]}}
                                      for m in [x[0] for x in medidas] if m != rotulos_em]
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(8.5), "labelColor": cor(COR["suave"]),
                                             "fontFamily": lit(FONTE), "showAxisTitle": lit(False),
                                             "gridlineShow": lit(False), "axisType": lit("Categorical")}}],
            "valueAxis": [{"properties": {"show": lit(True), "fontSize": lit(7.5), "labelColor": cor(COR["apagado"]),
                                          "fontFamily": lit(FONTE), "showAxisTitle": lit(False),
                                          "gridlineShow": lit(True), "gridlineColor": cor(COR["grade"]),
                                          "gridlineStyle": lit("solid")}}],
            "legend": [{"properties": {"show": lit(True), "position": lit("TopRight"), "showTitle": lit(False),
                                       "fontSize": lit(9.0), "labelColor": cor(COR["suave"]),
                                       "fontFamily": lit(FONTE)}}],
            "labels": rotulos,
            "dataPoint": pontos,
        }
        return self._add(x, y, w, h, {
            "visualType": "clusteredColumnChart",
            "query": {"queryState": {"Category": {"projections": [projecao(eixo, ativo=True)]},
                                     "Y": {"projections": campos(medidas)}},
                      "sortDefinition": {"sort": [{"field": campo(eixo), "direction": "Ascending"}]}},
            "objects": objetos})

    def barras_agrupadas(self, x, y, w, h, categoria, medidas, cores):
        pontos = [{"properties": {"fill": cor(c)}, "selector": {"metadata": projecao(m)["queryRef"]}}
                  for m, c in zip([m[0] for m in medidas], cores, strict=True)]
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "labelColor": cor(COR["texto"]),
                                             "fontFamily": lit(FONTE), "showAxisTitle": lit(False),
                                             "maxMarginFactor": lit(40)}}],
            "valueAxis": [{"properties": {"show": lit(False), "showAxisTitle": lit(False), "gridlineShow": lit(False)}}],
            "labels": [{"properties": {"show": lit(True), "fontSize": lit(8.5), "color": cor(COR["suave"]),
                                       "fontFamily": lit(FONTE_FORTE)}}],
            "legend": [{"properties": {"show": lit(True), "position": lit("TopRight"), "showTitle": lit(False),
                                       "fontSize": lit(8.5), "labelColor": cor(COR["suave"]), "fontFamily": lit(FONTE)}}],
            "dataPoint": pontos,
        }
        return self._add(x, y, w, h, {
            "visualType": "clusteredBarChart",
            "query": {"queryState": {"Category": {"projections": [projecao(categoria, ativo=True)]},
                                     "Y": {"projections": campos(medidas)}},
                      "sortDefinition": {"sort": [{"field": campo(categoria), "direction": "Ascending"}]}},
            "objects": objetos})

    def cascata(self, x, y, w, h, categoria, medida):
        """Gráfico em cascata: cada parte que subiu (laranja) ou caiu (azul) e o total no fim."""
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "labelColor": cor(COR["texto"]),
                                             "fontFamily": lit(FONTE), "showAxisTitle": lit(False),
                                             "concatenateLabels": lit(False)}}],
            "valueAxis": [{"properties": {"show": lit(False), "showAxisTitle": lit(False), "gridlineShow": lit(False)}}],
            "labels": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "color": cor(COR["texto"]),
                                       "fontFamily": lit(FONTE_FORTE)}}],
            "legend": [{"properties": {"show": lit(False)}}],
            "breakdown": [{"properties": {"totalLabel": lit("Total no posto")}}],
            "sentimentColors": [{"properties": {"increaseFill": cor(COR["alta"]), "decreaseFill": cor(COR["baixa"]),
                                                "totalFill": cor(COR["suave"])}}],
        }
        return self._add(x, y, w, h, {
            "visualType": "waterfallChart",
            "query": {"queryState": {"Category": {"projections": [projecao(categoria, ativo=True)]},
                                     "Y": {"projections": campos([medida])}},
                      "sortDefinition": {"sort": [{"field": campo(categoria), "direction": "Ascending"}]}},
            "objects": objetos})

    def interacao(self, origem, destino, tipo="DataFilter"):
        self.interacoes.append({"source": origem, "target": destino, "type": tipo})


# --- página: visão geral ------------------------------------------------------------------------------------------

def visao_geral() -> Pagina:
    p = Pagina("VisaoGeral", "Visão geral", fundo=FUNDO)
    # nota do canto superior direito
    p.texto_dinamico("Texto Dados Até a Semana", 1068, 22, 190, 18, 8.0, cor_texto=COR["nota"], fundo=COR["pagina"])
    p.texto_dinamico("Texto Postos e Fonte", 948, 39, 310, 18, 8.0, cor_texto=COR["nota"], fundo=COR["pagina"])
    # filtros
    for f, coluna, extra in [(L.COMBUSTIVEL, "dim_produto.nome",
                              {"padrao": "Gasolina comum", "filtros": [("dim_produto.produto", ["GASOLINA", "DIESEL S10"])]}),
                             (L.ESTADO, "dim_uf.estado", {"padrao": "Brasil"}),
                             (L.SEMANA, "semana_referencia.rotulo", {"obrigatorio": False, "decrescente": True})]:
        p.lista(coluna, f["x"] + f["rotulo_w"], f["y"] + 2, f["w"] - f["rotulo_w"] - 4, f["h"] - 4, **extra)
    # cartões: título na imagem de fundo; número grande e uma linha de apoio
    y = L.CARTAO_Y
    for i, (valor, cor_valor, apoio, cor_apoio, w_valor) in enumerate([
        ("Preço no Posto", None, "Apoio Preço no Posto", "Cor Apoio Preço no Posto", 110),
        (None, None, "Posto x Refinaria 12 Meses", None, None),
        ("Diferença Posto Refinaria", None, "Apoio Diferença Curto", None, 110),
        ("Variação Refinaria 4 Semanas", "Cor Refinaria 4 Semanas", "Apoio Repasse 4 Semanas", None, 211),
        ("Etanol ÷ Gasolina", "Cor Etanol", "Apoio Etanol", None, 211),
    ]):
        x = L.cartao_x(i)
        if valor:
            p.texto_dinamico(valor, x + 12, y + 32, w_valor, 40, 22.0, medida_cor=cor_valor, forte=True)
        p.texto_dinamico(apoio, x + 12, y + 96, 211, 22, 8.5, cor_texto=COR["suave"], medida_cor=cor_apoio)
    x = L.cartao_x(1)
    p.texto_dinamico("Variação 12 Meses Posto", x + 12, y + 34, 96, 36, 20.0, medida_cor="Cor Variação 12 Meses",
                     forte=True)
    p.texto_dinamico("Variação 12 Meses Refinaria", x + 108, y + 34, 115, 36, 20.0,
                     medida_cor="Cor Variação 12 Meses Refinaria", forte=True)
    for i, barra, cor_barra in [(3, "Texto Barra Repasse", COR["baixa"]), (4, "Texto Barra Etanol", COR["etanol"])]:
        # a barra é um texto de blocos "█" sobre um fundo da cor do trilho (o Power BI não desenha gráficos tão baixos)
        x = L.cartao_x(i)
        p.texto_dinamico(barra, x + L.BARRA_X, y + L.BARRA_Y - 3, L.BARRA_W, 14, 7.0, cor_texto=cor_barra,
                         fundo=COR["trilho"])
    # o que aconteceu com o preço, mês a mês
    g = L.GRAFICO
    p.colunas_lado_a_lado(g["x"] + 12, g["y"] + 54, g["w"] - 24, g["h"] - 62, "dim_semana.mes_rotulo",
                          [("Variação Mensal Posto R$", "Posto"), ("Variação Mensal Refinaria R$", "Refinaria (no litro)")],
                          [COR["posto"], COR["refinaria"]], rotulos_em="Variação Mensal Posto R$")
    # por que o preço mudou em 12 meses: frase-resumo e um gráfico de barras
    b = L.PONTE
    p.texto_dinamico("Manchete 12 Meses", b["x"] + 12, b["y"] + 56, b["w"] - 24, 28, 12.0,
                     medida_cor="Cor Conclusão 12 Meses", forte=True)
    p.barras_coloridas(b["x"] + 12, b["y"] + 90, b["w"] - 24, b["h"] - 98, "componente.componente",
                       "Variação 12 Meses do Componente", "Cor Variação 12 Meses do Componente")
    return p


def paginas() -> list[Pagina]:
    return [visao_geral()]


def tema() -> dict:
    return {"name": "TemaPrecosCombustiveis",
            "dataColors": [COR[c] for c in ("posto", "refinaria", "etanol", "texto", "suave")],
            # o botão selecionado do filtro de combustível usa a cor de primeiro plano do tema
            "foreground": COR["alta"], "foregroundNeutralSecondary": COR["suave"],
            "foregroundNeutralTertiary": COR["apagado"], "background": COR["cartao"], "backgroundLight": COR["cartao"],
            "backgroundNeutral": COR["borda"], "tableAccent": COR["alta"],
            "textClasses": {"callout": {"fontFace": FONTE_FORTE, "color": COR["texto"]},
                            "title": {"fontFace": FONTE_FORTE, "color": COR["texto"], "fontSize": 12},
                            "header": {"fontFace": FONTE_FORTE, "color": COR["texto"]},
                            "label": {"fontFace": FONTE, "color": COR["suave"]}},
            "visualStyles": {"*": {"*": {"dropShadow": [{"show": False}], "visualHeader": [{"show": False}]}}}}


def escrever(caminho: Path, conteudo) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n"
    caminho.write_text(texto, encoding="utf-8")


def fundo_da_pagina(p: Pagina) -> list[dict]:
    propriedades = {"color": cor(COR["pagina"]), "transparency": lit(0.0)}
    if p.fundo:
        propriedades["image"] = {"image": {
            "name": lit(p.fundo),
            "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1,
                                                     "ItemName": p.fundo}}},
            "scaling": lit("Fit")}}
    return [{"properties": propriedades}]


def gerar(destino: Path = DESTINO) -> list[Pagina]:
    if destino.exists():
        shutil.rmtree(destino)
    lista = paginas()
    imagens = sorted({p.fundo for p in lista if p.fundo})
    escrever(destino / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NOME}.SemanticModel"}}})
    versao = {"visual": "2.8.0", "report": "3.2.0", "page": "2.3.1"}
    escrever(destino / "definition" / "report.json", {
        "$schema": f"{SCHEMA}/report/3.3.0/schema.json",
        "themeCollection": {"baseTheme": {"name": TEMA_BASE, "reportVersionAtImport": versao, "type": "SharedResources"},
                            "customTheme": {"name": TEMA, "reportVersionAtImport": versao,
                                            "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": TEMA, "path": TEMA, "type": "CustomTheme"}]
             + [{"name": i, "path": i, "type": "Image"} for i in imagens]},
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": TEMA_BASE, "path": f"BaseThemes/{TEMA_BASE}.json", "type": "BaseTheme"}]}],
        "objects": {"outspacePane": [{"properties": {"visible": lit(False), "expanded": lit(False)}}]},
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}})
    escrever(destino / "definition" / "version.json", {
        "$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    escrever(destino / "definition" / "pages" / "pages.json", {
        "$schema": f"{SCHEMA}/pagesMetadata/1.1.0/schema.json",
        "pageOrder": [p.nome for p in lista], "activePageName": lista[0].nome})
    for p in lista:
        pasta = destino / "definition" / "pages" / p.nome
        escrever(pasta / "page.json", {
            "$schema": f"{SCHEMA}/page/2.1.0/schema.json", "name": p.nome, "displayName": p.titulo,
            "displayOption": "FitToPage", "height": ALTURA, "width": LARGURA,
            "objects": {"background": fundo_da_pagina(p),
                        "outspace": [{"properties": {"color": cor(COR["pagina"])}}]},
            **({"visualInteractions": p.interacoes} if p.interacoes else {})})
        for v in p.visuais:
            escrever(pasta / "visuals" / v["name"] / "visual.json", v)
    base = destino / "StaticResources" / "SharedResources" / "BaseThemes"
    base.mkdir(parents=True, exist_ok=True)
    shutil.copy(RAIZ / "tools" / "recursos" / f"{TEMA_BASE}.json", base / f"{TEMA_BASE}.json")
    registrados = destino / "StaticResources" / "RegisteredResources"
    escrever(registrados / TEMA, tema())
    for i in imagens:
        shutil.copy(RAIZ / "tools" / "recursos" / i, registrados / i)
    return lista


if __name__ == "__main__":
    gerado = gerar()
    print(f"relatório gerado em {DESTINO.relative_to(RAIZ)}: "
          + ", ".join(f"{p.titulo} ({len(p.visuais)} visuais)" for p in gerado))
