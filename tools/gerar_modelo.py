"""Gera o modelo semântico (TMDL) em fabric/PrecosCombustiveis.SemanticModel.

O modelo lê as tabelas gold do Warehouse em Direct Lake. O endereço do Warehouse fica como marcador e é
preenchido na publicação (tools/publicar_relatorio.py).

    python tools/gerar_modelo.py
"""
import json
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
NOME = "PrecosCombustiveis"
DESTINO = RAIZ / "fabric" / f"{NOME}.SemanticModel"
ENDPOINT, WAREHOUSE_ID = "COLE_AQUI_O_ENDPOINT_DO_WAREHOUSE", "COLE_AQUI_O_ID_DO_WAREHOUSE"

# Tipos das colunas como o Warehouse cria as tabelas (fabric/sql/03_gold.sql e 04_analise_repasse.sql).
# decimal com até 4 casas vira "decimal" (decimal fixo); com mais casas, "double".
TABELAS = {
    "dim_semana": [("semana", "date"), ("semana_fim", "date"), ("ano", "int"), ("mes", "int"),
                   ("ano_mes", "string"), ("rotulo", "string"), ("mes_inicio", "date"), ("mes_rotulo", "string")],
    "dim_uf": [("uf", "string"), ("estado", "string"), ("regiao", "string"), ("ordem", "int")],
    "semana_referencia": [("semana", "date"), ("rotulo", "string")],
    "componente": [("componente", "string"), ("ordem", "int")],
    "evento": [("data", "date"), ("semana", "date"), ("produto", "string"), ("tipo", "string"),
               ("descricao", "string")],
    "composicao_preco_semana": [("semana", "date"), ("uf", "string"), ("produto", "string"), ("preco_posto", "dec"),
                                ("fracao_fossil", "dec"), ("refinaria", "dec"), ("tributos_federais", "dec"),
                                ("icms", "dec"), ("outros", "dec")],
    "dim_produto": [("produto", "string"), ("tem_preco_refinaria", "bool")],
    "fato_preco_uf_semana": [("semana", "date"), ("uf", "string"), ("produto", "string"), ("preco_medio", "dec"),
                             ("coletas", "int"), ("postos", "int"), ("municipios", "int")],
    "fato_preco_municipio_semana": [("semana", "date"), ("uf", "string"), ("municipio", "string"),
                                    ("produto", "string"), ("preco_medio", "dec"), ("preco_mediano", "dec"),
                                    ("preco_minimo", "dec"), ("preco_maximo", "dec"), ("coletas", "int"),
                                    ("postos", "int"), ("amostra_suficiente", "bool")],
    "fato_preco_produtor_semana": [("semana", "date"), ("semana_fim", "date"), ("produto", "string"),
                                   ("regiao", "string"), ("preco_produtor", "dec"), ("fracao_fossil", "dec"),
                                   ("mandato", "string"), ("custo_fossil_por_litro", "dec")],
    "refinaria_suavizada": [("produto", "string"), ("semana", "date"), ("preco_produtor", "dec"),
                            ("fracao_fossil", "dec"), ("preco_suavizado", "dec")],
    "repasse_evento": [("produto", "string"), ("semana_evento", "date"), ("semana_fim_reajuste", "date"),
                       ("semanas_reajuste", "int"), ("direcao", "string"), ("preco_antes", "dec"),
                       ("preco_depois", "dec"), ("variacao_refinaria", "dec"), ("variacao_refinaria_pct", "double"),
                       ("fracao_fossil", "dec"), ("repasse_esperado", "dec"), ("proximo_reajuste", "date"),
                       ("semanas_acompanhadas", "int")],
    "repasse_curva": [("produto", "string"), ("semana_evento", "date"), ("direcao", "string"), ("escopo", "string"),
                      ("municipio", "string"), ("h", "int"), ("semana", "date"), ("preco_bomba_antes", "dec"),
                      ("preco_bomba", "dec"), ("variacao_bomba", "dec"), ("repasse_esperado", "dec"),
                      ("repasse", "dec")],
    "repasse_resumo": [("produto", "string"), ("escopo", "string"), ("direcao", "string"), ("h", "int"),
                       ("eventos", "int"), ("repasse_ponderado", "dec"), ("repasse_mediano", "dec"),
                       ("repasse_medio", "dec")],
    "repasse_velocidade": [("produto", "string"), ("escopo", "string"), ("direcao", "string"), ("eventos", "int"),
                           ("eventos_sem_80_no_horizonte", "int"), ("semanas_mediana_ate_50", "dec"),
                           ("semanas_mediana_ate_80", "dec")],
}
TIPOS = {"string": "string", "date": "dateTime", "int": "int64", "dec": "decimal", "double": "double",
         "bool": "boolean"}
