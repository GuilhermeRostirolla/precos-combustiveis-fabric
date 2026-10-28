"""Leitura das fontes públicas de preços de combustíveis da ANP.

Duas fontes:

- Série histórica do Levantamento de Preços de Combustíveis (LPC): preço de venda de cada posto
  pesquisado. Publicada em arquivos semestrais compactados (``dsas/ca/ca-AAAA-0S.zip``) e, para o
  semestre corrente, em arquivos mensais (``dsan/AAAA/...-gasolina-etanol.csv`` e
  ``...-diesel-gnv.csv``).
- Preços médios ponderados semanais de produtores e importadores: preço na saída da refinaria ou do
  importador, sem ICMS, por região. Uma planilha .xls atualizada toda semana.

As funções deste módulo não dependem de Spark nem do Fabric, então rodam nos testes locais e são
copiadas para o notebook de ingestão pelo instalador.
"""

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date

import pandas as pd

URL_PAGINA_SERIE = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis"
)
URL_PRODUTOR = (
    "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/ppidp/"
    "precos-medios-ponderados-semanais-2013.xls"
)

COLUNAS_REVENDA = {
    "regiao_sigla": "regiao",
    "estado_sigla": "uf",
    "municipio": "municipio",
    "revenda": "revenda",
    "cnpj_da_revenda": "cnpj",
    "nome_da_rua": "rua",
    "numero_rua": "numero",
    "complemento": "complemento",
    "bairro": "bairro",
    "cep": "cep",
    "produto": "produto",
    "data_da_coleta": "data_coleta",
    "valor_de_venda": "valor_venda",
    "valor_de_compra": "valor_compra",
    "unidade_de_medida": "unidade",
    "bandeira": "bandeira",
}


@dataclass(frozen=True)
class Arquivo:
    url: str
    nome: str
    tipo: str  # "semestral" ou "mensal"
    ano: int
    periodo: int  # semestre (1-2) ou mês (1-12)

    @property
    def primeiro_mes(self) -> date:
        mes = (self.periodo - 1) * 6 + 1 if self.tipo == "semestral" else self.periodo
        return date(self.ano, mes, 1)

    @property
    def ultimo_mes(self) -> date:
        mes = self.periodo * 6 if self.tipo == "semestral" else self.periodo
        return date(self.ano, mes, 1)


_RE_SEMESTRAL = re.compile(r"/dsas/ca/ca-(\d{4})-0([12])\.(?:zip|csv)$")


def _absoluta(url: str) -> str:
    return url if url.startswith("http") else "https://www.gov.br" + url


def _mes_do_nome(caminho: str) -> int | None:
    """Os arquivos mensais mudaram de nome ao longo do tempo; o mês aparece como prefixo
    (``06-dados-abertos-precos-2026-06-...``) ou como sufixo (``precos-gasolina-etanol-04.csv``)."""
    nome = caminho.rsplit("/", 1)[-1]
    inicio = re.match(r"(\d{2})-", nome)
    if inicio:
        return int(inicio.group(1))
    fim = re.search(r"-(\d{2})\.csv$", nome)
    return int(fim.group(1)) if fim else None


def descobrir_arquivos(html: str) -> list[Arquivo]:
    """Extrai da página da série histórica os arquivos de combustíveis automotivos."""
    arquivos = {}
    for link in re.findall(r'href="([^"]+?\.(?:zip|csv))"', html):
        url = _absoluta(link)
        semestral = _RE_SEMESTRAL.search(url)
        if semestral:
            ano, semestre = int(semestral.group(1)), int(semestral.group(2))
            arquivos[url] = Arquivo(url, url.rsplit("/", 1)[-1], "semestral", ano, semestre)
            continue
        if "/dsan/" in url and ("gasolina-etanol" in url or "diesel-gnv" in url):
            ano = int(re.search(r"/dsan/(\d{4})/", url).group(1))
            mes = _mes_do_nome(url)
            if mes and 1 <= mes <= 12:
                arquivos[url] = Arquivo(url, url.rsplit("/", 1)[-1], "mensal", ano, mes)
    return sorted(arquivos.values(), key=lambda a: (a.primeiro_mes, a.tipo, a.nome))


