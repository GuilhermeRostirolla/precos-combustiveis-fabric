"""Gera o relatório (PBIR) em fabric/PrecosCombustiveis.Report, sobre o modelo PrecosCombustiveis.

    python tools/gerar_relatorio.py

Campos: "tabela.coluna" para colunas e o nome da medida para medidas (as medidas vêm de tools/gerar_modelo.py).
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gerar_modelo import MEDIDAS, NOME, TABELAS  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "fabric" / f"{NOME}.Report"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
TEMA_BASE = "CY26SU04"
TEMA = "TemaPrecosCombustiveis.json"
LARGURA, ALTURA = 1280, 720

COR = {"pagina": "#0A1020", "cartao": "#111A2C", "borda": "#1E2940", "texto": "#E8EDF5", "suave": "#9AA7BD",
       "apagado": "#62718B", "grade": "#1A2438", "alta": "#E8803A", "baixa": "#3FA7D6", "bomba": "#E8EDF5",
       "refinaria": "#E8803A", "gasolina": "#F2B33D", "diesel": "#5B8DEF", "barra": "#24365C"}

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


def filtro(ref: str, valores, nome: str, negar: bool = False) -> dict:
    tabela, coluna = ref.split(".", 1)
    valores = valores if isinstance(valores, list) else [valores]
    condicao = {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": coluna}}],
                       "Values": [[{"Literal": {"Value": _literal_filtro(v)}}] for v in valores]}}
    if negar:
        condicao = {"Not": {"Expression": condicao}}
    return {"name": nome, "field": campo(ref), "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": tabela, "Type": 0}],
                       "Where": [{"Condition": condicao}]},
            "howCreated": "User"}


def moldura(titulo: str | None, subtitulo: str | None = None, fundo: str | None = COR["cartao"],
            borda: bool = True, respiro: float = 12.0) -> dict:
    objetos = {
        "title": [{"properties": {"show": lit(bool(titulo)), **({
            "text": lit(titulo), "fontColor": cor(COR["texto"]), "fontSize": lit(12.0),
            "fontFamily": lit("Segoe UI Semibold")} if titulo else {})}}],
        "background": [{"properties": {"show": lit(fundo is not None),
                                       **({"color": cor(fundo), "transparency": lit(0.0)} if fundo else {})}}],
        "border": [{"properties": {"show": lit(borda), "color": cor(COR["borda"]), "radius": lit(12.0)}}],
        "dropShadow": [{"properties": {"show": lit(False)}}],
        "visualHeader": [{"properties": {"show": lit(False)}}],
        "padding": [{"properties": {k: lit(respiro) for k in ("top", "bottom", "left", "right")}}],
    }
    if subtitulo:
        objetos["subTitle"] = [{"properties": {"show": lit(True), "text": lit(subtitulo),
                                               "fontColor": cor(COR["suave"]), "fontSize": lit(9.0)}}]
    return objetos


# --- página -------------------------------------------------------------------------------------------------------

class Pagina:

    def __init__(self, nome: str, titulo: str, subtitulo: str, nota: str = "Texto Dados Até"):
        self.nome, self.titulo = nome, titulo
        self.visuais: list[dict] = []
        self.interacoes: list[dict] = []
        self.texto(titulo, 24, 14, 760, 36, 20, COR["texto"], negrito=True)
        self.texto(subtitulo, 24, 48, 900, 24, 10.5, COR["suave"])
        self.valor(nota, 840, 22, 416, 28, 9.0, COR["apagado"])

    def _add(self, x, y, w, h, visual: dict, filtros: list[dict] | None = None) -> None:
        z = len(self.visuais) * 100
        nome = hashlib.sha1(f"{self.nome}/{len(self.visuais)}".encode()).hexdigest()[:20]
        conteiner = {
            "$schema": f"{SCHEMA}/visualContainer/2.11.0/schema.json",
            "name": nome,
            "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
            "visual": {**visual, "drillFilterOtherVisuals": True},
        }
        if filtros:
            conteiner["filterConfig"] = {"filters": [
                filtro(*f[:2], nome=hashlib.sha1(f"{nome}/{i}".encode()).hexdigest()[:20],
                       negar=len(f) > 2 and f[2]) for i, f in enumerate(filtros)]}
        self.visuais.append(conteiner)
        return nome

    def texto(self, conteudo, x, y, w, h, tamanho, cor_texto, negrito=False):
        estilo = {"fontFamily": "Segoe UI Semibold" if negrito else "Segoe UI", "fontSize": f"{tamanho}pt",
                  "color": cor_texto}
        self._add(x, y, w, h, {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [
                {"textRuns": [{"value": conteudo, "textStyle": estilo}], "horizontalTextAlignment": "left"}]}}]},
            "visualContainerObjects": moldura(None, fundo=None, borda=False, respiro=0.0)})

    def valor(self, medida, x, y, w, h, tamanho, cor_valor, alinhamento="right"):
        self._add(x, y, w, h, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": campos([medida])}}},
            "objects": {"labels": [{"properties": {"fontSize": lit(float(tamanho)), "color": cor(cor_valor),
                                                   "fontFamily": lit("Segoe UI")}}],
                        "categoryLabels": [{"properties": {"show": lit(False)}}]},
            "visualContainerObjects": moldura(None, fundo=None, borda=False, respiro=0.0)})

    def kpi(self, medida, rotulo, contexto, x, y, w, h, filtros=None, cor_valor=COR["texto"]):
        self._add(x, y, w, h, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": campos([medida])}}},
            "objects": {"labels": [{"properties": {"fontSize": lit(26.0), "color": cor(cor_valor),
                                                   "fontFamily": lit("Segoe UI Semibold")}}],
                        "categoryLabels": [{"properties": {"show": lit(False)}}]},
            "visualContainerObjects": moldura(rotulo, contexto)}, filtros)

    def linhas(self, titulo, subtitulo, x, y, w, h, eixo, medidas, cores, legenda=None, filtros=None,
               formato_eixo_y=None, eixo_continuo=False, rotulo_eixo=None):
        query = {"Category": {"projections": [projecao(eixo, rotulo_eixo, ativo=True)]},
                 "Y": {"projections": campos(medidas)}}
        if legenda:
            query["Series"] = {"projections": [projecao(legenda)]}
        pontos = []
        if legenda:
            for valor_legenda, c in cores.items():
                pontos.append({"properties": {"fill": cor(c)}, "selector": {"data": [{"scopeId": {"Comparison": {
                    "ComparisonKind": 0, "Left": campo(legenda),
                    "Right": {"Literal": {"Value": _literal_filtro(valor_legenda)}}}}}]}})
        else:
            for medida, c in zip([m if isinstance(m, str) else m[0] for m in medidas], cores.values(), strict=True):
                pontos.append({"properties": {"fill": cor(c)}, "selector": {"metadata": projecao(medida)["queryRef"]}})
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(8.5), "labelColor": cor(COR["suave"]),
                                             "showAxisTitle": lit(not eixo_continuo),
                                             "titleColor": cor(COR["apagado"]), "titleFontSize": lit(8.5),
                                             "axisType": lit("Scalar" if eixo_continuo else "Categorical"),
                                             "gridlineShow": lit(False)}}],
            "valueAxis": [{"properties": {"show": lit(True), "fontSize": lit(8.5), "labelColor": cor(COR["apagado"]),
                                          "showAxisTitle": lit(False), "gridlineShow": lit(True),
                                          "gridlineColor": cor(COR["grade"]), "gridlineStyle": lit("solid"),
                                          **({"labelDisplayUnits": lit(1.0)} if formato_eixo_y else {})}}],
            "legend": [{"properties": {"show": lit(True), "position": lit("Top"), "showTitle": lit(False),
                                       "fontSize": lit(9.0), "labelColor": cor(COR["suave"])}}],
            "lineStyles": [{"properties": {"strokeWidth": lit(2.5), "showMarker": lit(not eixo_continuo),
                                           "markerSize": lit(4.0)}}],
            "dataPoint": pontos,
        }
        self._add(x, y, w, h, {"visualType": "lineChart", "query": {"queryState": query,
                                                                     "sortDefinition": {"sort": [{
                                                                         "field": campo(eixo),
                                                                         "direction": "Ascending"}]}},
                               "objects": objetos, "visualContainerObjects": moldura(titulo, subtitulo)}, filtros)

    def tabela(self, titulo, subtitulo, x, y, w, h, colunas, ordem, crescente=False, filtros=None, barras=None):
        objetos = {
            "columnHeaders": [{"properties": {"fontColor": cor(COR["apagado"]), "bold": lit(True),
                                              "backColor": cor(COR["cartao"]), "fontSize": lit(8.5),
                                              "outline": lit("BottomOnly"), "wordWrap": lit(True)}}],
            "values": [{"properties": {"fontSize": lit(9.0), "fontColorPrimary": cor(COR["texto"]),
                                       "fontColorSecondary": cor(COR["texto"]), "backColorPrimary": cor(COR["cartao"]),
                                       "backColorSecondary": cor(COR["cartao"])}}],
            "grid": [{"properties": {"gridHorizontal": lit(True), "gridHorizontalColor": cor(COR["grade"]),
                                     "gridVertical": lit(False), "outlineColor": cor(COR["borda"]),
                                     "rowPadding": lit(5)}}],
            "total": [{"properties": {"totals": lit(False)}}],
        }
        if barras:
            objetos["columnFormatting"] = [
                {"properties": {"dataBars": {"positiveColor": cor(c), "negativeColor": cor(c),
                                             "axisColor": cor(COR["borda"]), "reverseDirection": lit(False),
                                             "hideText": lit(False)}},
                 "selector": {"metadata": projecao(ref)["queryRef"]}} for ref, c in barras.items()]
        self._add(x, y, w, h, {
            "visualType": "tableEx",
            "query": {"queryState": {"Values": {"projections": campos(colunas)}},
                      "sortDefinition": {"sort": [{"field": campo(ordem),
                                                   "direction": "Ascending" if crescente else "Descending"}]}},
            "objects": objetos, "visualContainerObjects": moldura(titulo, subtitulo)}, filtros)

    def barras(self, titulo, subtitulo, x, y, w, h, categoria, medida, cor_barra, filtros=None, top=None):
        query = {"Category": {"projections": [projecao(categoria, ativo=True)]},
                 "Y": {"projections": campos([medida])}}
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(8.5), "labelColor": cor(COR["texto"]),
                                             "showAxisTitle": lit(False), "maxMarginFactor": lit(40)}}],
            "valueAxis": [{"properties": {"show": lit(False), "showAxisTitle": lit(False), "gridlineShow": lit(False)}}],
            "labels": [{"properties": {"show": lit(True), "fontSize": lit(8.5), "color": cor(COR["texto"])}}],
            "dataPoint": [{"properties": {"defaultColor": cor(cor_barra)}}],
        }
        self._add(x, y, w, h, {"visualType": "clusteredBarChart",
                               "query": {"queryState": query, "sortDefinition": {"sort": [{
                                   "field": campo(medida), "direction": "Descending"}]}},
                               "objects": objetos, "visualContainerObjects": moldura(titulo, subtitulo)}, filtros)

    def fundo(self, x, y, w, h):
        """Moldura vazia, usada para agrupar visuais num mesmo cartão."""
        return self._add(x, y, w, h, {
            "visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": [
                {"textRuns": [{"value": " "}]}]}}]},
            "visualContainerObjects": moldura(None, fundo=COR["cartao"], borda=True, respiro=0.0)})

    def segmentacao(self, coluna, rotulo, x, y, w, h, padrao=None, filtros=None, obrigatorio=True, decrescente=False):
        selecao = ({"strictSingleSelect": lit(True)} if obrigatorio
                   else {"strictSingleSelect": lit(False), "singleSelect": lit(True)})
        objetos = {"data": [{"properties": {"mode": lit("Dropdown")}}],
                   "selection": [{"properties": selecao}],
                   "header": [{"properties": {"show": lit(True), "text": lit(rotulo), "fontColor": cor(COR["suave"]),
                                              "textSize": lit(8.0), "outline": lit("None")}}],
                   "items": [{"properties": {"fontColor": cor(COR["texto"]), "background": cor(COR["cartao"]),
                                             "textSize": lit(10.0), "outline": lit("None")}}]}
        if padrao is not None:
            tabela, col = coluna.split(".", 1)
            objetos["general"] = [{"properties": {"filter": {"filter": {
                "Version": 2, "From": [{"Name": "t", "Entity": tabela, "Type": 0}],
                "Where": [{"Condition": {"In": {
                    "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": col}}],
                    "Values": [[{"Literal": {"Value": _literal_filtro(padrao)}}]]}}}]}}}}]
        return self._add(x, y, w, h, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [projecao(coluna, ativo=True)]}},
                      "sortDefinition": {"sort": [{"field": campo(coluna),
                                                   "direction": "Descending" if decrescente else "Ascending"}]}},
            "objects": objetos,
            "visualContainerObjects": moldura(None, fundo=COR["cartao"], borda=True, respiro=4.0)}, filtros)

    def cartao(self, medida, x, y, w, h, tamanho, cor_valor=COR["texto"], medida_cor=None, titulo=None,
               fundo=None, borda=False, quebra=False, negrito=True):
        rotulos = {"fontSize": lit(float(tamanho)), "fontFamily": lit("Segoe UI Semibold" if negrito else "Segoe UI"),
                   "color": cor(cor_valor)}
        if medida_cor:
            rotulos["color"] = {"solid": {"color": {"expr": campo(medida_cor)}}}
        objetos = {"labels": [{"properties": rotulos}], "categoryLabels": [{"properties": {"show": lit(False)}}]}
        if quebra:
            objetos["wordWrap"] = [{"properties": {"show": lit(True)}}]
        return self._add(x, y, w, h, {
            "visualType": "card",
            "query": {"queryState": {"Values": {"projections": campos([medida])}}},
            "objects": objetos,
            "visualContainerObjects": moldura(titulo, fundo=fundo, borda=borda, respiro=6.0 if titulo else 0.0)})

    def colunas_empilhadas(self, titulo, subtitulo, x, y, w, h, eixo, medidas, cores, total=None):
        pontos = [{"properties": {"fill": cor(c)}, "selector": {"metadata": projecao(m)["queryRef"]}}
                  for m, c in zip([m[0] for m in medidas], cores, strict=True)]
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "labelColor": cor(COR["suave"]),
                                             "showAxisTitle": lit(False), "gridlineShow": lit(False),
                                             "axisType": lit("Categorical")}}],
            "valueAxis": [{"properties": {"show": lit(False), "showAxisTitle": lit(False),
                                          "gridlineShow": lit(False)}}],
            "legend": [{"properties": {"show": lit(True), "position": lit("Top"), "showTitle": lit(False),
                                       "fontSize": lit(9.0), "labelColor": cor(COR["suave"])}}],
            "labels": [{"properties": {"show": lit(False)}}],
            "totals": [{"properties": {"show": lit(True), "color": cor(COR["texto"]), "fontSize": lit(9.0)}}],
            "dataPoint": pontos,
        }
        return self._add(x, y, w, h, {
            "visualType": "columnChart",
            "query": {"queryState": {"Category": {"projections": [projecao(eixo, ativo=True)]},
                                     "Y": {"projections": campos(medidas)}},
                      "sortDefinition": {"sort": [{"field": campo(eixo), "direction": "Ascending"}]}},
            "objects": objetos, "visualContainerObjects": moldura(titulo, subtitulo)})

    def barras_coloridas(self, x, y, w, h, categoria, medida, medida_cor):
        objetos = {
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "labelColor": cor(COR["texto"]),
                                             "showAxisTitle": lit(False), "maxMarginFactor": lit(60)}}],
            "valueAxis": [{"properties": {"show": lit(False), "showAxisTitle": lit(False), "gridlineShow": lit(False)}}],
            "labels": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "color": cor(COR["texto"])}}],
            "dataPoint": [{"properties": {"fill": {"solid": {"color": {"expr": campo(medida_cor)}}}},
                           "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}],
        }
        return self._add(x, y, w, h, {
            "visualType": "clusteredBarChart",
            "query": {"queryState": {"Category": {"projections": [projecao(categoria, ativo=True)]},
                                     "Y": {"projections": campos([medida])}},
                      "sortDefinition": {"sort": [{"field": campo(categoria), "direction": "Ascending"}]}},
            "objects": objetos, "visualContainerObjects": moldura(None, fundo=None, borda=False, respiro=0.0)})

    def interacao(self, origem, destino, tipo="DataFilter"):
        self.interacoes.append({"source": origem, "target": destino, "type": tipo})


# --- páginas ------------------------------------------------------------------------------------------------------

GAS, DIESEL = ("dim_produto.produto", "GASOLINA"), ("dim_produto.produto", "DIESEL S10")
ESTADO = ("repasse_resumo.escopo", "RS (estado)")
CORES_DIRECAO = {"alta": COR["alta"], "baixa": COR["baixa"]}


CORES_COMPOSICAO = ["#3BA3D9", "#8A7CF0", "#E8833A"]


def visao_geral() -> Pagina:
    p = Pagina("P0VisaoGeral", "Preço dos combustíveis", "Quanto custa hoje, quanto mudou e por quê",
               nota="Texto Semana de Referência")
    # filtros
    produto = p.segmentacao("dim_produto.produto", "Combustível", 24, 78, 200, 54, padrao="GASOLINA",
                            filtros=[("dim_produto.produto", ["GASOLINA", "DIESEL S10"])])
    estado = p.segmentacao("dim_uf.estado", "Estado", 234, 78, 160, 54, padrao="Brasil")
    semana = p.segmentacao("semana_referencia.rotulo", "Semana (vazio = a mais recente)", 404, 78, 220, 54,
                           obrigatorio=False, decrescente=True)
    # cartões: título e número num visual, a linha de apoio noutro por cima
    x, y, w, h, gap = 24, 140, 301, 88, 9
    for i, (titulo, medida, apoio, medida_cor, c) in enumerate([
        ("Preço médio no posto (R$/litro)", "Preço no Posto", "Apoio Preço no Posto", None, COR["texto"]),
        ("Refinaria no litro (R$, sem impostos)", "Refinaria no Litro do Posto", "Apoio Refinaria", None,
         COR["texto"]),
        ("Diferença posto − refinaria (R$/litro)", "Diferença Posto Refinaria", "Apoio Diferença", None,
         COR["texto"]),
        ("Postos pesquisados na semana", "Postos Pesquisados", "Apoio Postos", None, COR["texto"]),
    ]):
        xi = x + i * (w + gap)
        p.fundo(xi, y, w, h)
        p.texto(titulo, xi + 12, y + 8, w - 24, 20, 9.0, COR["suave"])
        p.cartao(medida, xi + 6, y + 26, w - 12, 36, 20.0, cor_valor=c or COR["texto"], medida_cor=medida_cor)
        p.cartao(apoio, xi + 6, y + 62, w - 12, 20, 8.5, cor_valor=COR["suave"], negrito=False)
    # do que é feito o preço, mês a mês
    grafico = p.colunas_empilhadas(
        "Do que é feito o preço, mês a mês",
        "R$ por litro no posto. Clique num mês para ver por que o preço mudou.",
        24, 240, 832, 456, "dim_semana.mes_rotulo",
        [("Refinaria no Mês", "Refinaria"), ("Impostos no Mês", "Impostos"),
         ("Outros no Mês", "Etanol/biodiesel, frete e margens")], CORES_COMPOSICAO)
    # por que mudou
    px, pw = 866, 390
    p.fundo(px, 240, pw, 456)
    p.cartao("Título Por Que Mudou", px + 8, 250, pw - 16, 30, 12.0)
    p.texto("Preço no posto, média do mês contra o mês anterior", px + 16, 284, pw - 32, 20, 9.0, COR["suave"])
    p.cartao("Texto Δ Posto", px + 8, 304, pw - 16, 46, 26.0, medida_cor="Cor Δ Posto")
    p.cartao("Texto De Para", px + 8, 350, pw - 16, 22, 9.0, cor_valor=COR["suave"], negrito=False)
    barras = p.barras_coloridas(px + 8, 380, pw - 16, 150, "componente.componente", "Variação do Componente",
                                "Cor do Componente")
    p.cartao("Conclusão", px + 8, 540, pw - 16, 30, 12.0, quebra=True)
    p.cartao("Conclusão Detalhe", px + 8, 572, pw - 16, 116, 9.5, cor_valor=COR["suave"], quebra=True,
             negrito=False)
    # o mês clicado no gráfico filtra as barras do "por quê" (em vez de só destacar)
    p.interacao(grafico, barras)
    del produto, estado, semana
    return p


def paginas() -> list[Pagina]:
    resumo = Pagina("P1Repasse", "Da refinaria à bomba no RS",
                    "Quanto de cada reajuste da refinaria chegou ao posto, desde jan/2023")
    y, w, h = 92, 293, 104
    for i, (produto, rotulo, direcao, medida) in enumerate([
        (GAS, "Gasolina · alta na refinaria", "alta", "Repasse em 2 Semanas (alta)"),
        (GAS, "Gasolina · baixa na refinaria", "baixa", "Repasse em 2 Semanas (baixa)"),
        (DIESEL, "Diesel S10 · alta na refinaria", "alta", "Repasse em 2 Semanas (alta)"),
        (DIESEL, "Diesel S10 · baixa na refinaria", "baixa", "Repasse em 2 Semanas (baixa)"),
    ]):
        resumo.kpi(medida, rotulo, "do reajuste chegou à bomba em 2 semanas", 24 + i * (w + 10), y, w, h,
                   filtros=[produto], cor_valor=CORES_DIRECAO[direcao])
    for i, (produto, titulo) in enumerate([(GAS, "Gasolina comum"), (DIESEL, "Diesel S10")]):
        resumo.linhas(titulo, "% do reajuste que já chegou à bomba (100% = acompanhou a refinaria). "
                      "Só semanas com 3 ou mais reajustes.",
                      24 + i * 621, 208, 611, 492, "repasse_resumo.h", [("Repasse RS", "Repasse")],
                      CORES_DIRECAO, legenda="repasse_resumo.direcao", filtros=[produto, ESTADO],
                      rotulo_eixo="Semanas depois do reajuste")

    serie = Pagina("P2BombaRefinaria", "Bomba x refinaria",
                   "Preço médio no posto (RS) e custo da parcela fóssil do litro na refinaria (região Sul)")
    for i, (produto, titulo) in enumerate([(GAS, "Gasolina comum"), (DIESEL, "Diesel S10")]):
        serie.linhas(titulo, "R$ por litro, por semana", 24 + i * 621, 92, 611, 318, "dim_semana.semana",
                     [("Preço Bomba RS", "Bomba (RS)"), ("Custo Fóssil na Bomba", "Refinaria (parcela fóssil)")],
                     {"bomba": COR["bomba"], "refinaria": COR["refinaria"]},
                     filtros=[produto, ("dim_semana.ano", [2023, 2024, 2025, 2026, 2027])],
                     formato_eixo_y=True, eixo_continuo=True)
    serie.tabela("Reajustes na refinaria", "Do mais recente para o mais antigo. Semanas acompanhadas: até o "
                 "reajuste seguinte, no máximo 8", 24, 420, 1232, 280,
                 [("repasse_evento.semana_evento", "Semana do reajuste"), ("dim_produto.produto", "Produto"),
                  ("repasse_evento.direcao", "Sentido"), ("repasse_evento.semanas_reajuste", "Semanas de reajuste"),
                  ("repasse_evento.preco_antes", "Refinaria antes"), ("repasse_evento.preco_depois", "Refinaria depois"),
                  ("repasse_evento.variacao_refinaria_pct", "Variação"),
                  ("repasse_evento.repasse_esperado", "Esperado na bomba (R$/l)"),
                  ("repasse_evento.semanas_acompanhadas", "Semanas acompanhadas")],
                 ordem="repasse_evento.semana_evento", filtros=[("dim_produto.produto", ["GASOLINA", "DIESEL S10"])])

    municipios = Pagina("P3Municipios", "Municípios do RS",
                        "Cidades com pelo menos 5 postos pesquisados na semana")
    for i, (produto, titulo) in enumerate([(GAS, "Gasolina comum"), (DIESEL, "Diesel S10")]):
        municipios.tabela(f"{titulo}: quando a refinaria baixa",
                          "Quedas que chegaram a 80% na bomba em até 8 semanas; cidades com 3 ou mais quedas",
                          24 + i * 621, 92, 611, 300,
                          [("repasse_velocidade.escopo", "Município"), ("Reajustes no Município", "Quedas"),
                           ("% Chegou a 80%", "Chegaram a 80%"), ("Semanas até a Metade", "Semanas até a metade")],
                          ordem="% Chegou a 80%", crescente=True,
                          filtros=[produto, ("repasse_velocidade.direcao", "baixa"),
                                   ("repasse_velocidade.eventos", list(range(3, 40)))])
        municipios.barras(f"{titulo}: preço na semana mais recente", "Média dos postos pesquisados, R$ por litro",
                          24 + i * 621, 402, 611, 298, "fato_preco_municipio_semana.municipio",
                          "Preço Município Última Semana", COR["gasolina"] if i == 0 else COR["diesel"],
                          filtros=[produto, ("fato_preco_municipio_semana.uf", "RS"),
                                   ("fato_preco_municipio_semana.amostra_suficiente", True)])
    return [visao_geral(), resumo, serie, municipios]


def tema() -> dict:
    return {"name": "TemaPrecosCombustiveis",
            "dataColors": [COR[c] for c in ("alta", "baixa", "gasolina", "diesel", "bomba", "suave")],
            "foreground": COR["texto"], "foregroundNeutralSecondary": COR["suave"],
            "foregroundNeutralTertiary": COR["apagado"], "background": COR["cartao"], "backgroundLight": COR["cartao"],
            "backgroundNeutral": COR["borda"], "tableAccent": COR["alta"],
            "textClasses": {"callout": {"fontFace": "Segoe UI Semibold", "color": COR["texto"]},
                            "title": {"fontFace": "Segoe UI Semibold", "color": COR["texto"], "fontSize": 12},
                            "header": {"fontFace": "Segoe UI Semibold", "color": COR["texto"]},
                            "label": {"fontFace": "Segoe UI", "color": COR["suave"]}},
            "visualStyles": {"*": {"*": {"dropShadow": [{"show": False}], "visualHeader": [{"show": False}]}}}}


def escrever(caminho: Path, conteudo) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n"
    caminho.write_text(texto, encoding="utf-8")


def gerar(destino: Path = DESTINO) -> list[Pagina]:
    if destino.exists():
        shutil.rmtree(destino)
    lista = paginas()
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
             "items": [{"name": TEMA, "path": TEMA, "type": "CustomTheme"}]},
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
            "objects": {"background": [{"properties": {"color": cor(COR["pagina"]), "transparency": lit(0.0)}}],
                        "outspace": [{"properties": {"color": cor(COR["pagina"])}}]},
            **({"visualInteractions": p.interacoes} if p.interacoes else {})})
        for v in p.visuais:
            escrever(pasta / "visuals" / v["name"] / "visual.json", v)
    base = destino / "StaticResources" / "SharedResources" / "BaseThemes"
    base.mkdir(parents=True, exist_ok=True)
    shutil.copy(RAIZ / "tools" / "recursos" / f"{TEMA_BASE}.json", base / f"{TEMA_BASE}.json")
    escrever(destino / "StaticResources" / "RegisteredResources" / TEMA, tema())
    return lista


if __name__ == "__main__":
    gerado = gerar()
    print(f"relatório gerado em {DESTINO.relative_to(RAIZ)}: "
          + ", ".join(f"{p.titulo} ({len(p.visuais)} visuais)" for p in gerado))