FORMATOS = {"date": "dd/MM/yyyy", "int": "#,0", "dec": "#,0.0000", "double": "0.00%"}
FORMATO_COLUNA = {
    ("fato_preco_uf_semana", "preco_medio"): '"R$" #,0.000',
    ("fato_preco_municipio_semana", "preco_medio"): '"R$" #,0.000',
    ("fato_preco_municipio_semana", "preco_mediano"): '"R$" #,0.000',
    ("fato_preco_municipio_semana", "preco_minimo"): '"R$" #,0.000',
    ("fato_preco_municipio_semana", "preco_maximo"): '"R$" #,0.000',
    ("fato_preco_produtor_semana", "preco_produtor"): '"R$" #,0.0000',
    ("fato_preco_produtor_semana", "custo_fossil_por_litro"): '"R$" #,0.0000',
    ("fato_preco_produtor_semana", "fracao_fossil"): "0%",
    ("repasse_evento", "fracao_fossil"): "0%",
    ("repasse_evento", "preco_antes"): '"R$" #,0.0000',
    ("repasse_evento", "preco_depois"): '"R$" #,0.0000',
    ("repasse_evento", "variacao_refinaria"): '+"R$" #,0.0000;-"R$" #,0.0000',
    ("repasse_evento", "repasse_esperado"): '+"R$" #,0.0000;-"R$" #,0.0000',
    ("repasse_evento", "variacao_refinaria_pct"): "+0.0%;-0.0%",
    ("refinaria_suavizada", "preco_produtor"): '"R$" #,0.0000',
    ("refinaria_suavizada", "preco_suavizado"): '"R$" #,0.0000',
    ("refinaria_suavizada", "fracao_fossil"): "0%",
    ("repasse_curva", "repasse"): "0%",
    ("repasse_curva", "preco_bomba"): '"R$" #,0.000',
    ("repasse_curva", "preco_bomba_antes"): '"R$" #,0.000',
    ("repasse_curva", "variacao_bomba"): '+"R$" #,0.000;-"R$" #,0.000',
    ("repasse_curva", "repasse_esperado"): '+"R$" #,0.0000;-"R$" #,0.0000',
    ("repasse_curva", "h"): "0",
    ("repasse_resumo", "repasse_ponderado"): "0%",
    ("repasse_resumo", "repasse_mediano"): "0%",
    ("repasse_resumo", "repasse_medio"): "0%",
    ("repasse_resumo", "h"): "0",
    ("repasse_velocidade", "semanas_mediana_ate_50"): "0.0",
    ("repasse_velocidade", "semanas_mediana_ate_80"): "0.0",
    ("dim_semana", "ano"): "0",
    ("dim_uf", "ordem"): "0",
    ("componente", "ordem"): "0",
    ("composicao_preco_semana", "preco_posto"): '"R$" #,0.000',
    ("composicao_preco_semana", "refinaria"): '"R$" #,0.000',
    ("composicao_preco_semana", "tributos_federais"): '"R$" #,0.000',
    ("composicao_preco_semana", "icms"): '"R$" #,0.000',
    ("composicao_preco_semana", "outros"): '"R$" #,0.000',
    ("composicao_preco_semana", "fracao_fossil"): "0%",
    ("dim_semana", "mes"): "0",
}
OCULTAS = {
    "fato_preco_uf_semana": {"semana", "produto"},
    "fato_preco_municipio_semana": {"semana", "produto"},
    "fato_preco_produtor_semana": {"semana", "produto", "semana_fim"},
    "repasse_resumo": {"produto"},
    "repasse_velocidade": {"produto"},
    "repasse_evento": {"produto"},
    "repasse_curva": {"produto"},
    "refinaria_suavizada": {"produto", "semana"},
    "dim_semana": {"ano_mes"},
    "composicao_preco_semana": {"semana", "produto", "uf"},
    "dim_uf": {"ordem"},
    "componente": {"ordem"},
}
ORDENAR_POR = {("dim_semana", "rotulo"): "semana", ("dim_semana", "mes_rotulo"): "mes_inicio",
               ("dim_uf", "estado"): "ordem", ("semana_referencia", "rotulo"): "semana",
               ("componente", "componente"): "ordem"}

