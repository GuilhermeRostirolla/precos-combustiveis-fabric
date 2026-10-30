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
                   "selection": [{"properties": selecao}],
                   "header": [{"properties": {"show": lit(False)}}],
                   "items": [{"properties": {"fontColor": cor(COR["texto"]), "background": cor(COR["cartao"]),
                                             "textSize": lit(10.0), "fontFamily": lit(FONTE), "outline": lit("None")}}]}
        if padrao is not None:
            tabela, col = coluna.split(".", 1)
            objetos["general"] = [{"properties": {"filter": {"filter": condicao_em(tabela, col, [padrao])}}}]
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
            "categoryAxis": [{"properties": {"show": lit(True), "fontSize": lit(9.0), "labelColor": cor(COR["texto"]),
                                             "fontFamily": lit(FONTE), "showAxisTitle": lit(False),
                                             "maxMarginFactor": lit(60)}}],
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

    def interacao(self, origem, destino, tipo="DataFilter"):
        self.interacoes.append({"source": origem, "target": destino, "type": tipo})


# --- página: visão geral ------------------------------------------------------------------------------------------

def visao_geral() -> Pagina:
    p = Pagina("VisaoGeral", "Visão geral", fundo=FUNDO)
    # filtros: a lista fica à direita do rótulo desenhado no fundo
    combustivel, estado, semana = L.FILTROS
    for f, coluna, extra in [
        (combustivel, "dim_produto.produto", {"padrao": "GASOLINA",
                                              "filtros": [("dim_produto.produto", ["GASOLINA", "DIESEL S10"])]}),
        (estado, "dim_uf.estado", {"padrao": "Brasil"}),
        (semana, "semana_referencia.rotulo", {"obrigatorio": False, "decrescente": True}),
    ]:
        p.lista(coluna, f["x"] + f["rotulo_w"], f["y"] + 3, f["w"] - f["rotulo_w"] - 6, f["h"] - 6, **extra)
    n = L.NOTA
    p.texto_dinamico("Texto Semana de Referência", n["x"] + n["w"] - 300, n["y"], 300, n["h"], 9.0,
                     cor_texto=COR["suave"], fundo=COR["pagina"])
    # cartões: título na imagem de fundo; número e linha de apoio por cima
    for i, (medida, apoio) in enumerate([
        ("Preço no Posto", "Apoio Preço no Posto"),
        ("Refinaria no Litro do Posto", "Apoio Refinaria"),
        ("Diferença Posto Refinaria", "Apoio Diferença"),
        ("Postos Pesquisados", "Apoio Postos"),
    ]):
        x = L.cartao_x(i)
        p.texto_dinamico(medida, x + 10, L.CARTOES_Y + 30, L.CARTAO_W - 20, 40, 20.0, forte=True)
        p.texto_dinamico(apoio, x + 10, L.CARTOES_Y + 64, L.CARTAO_W - 20, 26, 9.0, cor_texto=COR["suave"])
    # do que é feito o preço, mês a mês
    g = L.GRAFICO
    grafico = p.colunas_empilhadas(
        g["x"] + 12, g["y"] + 58, g["w"] - 24, g["h"] - 68, "dim_semana.mes_rotulo",
        [("Refinaria no Mês", "Refinaria"), ("Impostos no Mês", "Impostos"),
         ("Outros no Mês", "Etanol/biodiesel, frete e margens")],
        [COR["refinaria"], COR["impostos"], COR["outros"]])
    # por que mudou
    pn, c = L.PAINEL, L.CONCLUSAO
    x, w = pn["x"] + 12, pn["w"] - 24
    p.texto_dinamico("Título Por Que Mudou", x, pn["y"] + 12, w, 26, 12.0, forte=True)
    p.texto_dinamico("Texto Δ Posto", x, pn["y"] + 66, w, 44, 24.0, medida_cor="Cor Δ Posto", forte=True)
    p.texto_dinamico("Texto De Para", x, pn["y"] + 110, w, 22, 9.0, cor_texto=COR["suave"])
    barras = p.barras_coloridas(x, pn["y"] + 140, w, 160, "componente.componente", "Variação do Componente",
                                "Cor do Componente")
    p.texto_dinamico("Conclusão", c["x"] + 8, c["y"] + 8, c["w"] - 16, 26, 11.0, forte=True, fundo=COR["caixa"])
    p.texto_longo("Conclusão Detalhe", c["x"] + 8, c["y"] + 34, c["w"] - 16, c["h"] - 40, 9.0, COR["suave"])
    # o mês clicado no gráfico filtra as barras do "por quê" (em vez de só destacar)
    p.interacao(grafico, barras)
    return p


def paginas() -> list[Pagina]:
    return [visao_geral()]


def tema() -> dict:
    return {"name": "TemaPrecosCombustiveis",
            "dataColors": [COR[c] for c in ("refinaria", "impostos", "outros", "texto", "suave")],
            "foreground": COR["texto"], "foregroundNeutralSecondary": COR["suave"],
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
