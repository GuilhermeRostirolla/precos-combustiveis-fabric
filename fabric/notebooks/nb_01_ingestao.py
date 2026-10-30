# %% [markdown]
# # nb_01 · Ingestão (bronze)
# Baixa as duas fontes da ANP e grava no lakehouse `lh_combustiveis` exatamente como vieram, só com os nomes
# das colunas padronizados e metadados de carga.
#
# - **Postos (LPC)**: arquivos semestrais compactados desde `DESDE` e, para o semestre corrente, os mensais.
#   Um arquivo só é baixado e reprocessado se for novo ou se o tamanho mudar (a ANP republica arquivos).
#   Os dois arquivos mais recentes são sempre reprocessados, porque ainda recebem correções.
# - **Produtores e importadores**: planilha semanal com o preço na saída da refinaria, sem ICMS, por região.
#   É pequena, então é recarregada inteira a cada execução.
# - **Levantamento semanal por estado**: preço médio de cada estado, publicado toda semana. Cobre as semanas
#   que a série histórica (mensal, com atraso) ainda não trouxe. Se a ANP estiver fora do ar, a carga segue
#   sem ela e a tabela fica como estava.
#
# No fim, o SQL endpoint do lakehouse é atualizado para o Warehouse enxergar as tabelas novas na mesma execução.

# %% tags=["parameters"]
DESDE = "2023-01-01"
FORCAR = False

# %%
# <<ANP>>  (o instalador substitui esta linha pelo conteúdo de src/anp.py)

# %%
import hashlib
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from pyspark.sql import functions as F

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "xlrd==2.0.1"], check=False)

RAIZ = Path("/lakehouse/default/Files/raw")
(RAIZ / "revenda").mkdir(parents=True, exist_ok=True)
(RAIZ / "produtor").mkdir(parents=True, exist_ok=True)
CABECALHOS = {"User-Agent": "Mozilla/5.0 (pipeline de dados publicos)"}
CARIMBO = datetime.now(timezone.utc)
sessao = requests.Session()
sessao.headers.update(CABECALHOS)


def baixar(url: str, tentativas: int = 4) -> bytes:
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = sessao.get(url, timeout=300)
            resposta.raise_for_status()
            return resposta.content
        except requests.RequestException:
            if tentativa == tentativas:
                raise
            time.sleep(20 * tentativa)


def tamanho_remoto(url: str) -> int | None:
    try:
        resposta = sessao.head(url, timeout=60, allow_redirects=True)
        return int(resposta.headers["content-length"]) if resposta.ok and "content-length" in resposta.headers else None
    except requests.RequestException:
        return None

# %%
pagina = baixar(URL_PAGINA_SERIE).decode("utf-8", errors="replace")
arquivos = selecionar_arquivos(descobrir_arquivos(pagina), desde=date.fromisoformat(DESDE))
if not arquivos:
    raise RuntimeError("Nenhum arquivo da série histórica encontrado na página da ANP")

controle = {}
if spark.catalog.tableExists("controle_arquivos"):
    controle = {r.url: r for r in spark.table("controle_arquivos").collect()}

ultimos = {a.url for a in sorted(arquivos, key=lambda a: (a.ultimo_mes, a.nome))[-2:]}
pendentes = []
for arquivo in arquivos:
    anterior = controle.get(arquivo.url)
    tamanho = tamanho_remoto(arquivo.url)
    mudou = anterior is None or tamanho is None or anterior.tamanho != tamanho
    if FORCAR or mudou or arquivo.url in ultimos:
        pendentes.append(arquivo)
print(f"{len(arquivos)} arquivos na série a partir de {DESDE}; {len(pendentes)} para baixar e carregar")

# %%
novos_controles = []
for arquivo in pendentes:
    conteudo = baixar(arquivo.url)
    (RAIZ / "revenda" / arquivo.nome).write_bytes(conteudo)
    pdf = ler_revenda(conteudo, arquivo.nome)
    pdf["arquivo_lote"] = arquivo.nome
    df = (spark.createDataFrame(pdf)
          .withColumn("periodo_inicio", F.lit(arquivo.primeiro_mes))
          .withColumn("periodo_fim", F.lit(arquivo.ultimo_mes))
          .withColumn("_data_carga", F.lit(CARIMBO)))
    if spark.catalog.tableExists("bronze_revenda"):
        (df.write.format("delta").mode("overwrite")
           .option("replaceWhere", f"arquivo_lote = '{arquivo.nome}'")
           .saveAsTable("bronze_revenda"))
    else:
        df.write.format("delta").saveAsTable("bronze_revenda")
    novos_controles.append((arquivo.url, arquivo.nome, arquivo.tipo, arquivo.primeiro_mes, arquivo.ultimo_mes,
                            len(conteudo), hashlib.sha256(conteudo).hexdigest(), len(pdf), CARIMBO))
    print(f"  {arquivo.nome:<60} {len(pdf):>9,} linhas")