RELACIONAMENTOS = [
    ("fato_preco_uf_semana.semana", "dim_semana.semana"),
    ("fato_preco_uf_semana.produto", "dim_produto.produto"),
    ("fato_preco_municipio_semana.semana", "dim_semana.semana"),
    ("fato_preco_municipio_semana.produto", "dim_produto.produto"),
    ("fato_preco_produtor_semana.semana", "dim_semana.semana"),
    ("fato_preco_produtor_semana.produto", "dim_produto.produto"),
    ("repasse_resumo.produto", "dim_produto.produto"),
    ("repasse_velocidade.produto", "dim_produto.produto"),
    ("repasse_evento.produto", "dim_produto.produto"),
    ("repasse_curva.produto", "dim_produto.produto"),
    ("refinaria_suavizada.semana", "dim_semana.semana"),
    ("refinaria_suavizada.produto", "dim_produto.produto"),
    ("fato_preco_uf_semana.uf", "dim_uf.uf"),
    ("composicao_preco_semana.semana", "dim_semana.semana"),
    ("composicao_preco_semana.produto", "dim_produto.produto"),
    ("composicao_preco_semana.uf", "dim_uf.uf"),
]

REAIS, REAIS4, PCT, SEMANAS, INT = '"R$" #,0.000', '"R$" #,0.0000', "0%", "0.0", "#,0"
RS = 'fato_preco_uf_semana[uf] = "RS"'
SUL = 'fato_preco_produtor_semana[regiao] = "Sul"'
ESTADO = '"RS (estado)"'


def _ultima_semana(medida: str, tabela: str, filtro: str) -> str:
    return (f"VAR ultima =\n    CALCULATE ( MAX ( {tabela}[semana] ), {filtro}, REMOVEFILTERS ( dim_semana ) )\n"
            f"RETURN\n    CALCULATE ( {medida}, {tabela}[semana] = ultima, REMOVEFILTERS ( dim_semana ) )")


def _velocidade(coluna: str, direcao: str) -> str:
    return (f"CALCULATE (\n    MAX ( repasse_velocidade[{coluna}] ),\n    repasse_velocidade[escopo] = {ESTADO},\n"
            f'    repasse_velocidade[direcao] = "{direcao}"\n)')


def _repasse_em(h: int, direcao: str) -> str:
    return (f"CALCULATE (\n    MAX ( repasse_resumo[repasse_ponderado] ),\n    repasse_resumo[escopo] = {ESTADO},\n"
            f'    repasse_resumo[direcao] = "{direcao}",\n    repasse_resumo[h] = {h}\n)')


