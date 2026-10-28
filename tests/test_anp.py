import io
import zipfile
from datetime import date, datetime

import pandas as pd
import pytest

from anp import descobrir_arquivos, ler_produtor, ler_revenda, selecionar_arquivos

CABECALHO = ("﻿Regiao - Sigla;Estado - Sigla;Municipio;Revenda;CNPJ da Revenda;Nome da Rua;Numero Rua;"
             "Complemento;Bairro;Cep;Produto;Data da Coleta;Valor de Venda;Valor de Compra;"
             "Unidade de Medida;Bandeira")
LINHAS = [
    "S;RS;BENTO GONCALVES;POSTO A LTDA;01.234.567/0001-89;RUA X;10;;CENTRO;95700-000;GASOLINA;02/01/2023;5,49;;R$ / litro;IPIRANGA",
    "S;RS;BENTO GONCALVES;POSTO A LTDA;01.234.567/0001-89;RUA X;10;;CENTRO;95700-000;ETANOL;02/01/2023;4,19;;R$ / litro;IPIRANGA",
    "SE;SP;CAMPINAS;POSTO B;11.111.111/0001-11;AV Y;1;;JD;13000-000;GASOLINA;03/01/2023; 5,09 ;;R$ / litro;BRANCA",
]


def _csv(linhas=LINHAS, cabecalho=CABECALHO, codificacao="utf-8"):
    return (cabecalho + "\n" + "\n".join(linhas) + "\n").encode(codificacao)


def test_le_csv_com_bom_e_renomeia_colunas():
    df = ler_revenda(_csv(), "precos-gasolina-etanol-01.csv")
    assert list(df.columns[:4]) == ["regiao", "uf", "municipio", "revenda"]
    assert len(df) == 3
    assert df.loc[2, "valor_venda"] == "5,09"  # espaços removidos, valor ainda como texto
    assert set(df["arquivo_origem"]) == {"precos-gasolina-etanol-01.csv"}


def test_le_csv_em_latin1():
    linhas = [LINHAS[0].replace("BENTO GONCALVES", "SÃO JOSÉ")]
    df = ler_revenda(_csv(linhas, CABECALHO.replace("﻿", ""), "latin-1"), "x.csv")
    assert df.loc[0, "municipio"] == "SÃO JOSÉ"


def test_le_zip_semestral():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ca-2023-01.csv", _csv())
    df = ler_revenda(buf.getvalue(), "ca-2023-01.zip")
    assert len(df) == 3
    assert df["arquivo_origem"].iloc[0] == "ca-2023-01.zip/ca-2023-01.csv"


def test_coluna_ausente_vira_vazia():
    cab = CABECALHO.replace(";Valor de Compra", "")
    linhas = [l.replace("5,49;;", "5,49;") for l in LINHAS[:1]]
    df = ler_revenda(_csv(linhas, cab), "x.csv")
    assert df.loc[0, "valor_compra"] == ""
    assert df.loc[0, "unidade"] == "R$ / litro"


HTML = """
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas/ca/ca-2022-02.zip">a</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas/ca/ca-2023-01.zip">a</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas/ca/ca-2026-01.zip">a</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas/ca/ca-2021-01.csv">a</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2026/05-dados-abertos-precos-glp.csv">glp</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2026/06-dados-abertos-precos-2026-06-gasolina-etanol.csv">a</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2026/07-dados-abertos-precos-gasolina-etanol.csv">a</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2026/07-dados-abertos-precos-diesel-gnv.csv">a</a>
<a href="/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2026/09-dados-abertos-precos-2026-09-diesel-gnv.csv">a</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2025/precos-gasolina-etanol-04.csv">a</a>
<a href="https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/qus/ultimas-4-semanas-diesel-gnv.csv">a</a>
"""


def test_descobre_semestrais_e_mensais_nos_dois_formatos_de_nome():
    arquivos = descobrir_arquivos(HTML)
    tipos = {(a.tipo, a.ano, a.periodo) for a in arquivos}
    assert ("semestral", 2023, 1) in tipos and ("semestral", 2021, 1) in tipos
    assert ("mensal", 2026, 6) in tipos and ("mensal", 2026, 7) in tipos and ("mensal", 2026, 9) in tipos
    assert ("mensal", 2025, 4) in tipos
    assert not any("glp" in a.url or "ultimas" in a.url for a in arquivos)
    assert all(a.url.startswith("https://www.gov.br/") for a in arquivos)


def test_selecao_nao_repete_mes_coberto_pelo_semestral():
    escolhidos = selecionar_arquivos(descobrir_arquivos(HTML), desde=date(2023, 1, 1))
    nomes = [a.nome for a in escolhidos]
    assert "ca-2022-02.zip" not in nomes and "ca-2021-01.csv" not in nomes
    assert "ca-2023-01.zip" in nomes and "ca-2026-01.zip" in nomes
    # junho/2026 já está no semestral 2026-01; abril/2025 também está coberto
    assert not any(a.tipo == "mensal" and a.primeiro_mes <= date(2026, 6, 1) for a in escolhidos)
    assert {(a.periodo, "diesel" in a.nome) for a in escolhidos if a.tipo == "mensal"} == {
        (7, False), (7, True), (9, True)}


def _planilha_produtor():
    linhas = [[None] * 10 for _ in range(12)]
    linhas[5][0] = "PREÇOS MÉDIOS PONDERADOS SEMANAIS"
    linhas[7][8] = "Brasil"
    linhas[8][1:8] = ["(A partir de 2013)", None, "Norte", "Nordeste", "Centro-Oeste", "Sul", "Sudeste"]
    linhas[9] = ["Gasolina A Comum (R$/litro)", datetime(2026, 10, 5), pd.Timestamp("2026-10-11"),
                 3.1, 3.2, "***", 3.0123, 3.05, 3.08, None]
    linhas[10] = ["Óleo Diesel S-10 (R$/litro)", datetime(2026, 10, 5), pd.Timestamp("2026-10-11"),
                  3.5, 3.6, 3.55, 3.4, 3.45, 3.5, None]
    linhas[11] = ["As informações são baseadas em dados preliminares.", None, None,
                  None, None, None, None, None, None, None]
    return pd.DataFrame(linhas)


def test_produtor_vira_formato_longo_com_regioes():
    df = ler_produtor(_planilha_produtor())
    assert set(df["regiao"]) == {"Norte", "Nordeste", "Centro-Oeste", "Sul", "Sudeste", "Brasil"}
    sul = df[(df["regiao"] == "Sul") & df["produto"].str.startswith("Gasolina A")].iloc[0]
    assert sul["preco"] == pytest.approx(3.0123)
    assert sul["semana_inicio"] == date(2026, 10, 5) and sul["semana_fim"] == date(2026, 10, 11)
    assert len(df) == 2 * 6  # nota de rodapé descartada


def test_produtor_sem_comercializacao_vira_nulo_mas_guarda_original():
    df = ler_produtor(_planilha_produtor())
    co = df[(df["regiao"] == "Centro-Oeste") & df["produto"].str.startswith("Gasolina")].iloc[0]
    assert pd.isna(co["preco"]) and co["valor_original"] == "***"