def selecionar_arquivos(arquivos: list[Arquivo], desde: date) -> list[Arquivo]:
    """Semestrais a partir de ``desde`` e, depois do último semestral, os mensais que faltam.

    Um mês nunca vem de duas fontes: se o semestral cobre o mês, o mensal é ignorado.
    """
    semestrais = [a for a in arquivos if a.tipo == "semestral" and a.ultimo_mes >= desde]
    coberto_ate = max((a.ultimo_mes for a in semestrais), default=date(desde.year, desde.month, 1))
    if not semestrais:
        coberto_ate = date(1900, 1, 1)
    mensais = [a for a in arquivos if a.tipo == "mensal" and a.primeiro_mes > coberto_ate
               and a.primeiro_mes >= desde]
    return semestrais + mensais


def _normalizar_coluna(nome: str) -> str:
    nome = nome.replace("﻿", "").replace("ï»¿", "")
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    nome = re.sub(r"[^a-zA-Z0-9]+", "_", nome.strip().lower()).strip("_")
    return nome


def _decodificar(conteudo: bytes) -> str:
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise ValueError("codificação desconhecida")


def _csvs(conteudo: bytes, nome: str):
    if nome.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            for interno in pacote.namelist():
                if interno.lower().endswith(".csv"):
                    yield f"{nome}/{interno}", pacote.read(interno)
    else:
        yield nome, conteudo


def ler_revenda(conteudo: bytes, nome: str) -> pd.DataFrame:
    """Lê um arquivo da série histórica (csv ou zip com csv) mantendo tudo como texto.

    As colunas são renomeadas para nomes estáveis; a tipagem e a validação ficam para a silver.
    """
    partes = []
    for origem, bruto in _csvs(conteudo, nome):
        texto = _decodificar(bruto)
        df = pd.read_csv(io.StringIO(texto), sep=";", dtype=str, keep_default_na=False)
        df.columns = [COLUNAS_REVENDA.get(_normalizar_coluna(c), _normalizar_coluna(c)) for c in df.columns]
        faltando = set(COLUNAS_REVENDA.values()) - set(df.columns)
        for coluna in faltando:
            df[coluna] = ""
        df = df[list(COLUNAS_REVENDA.values())]
        df = df.apply(lambda s: s.str.strip())
        df["arquivo_origem"] = origem
        partes.append(df)
    if not partes:
        raise ValueError(f"{nome}: nenhum csv encontrado")
    return pd.concat(partes, ignore_index=True)


def _rotulo(valor) -> str:
    return re.sub(r"\s+", " ", str(valor)).strip() if pd.notna(valor) else ""


def ler_produtor(tabela: pd.DataFrame) -> pd.DataFrame:
    """Converte a planilha de preços de produtores (lida com ``header=None``) para o formato longo.

    Uma linha por produto, semana e região. Células com ``***`` (sem comercialização) viram nulo.
    """
    linha_cabecalho = next(i for i in range(min(40, len(tabela)))
                           if any(_rotulo(v) == "Norte" for v in tabela.iloc[i]))
    regioes = {}
    for coluna in range(3, tabela.shape[1]):
        rotulo = _rotulo(tabela.iat[linha_cabecalho, coluna])
        if not rotulo:
            for acima in range(linha_cabecalho - 1, max(-1, linha_cabecalho - 4), -1):
                rotulo = _rotulo(tabela.iat[acima, coluna])
                if rotulo:
                    break
        if rotulo:
            regioes[coluna] = rotulo
    dados = tabela.iloc[linha_cabecalho + 1:].copy()
    dados["_inicio"] = pd.to_datetime(dados[1], errors="coerce")
    dados["_fim"] = pd.to_datetime(dados[2], errors="coerce")
    dados = dados[dados["_inicio"].notna() & dados["_fim"].notna() & dados[0].notna()]
    registros = []
    for coluna, regiao in regioes.items():
        parte = pd.DataFrame({
            "produto": dados[0].map(_rotulo).values,
            "semana_inicio": dados["_inicio"].dt.date.values,
            "semana_fim": dados["_fim"].dt.date.values,
            "regiao": regiao,
            "preco": pd.to_numeric(dados[coluna], errors="coerce").values,
            "valor_original": dados[coluna].map(_rotulo).values,
        })
        registros.append(parte)
    return pd.concat(registros, ignore_index=True)