MEDIDAS = {
    "fato_preco_uf_semana": [
        ("Preço Bomba RS", "Preços", REAIS, f"CALCULATE ( AVERAGE ( fato_preco_uf_semana[preco_medio] ), {RS} )"),
        ("Preço Bomba Brasil", "Preços", REAIS,
         "VAR postos = SUMX ( fato_preco_uf_semana, fato_preco_uf_semana[coletas] )\n"
         "RETURN\n    DIVIDE ( SUMX ( fato_preco_uf_semana, fato_preco_uf_semana[preco_medio] "
         "* fato_preco_uf_semana[coletas] ), postos )"),
        ("Postos Pesquisados RS", "Preços", INT, f"CALCULATE ( SUM ( fato_preco_uf_semana[postos] ), {RS} )"),
        ("Preço Bomba RS Última Semana", "Preços", REAIS,
         _ultima_semana("[Preço Bomba RS]", "fato_preco_uf_semana", RS)),
        ("Semana Mais Recente", "Preços", "dd/MM/yyyy",
         f"CALCULATE ( MAX ( fato_preco_uf_semana[semana] ), {RS}, REMOVEFILTERS ( dim_semana ) )"),
        ("Texto Dados Até", "Preços", None,
         '"Postos pesquisados até a semana de " & FORMAT ( [Semana Mais Recente], "dd/MM/yyyy" )'),
    ],
    "fato_preco_municipio_semana": [
        ("Preço Município Última Semana", "Preços", REAIS,
         "VAR ultima = [Semana Mais Recente]\nRETURN\n    CALCULATE (\n"
         "        AVERAGE ( fato_preco_municipio_semana[preco_medio] ),\n"
         "        fato_preco_municipio_semana[semana] = ultima,\n        REMOVEFILTERS ( dim_semana )\n    )"),
    ],
    "fato_preco_produtor_semana": [
        ("Preço Refinaria Sul", "Refinaria", REAIS4,
         f"CALCULATE ( AVERAGE ( fato_preco_produtor_semana[preco_produtor] ), {SUL} )"),
    ],
    "refinaria_suavizada": [
        ("Refinaria Sul Suavizada", "Refinaria", REAIS4, "AVERAGE ( refinaria_suavizada[preco_suavizado] )"),
        ("Custo Fóssil na Bomba", "Refinaria", REAIS,
         "// preço na refinaria (suavizado) x parcela fóssil do litro vendido no posto\n"
         "AVERAGEX ( refinaria_suavizada, refinaria_suavizada[preco_suavizado] * refinaria_suavizada[fracao_fossil] )"),
        ("Bomba menos Refinaria", "Refinaria", REAIS,
         "// tudo o que não é o derivado fóssil: etanol ou biodiesel, impostos, frete e margens\n"
         "IF (\n    NOT ISBLANK ( [Preço Bomba RS] ) && NOT ISBLANK ( [Custo Fóssil na Bomba] ),\n"
         "    [Preço Bomba RS] - [Custo Fóssil na Bomba]\n)"),
    ],
    "repasse_evento": [
        ("Reajustes na Refinaria", "Repasse", INT, "COUNTROWS ( repasse_evento )"),
        ("Altas na Refinaria", "Repasse", INT,
         'CALCULATE ( COUNTROWS ( repasse_evento ), repasse_evento[direcao] = "alta" )'),
        ("Baixas na Refinaria", "Repasse", INT,
         'CALCULATE ( COUNTROWS ( repasse_evento ), repasse_evento[direcao] = "baixa" )'),
    ],
    "repasse_curva": [
        ("Repasse do Reajuste", "Repasse", PCT,
         f"CALCULATE ( AVERAGE ( repasse_curva[repasse] ), repasse_curva[escopo] = {ESTADO} )"),
    ],
    "repasse_resumo": [
        ("Repasse RS", "Repasse", PCT,
         "// soma das variações na bomba / soma dos repasses esperados, no estado;\n"
         "// semana com menos de 3 reajustes acompanhados fica em branco (um reajuste só distorce a curva)\n"
         f"IF (\n    [Reajustes Acompanhados] >= 3,\n"
         f"    CALCULATE ( MAX ( repasse_resumo[repasse_ponderado] ), repasse_resumo[escopo] = {ESTADO} )\n)"),
        ("Repasse Mediano RS", "Repasse", PCT,
         f"CALCULATE ( MAX ( repasse_resumo[repasse_mediano] ), repasse_resumo[escopo] = {ESTADO} )"),
        ("Reajustes Acompanhados", "Repasse", INT,
         f"CALCULATE ( MAX ( repasse_resumo[eventos] ), repasse_resumo[escopo] = {ESTADO} )"),
        ("Repasse na Semana (alta)", "Repasse", PCT, _repasse_em(0, "alta")),
        ("Repasse na Semana (baixa)", "Repasse", PCT, _repasse_em(0, "baixa")),
        ("Repasse em 2 Semanas (alta)", "Repasse", PCT, _repasse_em(2, "alta")),
        ("Repasse em 2 Semanas (baixa)", "Repasse", PCT, _repasse_em(2, "baixa")),
        ("Repasse em 4 Semanas (alta)", "Repasse", PCT, _repasse_em(4, "alta")),
        ("Repasse em 4 Semanas (baixa)", "Repasse", PCT, _repasse_em(4, "baixa")),
    ],
    "repasse_velocidade": [
        ("Semanas até 80% (alta)", "Velocidade", SEMANAS, _velocidade("semanas_mediana_ate_80", "alta")),
        ("Semanas até 80% (baixa)", "Velocidade", SEMANAS, _velocidade("semanas_mediana_ate_80", "baixa")),
        ("Semanas até 50% (alta)", "Velocidade", SEMANAS, _velocidade("semanas_mediana_ate_50", "alta")),
        ("Semanas até 50% (baixa)", "Velocidade", SEMANAS, _velocidade("semanas_mediana_ate_50", "baixa")),
        ("Reajustes no Município", "Velocidade", INT, "SUM ( repasse_velocidade[eventos] )"),
        ("% Chegou a 80%", "Velocidade", PCT,
         "// reajustes em que a bomba chegou a 80% do esperado em até 8 semanas\n"
         "DIVIDE (\n    SUM ( repasse_velocidade[eventos] ) - SUM ( repasse_velocidade[eventos_sem_80_no_horizonte] ),\n"
         "    SUM ( repasse_velocidade[eventos] )\n)"),
        ("Semanas até a Metade", "Velocidade", None,
         "VAR s = MAX ( repasse_velocidade[semanas_mediana_ate_50] )\nRETURN\n"
         '    IF (\n        NOT ISBLANK ( s ),\n        SWITCH ( TRUE (), s > 8, "mais de 8", s = INT ( s ), FORMAT ( s, "0" ), '
         'FORMAT ( s, "0.0" ) )\n    )'),
    ],
}

