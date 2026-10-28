# %% [markdown]
# # nb_02 · Conferência
# Recalcula em Python, direto da bronze, os números que o Warehouse produziu em T-SQL e compara os dois:
#
# - preço médio semanal da gasolina e do diesel S10 no RS;
# - a lista de reajustes na refinaria (região Sul) e a variação de cada um;
# - a curva de repasse do estado, semana a semana.
#
# Se alguma diferença passar da tolerância, o notebook falha e o pipeline aparece como falho.
# No fim, mostra o resumo da análise.

# %%
import struct

import numpy as np
import pandas as pd
import pyodbc
from pyspark.sql import functions as F
from sempy.fabric import FabricRestClient

TOLERANCIA = 0.0006  # arredondamento de decimal(8,4) no warehouse
cliente = FabricRestClient()
ws = notebookutils.runtime.context["currentWorkspaceId"]  # noqa: F821
warehouse = next(w for w in cliente.get(f"v1/workspaces/{ws}/warehouses").json()["value"]
                 if w["displayName"] == "wh_combustiveis")
servidor = cliente.get(f"v1/workspaces/{ws}/warehouses/{warehouse['id']}").json()["properties"]["connectionString"]


def sql(consulta: str) -> pd.DataFrame:
    token = notebookutils.credentials.getToken("https://database.windows.net/").encode("utf-16-le")  # noqa: F821
    with pyodbc.connect(f"Driver={{ODBC Driver 18 for SQL Server}};Server={servidor},1433;Database=wh_combustiveis;"
                        "Encrypt=yes", attrs_before={1256: struct.pack(f"<I{len(token)}s", len(token), token)}) as c:
        cursor = c.execute(consulta)
        colunas = [d[0] for d in cursor.description]
        return pd.DataFrame.from_records(cursor.fetchall(), columns=colunas)


parametros = sql("SELECT nome, valor FROM config.parametro").set_index("nome")["valor"].astype(float)
mistura = sql("SELECT produto, vigente_de, vigente_ate, fracao_fossil FROM config.mistura")
produtos = sql("SELECT produto, produto_produtor FROM config.produto")

# %%
# 1. Preço médio semanal no RS, recalculado da bronze com as mesmas regras da silver.
b = (spark.table("bronze_revenda")
     .where((F.col("uf") == "RS") & F.col("produto").isin(list(produtos["produto"])))
     .select("cnpj", "produto", "data_coleta", "valor_venda", "unidade", "municipio", "arquivo_origem").toPandas())
b["data"] = pd.to_datetime(b["data_coleta"], format="%d/%m/%Y", errors="coerce")
b["valor"] = pd.to_numeric(b["valor_venda"].str.replace(",", "."), errors="coerce")
b = b[b["data"].notna() & (b["data"] <= pd.Timestamp.today()) & b["valor"].between(parametros["preco_minimo"],
      parametros["preco_maximo"]) & b["unidade"].str.match(r"R\$.*litro") & (b["municipio"] != "") & (b["cnpj"] != "")]
b = b.sort_values("arquivo_origem", ascending=False).drop_duplicates(["cnpj", "produto", "data"])
b["semana"] = b["data"] - pd.to_timedelta(b["data"].dt.weekday, unit="D")
media_py = b.groupby(["produto", "semana"])["valor"].mean().rename("py").reset_index()

media_wh = sql("SELECT produto, semana, CAST(preco_medio AS float) AS wh FROM gold.fato_preco_uf_semana WHERE uf = 'RS'")
media_wh["semana"] = pd.to_datetime(media_wh["semana"])
comparacao = media_py.merge(media_wh, on=["produto", "semana"], how="outer", indicator=True)
so_um_lado = int((comparacao["_merge"] != "both").sum())
diferenca = float((comparacao["py"] - comparacao["wh"]).abs().max())
print(f"média semanal RS: {len(comparacao)} semanas x produto, {so_um_lado} só de um lado, maior diferença {diferenca:.6f}")

# %%
# 2. Reajustes na refinaria (região Sul), com a mesma regra do T-SQL.
p = spark.table("bronze_produtor").where((F.col("regiao") == "Sul") & F.col("preco").isNotNull()).toPandas()
p = p.merge(produtos, left_on="produto", right_on="produto_produtor", suffixes=("_produtor", ""))
p["semana"] = pd.to_datetime(p["semana_inicio"])
p = p.drop_duplicates(["produto", "semana"]).sort_values(["produto", "semana"])
mistura["vigente_de"] = pd.to_datetime(mistura["vigente_de"])
mistura["vigente_ate"] = pd.to_datetime(mistura["vigente_ate"])
p = p.merge(mistura, on="produto")
p = p[(p["semana"] >= p["vigente_de"]) & (p["semana"] <= p["vigente_ate"])].copy()
p["preco"] = p["preco"].round(4)
p["anterior"] = p.groupby("produto")["preco"].shift()
p["semana_anterior"] = p.groupby("produto")["semana"].shift()
p["variacao"] = p["preco"] / p["anterior"] - 1
p["sinal"] = np.where(p["preco"] > p["anterior"], 1, -1)
cand = p[((p["semana"] - p["semana_anterior"]).dt.days == 7) & (p["variacao"].abs() >= parametros["limiar_reajuste"])]
chave = set(zip(cand["produto"], cand["semana"], cand["sinal"]))
precos = p.set_index(["produto", "semana"])["preco"]
eventos = []
for r in cand.itertuples():
    if (r.produto, r.semana - pd.Timedelta(days=7), r.sinal) in chave:
        continue
    antes = precos.get((r.produto, r.semana - pd.Timedelta(days=7)))
    depois = precos.get((r.produto, r.semana + pd.Timedelta(days=7)))
    if antes is None or depois is None or depois == antes or np.sign(depois - antes) != r.sinal:
        continue
    eventos.append({"produto": r.produto, "semana_evento": r.semana, "esperado": (depois - antes) * r.fracao_fossil})