# %%
conteudo = baixar(URL_PRODUTOR)
(RAIZ / "produtor" / URL_PRODUTOR.rsplit("/", 1)[-1]).write_bytes(conteudo)
import io
import pandas as pd
planilha = pd.read_excel(io.BytesIO(conteudo), header=None, engine="xlrd")
produtor = ler_produtor(planilha)
produtor["arquivo_origem"] = URL_PRODUTOR.rsplit("/", 1)[-1]
(spark.createDataFrame(produtor)
 .withColumn("_data_carga", F.lit(CARIMBO))
 .write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("bronze_produtor"))
print(f"produtores: {len(produtor):,} linhas, semanas de {produtor['semana_inicio'].min()} a {produtor['semana_inicio'].max()}")

# %%
ESQUEMA_SEMANAL = ("semana_inicio DATE, semana_fim DATE, uf STRING, produto STRING, postos INT, "
                   "preco_medio DOUBLE, unidade STRING, _data_carga TIMESTAMP")
try:
    conteudo = baixar(URL_SEMANAL_ESTADOS)
    (RAIZ / "produtor" / URL_SEMANAL_ESTADOS.rsplit("/", 1)[-1]).write_bytes(conteudo)
    semanal = ler_semanal_estados(pd.read_excel(io.BytesIO(conteudo), header=None))
    semanal = semanal[semanal["semana_inicio"] >= date.fromisoformat(DESDE)]
    (spark.createDataFrame(semanal.assign(_data_carga=CARIMBO), ESQUEMA_SEMANAL)
     .write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("bronze_revenda_semanal"))
    print(f"levantamento semanal: {len(semanal):,} linhas, até a semana de {semanal['semana_inicio'].max()}")
except Exception as erro:  # a fonte é complementar: sem ela, o relatório usa só a série histórica
    print(f"levantamento semanal não carregado: {erro}")
    if not spark.catalog.tableExists("bronze_revenda_semanal"):
        spark.createDataFrame([], ESQUEMA_SEMANAL).write.format("delta").saveAsTable("bronze_revenda_semanal")

# %%
if novos_controles:
    esquema = ("url STRING, nome STRING, tipo STRING, periodo_inicio DATE, periodo_fim DATE, tamanho LONG, "
               "sha256 STRING, linhas LONG, carregado_em TIMESTAMP")
    atualizados = spark.createDataFrame(novos_controles, esquema)
    if spark.catalog.tableExists("controle_arquivos"):
        urls = [r[0] for r in novos_controles]
        manter = spark.table("controle_arquivos").where(~F.col("url").isin(urls))
        atualizados = manter.unionByName(atualizados)
    atualizados.write.format("delta").mode("overwrite").saveAsTable("controle_arquivos_tmp")
    spark.sql("CREATE OR REPLACE TABLE controle_arquivos AS SELECT * FROM controle_arquivos_tmp")
    spark.sql("DROP TABLE controle_arquivos_tmp")

# %%
# O SQL endpoint do lakehouse demora a enxergar tabelas recém-gravadas; sem isso o Warehouse leria dados velhos.
from sempy.fabric import FabricRestClient

cliente = FabricRestClient()
ws = notebookutils.runtime.context["currentWorkspaceId"]  # noqa: F821
lakehouse = next(l for l in cliente.get(f"v1/workspaces/{ws}/lakehouses").json()["value"]
                 if l["displayName"] == "lh_combustiveis")
endpoint = cliente.get(f"v1/workspaces/{ws}/lakehouses/{lakehouse['id']}").json()["properties"]["sqlEndpointProperties"]["id"]
resposta = cliente.post(f"v1/workspaces/{ws}/sqlEndpoints/{endpoint}/refreshMetadata", json={})
print("refresh do SQL endpoint:", resposta.status_code)

# %%
resumo = (spark.table("bronze_revenda").groupBy("arquivo_lote")
          .agg(F.count("*").alias("linhas"), F.sum(F.when(F.col("uf") == "RS", 1).otherwise(0)).alias("linhas_rs"))
          .orderBy("arquivo_lote"))
for r in resumo.collect():
    print(f"{r.arquivo_lote:<60} {r.linhas:>10,} {r.linhas_rs:>8,} RS")