from medidas_visao_geral import medidas_visao_geral  # noqa: E402

MEDIDAS.update(medidas_visao_geral())


def tag(*partes: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "precos-combustiveis/" + "/".join(partes)))


def nome_tmdl(nome: str) -> str:
    return nome if nome.replace("_", "").isalnum() and nome.isascii() else "'" + nome.replace("'", "''") + "'"


def bloco_dax(dax: str) -> str:
    if "\n" not in dax:
        return " " + dax
    linhas = "\n".join("\t\t\t" + linha for linha in dax.splitlines())
    return f" ```\n{linhas}\n\t\t\t```"


def texto_tmdl(valor: str) -> str:
    return '"' + valor.replace('"', '""') + '"' if '"' in valor else valor


def tabela(nome: str, colunas: list[tuple[str, str]]) -> str:
    saida = [f"table {nome}", f"\tlineageTag: {tag(nome)}", f"\tsourceLineageTag: [gold].[{nome}]", ""]
    for medida, pasta, formato, dax in MEDIDAS.get(nome, []):
        saida.append(f"\tmeasure {nome_tmdl(medida)} ={bloco_dax(dax)}")
        if formato:
            saida.append(f"\t\tformatString: {texto_tmdl(formato)}")
        saida += [f"\t\tdisplayFolder: {pasta}", f"\t\tlineageTag: {tag(nome, 'medida', medida)}", ""]
    for coluna, tipo in colunas:
        saida += [f"\tcolumn {coluna}", f"\t\tdataType: {TIPOS[tipo]}"]
        if (nome, coluna) in {("dim_semana", "semana"), ("dim_produto", "produto"), ("dim_uf", "uf")}:
            saida.append("\t\tisKey")
        formato = FORMATO_COLUNA.get((nome, coluna), FORMATOS.get(tipo))
        if formato:
            saida.append(f"\t\tformatString: {texto_tmdl(formato)}")
        if coluna in OCULTAS.get(nome, set()):
            saida.append("\t\tisHidden")
        saida += [f"\t\tlineageTag: {tag(nome, coluna)}", f"\t\tsourceLineageTag: {coluna}",
                  "\t\tsummarizeBy: none", f"\t\tsourceColumn: {coluna}"]
        if (nome, coluna) in ORDENAR_POR:
            saida.append(f"\t\tsortByColumn: {ORDENAR_POR[(nome, coluna)]}")
        saida += ["", "\t\tannotation SummarizationSetBy = Automatic", ""]
    saida += [f"\tpartition {nome} = entity", "\t\tmode: directLake", "\t\tsource",
              f"\t\t\tentityName: {nome}", "\t\t\tschemaName: gold", "\t\t\texpressionSource: DatabaseQuery", ""]
    return "\n".join(saida)