eventos = pd.DataFrame(eventos)
janela = pd.Timedelta(days=7 * int(parametros["janela_isolamento"]))
eventos["isolado"] = [not ((eventos["produto"] == e.produto) & (eventos["semana_evento"] > e.semana_evento)
                           & (eventos["semana_evento"] <= e.semana_evento + janela)).any() for e in eventos.itertuples()]

eventos_wh = sql("SELECT produto, semana_evento, CAST(repasse_esperado AS float) AS esperado_wh, isolado AS isolado_wh "
                 "FROM gold.repasse_evento")
eventos_wh["semana_evento"] = pd.to_datetime(eventos_wh["semana_evento"])
ev = eventos.merge(eventos_wh, on=["produto", "semana_evento"], how="outer", indicator=True)
eventos_divergentes = int((ev["_merge"] != "both").sum())
diferenca_eventos = float((ev["esperado"] - ev["esperado_wh"]).abs().max())
isolado_divergente = int((ev.dropna(subset=["isolado", "isolado_wh"])
                          .pipe(lambda d: d["isolado"].astype(bool) != d["isolado_wh"].astype(bool))).sum())
print(f"reajustes: {len(eventos)} em Python, {len(eventos_wh)} no warehouse, {eventos_divergentes} divergentes, "
      f"maior diferença no repasse esperado {diferenca_eventos:.6f}, {isolado_divergente} com 'isolado' diferente")

# %%
# 3. Curva de repasse do estado.
serie = media_py.set_index(["produto", "semana"])["py"]
curva = []
for e in eventos.itertuples():
    base = serie.get((e.produto, e.semana_evento - pd.Timedelta(days=7)))
    if base is None:
        continue
    for h in range(int(parametros["horizonte_semanas"]) + 1):
        valor = serie.get((e.produto, e.semana_evento + pd.Timedelta(days=7 * h)))
        if valor is not None:
            curva.append({"produto": e.produto, "semana_evento": e.semana_evento, "h": h,
                          "repasse_py": (round(valor, 4) - round(base, 4)) / round(e.esperado, 4)})
curva = pd.DataFrame(curva)
curva_wh = sql("SELECT produto, semana_evento, h, CAST(repasse AS float) AS repasse_wh FROM gold.repasse_curva "
               "WHERE escopo = 'RS (estado)'")
curva_wh["semana_evento"] = pd.to_datetime(curva_wh["semana_evento"])
cc = curva.merge(curva_wh, on=["produto", "semana_evento", "h"], how="outer", indicator=True)
curva_divergente = int((cc["_merge"] != "both").sum())
diferenca_curva = float((cc["repasse_py"] - cc["repasse_wh"]).abs().max())
print(f"curva do estado: {len(cc)} pontos, {curva_divergente} só de um lado, maior diferença {diferenca_curva:.4f}")

# %%
problemas = []
if so_um_lado or diferenca > TOLERANCIA:
    problemas.append(f"média semanal (diferença {diferenca:.6f}, {so_um_lado} sem par)")
if eventos_divergentes or diferenca_eventos > TOLERANCIA or isolado_divergente:
    problemas.append(f"reajustes ({eventos_divergentes} divergentes, {isolado_divergente} isolado)")
if curva_divergente or diferenca_curva > 0.01:
    problemas.append(f"curva de repasse (diferença {diferenca_curva:.4f}, {curva_divergente} sem par)")
if problemas:
    raise AssertionError("Python e warehouse não batem: " + "; ".join(problemas))
print("conferência OK: Python e warehouse batem")

# %%
resumo = sql("""
SELECT produto, direcao, h, eventos, CAST(repasse_mediano AS float) AS mediano
FROM gold.repasse_resumo WHERE escopo = 'RS (estado)' AND h IN (0, 1, 2, 4, 8)
ORDER BY produto, direcao, h""")
print(resumo.pivot_table(index=["produto", "direcao"], columns="h", values="mediano").round(2).to_string())
velocidade = sql("""
SELECT produto, direcao, eventos, eventos_sem_80_no_horizonte AS sem_80,
       CAST(semanas_mediana_ate_50 AS float) AS ate_50, CAST(semanas_mediana_ate_80 AS float) AS ate_80
FROM gold.repasse_velocidade WHERE escopo = 'RS (estado)' ORDER BY produto, direcao""")
print(velocidade.to_string(index=False))