def relacionamentos() -> str:
    saida = []
    for de, para in RELACIONAMENTOS:
        saida += [f"relationship {tag('rel', de, para)}", f"\tfromColumn: {de}", f"\ttoColumn: {para}", ""]
    return "\n".join(saida)


def gerar(endpoint: str = ENDPOINT, warehouse_id: str = WAREHOUSE_ID, destino: Path = DESTINO) -> dict[str, str]:
    """Devolve {caminho relativo: conteúdo} e grava os arquivos em ``destino``."""
    arquivos = {
        "definition.pbism": json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.2", "settings": {}}, indent=2) + "\n",
        "definition/database.tmdl": "database\n\tcompatibilityLevel: 1604\n\n",
        "definition/model.tmdl": (
            "model Model\n\tculture: pt-BR\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
            "\tdiscourageImplicitMeasures\n\tsourceQueryCulture: pt-BR\n\n"
            + "".join(f"ref table {t}\n" for t in TABELAS) + "\n"),
        "definition/expressions.tmdl": (
            "expression DatabaseQuery =\n\t\tlet\n"
            f'\t\t    database = Sql.Database("{endpoint}", "{warehouse_id}")\n'
            "\t\tin\n\t\t    database\n"
            f"\tlineageTag: {tag('expressao')}\n\n\tannotation PBI_IncludeFutureArtifacts = False\n\n"),
        "definition/relationships.tmdl": relacionamentos(),
    }
    for nome, colunas in TABELAS.items():
        arquivos[f"definition/tables/{nome}.tmdl"] = tabela(nome, colunas)
    for caminho, conteudo in arquivos.items():
        (destino / caminho).parent.mkdir(parents=True, exist_ok=True)
        (destino / caminho).write_text(conteudo, encoding="utf-8")
    return arquivos


if __name__ == "__main__":
    gerados = gerar()
    medidas = sum(len(m) for m in MEDIDAS.values())
    print(f"modelo gerado em {DESTINO.relative_to(RAIZ)}: {len(TABELAS)} tabelas, "
          f"{len(RELACIONAMENTOS)} relacionamentos, {medidas} medidas")
