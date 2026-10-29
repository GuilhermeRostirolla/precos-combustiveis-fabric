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
from decimal import Decimal

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
        df = pd.DataFrame.from_records([tuple(linha) for linha in cursor.fetchall()], columns=colunas)
    # decimal do SQL chega como decimal.Decimal; as contas daqui são em float
    for coluna in colunas:
        if df[coluna].map(lambda v: isinstance(v, Decimal)).any():
            df[coluna] = df[coluna].astype(float)
    return df


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
# 2. Reajustes na refinaria (região Sul), com a mesma regra do T-SQL: mediana de 3 semanas, semanas seguidas no
#    mesmo sentido viram um reajuste só, e cada reajuste é acompanhado até o seguinte.
p = spark.table("bronze_produtor").where((F.col("regiao") == "Sul") & F.col("preco").isNotNull()
                                         & (F.col("preco") > 0)).toPandas()
p = p.rename(columns={"produto": "produto_produtor"}).merge(produtos, on="produto_produtor")
p["semana"] = pd.to_datetime(p["semana_inicio"])
p = p.drop_duplicates(["produto", "semana"]).sort_values(["produto", "semana"])
mistura["vigente_de"] = pd.to_datetime(mistura["vigente_de"])
mistura["vigente_ate"] = pd.to_datetime(mistura["vigente_ate"])
p = p.merge(mistura, on="produto")
p = p[(p["semana"] >= p["vigente_de"]) & (p["semana"] <= p["vigente_ate"])].sort_values(["produto", "semana"]).copy()
p["preco"] = p["preco"].round(4)
vizinhos = pd.concat([p.groupby("produto")["preco"].shift(1), p["preco"], p.groupby("produto")["preco"].shift(-1)],
                     axis=1)
p["suave"] = np.where(vizinhos.isna().any(axis=1), p["preco"], vizinhos.median(axis=1))
p["anterior"] = p.groupby("produto")["suave"].shift()
p["distancia"] = (p["semana"] - p.groupby("produto")["semana"].shift()).dt.days
p["sinal"] = np.where(p["suave"] > p["anterior"], 1, -1)
cand = p[(p["distancia"] == 7) & ((p["suave"] / p["anterior"] - 1).abs() >= parametros["limiar_reajuste"])].copy()
cand["grupo"] = ((cand["semana"] - pd.Timestamp("1900-01-01")).dt.days // 7
                 - cand.groupby(["produto", "sinal"]).cumcount() - 1)
sequencias = cand.groupby(["produto", "sinal", "grupo"]).agg(inicio=("semana", "min"), fim=("semana", "max"))
suave = p.set_index(["produto", "semana"])
inicio_bomba = pd.Timestamp(sql("SELECT MIN(semana) AS s FROM gold.fato_preco_uf_semana WHERE uf = 'RS'")["s"].iloc[0])
horizonte = int(parametros["horizonte_semanas"])
eventos = []
for (produto, sinal, _), s in sequencias.iterrows():
    chave_antes, chave_depois = (produto, s.inicio - pd.Timedelta(days=7)), (produto, s.fim + pd.Timedelta(days=7))
    if chave_antes not in suave.index or chave_depois not in suave.index:
        continue
    antes, depois = suave.loc[chave_antes, "suave"], suave.loc[chave_depois, "suave"]
    if (s.inicio < inicio_bomba + pd.Timedelta(days=7) or np.sign(depois - antes) != sinal
            or abs(depois / antes - 1) < parametros["limiar_reajuste"]):
        continue
    eventos.append({"produto": produto, "semana_evento": s.inicio,
                    "esperado": round((depois - antes) * suave.loc[chave_depois, "fracao_fossil"], 4)})
eventos = pd.DataFrame(eventos).sort_values(["produto", "semana_evento"])
eventos["proximo"] = eventos.groupby("produto")["semana_evento"].shift(-1)
eventos["acompanhadas"] = [horizonte if pd.isna(e.proximo) else min(horizonte, (e.proximo - e.semana_evento).days // 7 - 1)
                           for e in eventos.itertuples()]

eventos_wh = sql("SELECT produto, semana_evento, CAST(repasse_esperado AS float) AS esperado_wh, "
                 "semanas_acompanhadas AS acompanhadas_wh FROM gold.repasse_evento")
eventos_wh["semana_evento"] = pd.to_datetime(eventos_wh["semana_evento"])
ev = eventos.merge(eventos_wh, on=["produto", "semana_evento"], how="outer", indicator=True)
eventos_divergentes = int((ev["_merge"] != "both").sum())
diferenca_eventos = float((ev["esperado"] - ev["esperado_wh"]).abs().max())
acompanhadas_divergentes = int((ev.dropna(subset=["acompanhadas", "acompanhadas_wh"])
                          .pipe(lambda d: d["acompanhadas"] != d["acompanhadas_wh"])).sum())
print(f"reajustes: {len(eventos)} em Python, {len(eventos_wh)} no warehouse, {eventos_divergentes} divergentes, "
      f"maior diferença no repasse esperado {diferenca_eventos:.6f}, "
      f"{acompanhadas_divergentes} com semanas acompanhadas diferentes")

# %%
# 3. Curva de repasse do estado.
serie = media_py.set_index(["produto", "semana"])["py"]
curva = []
for e in eventos.itertuples():
    base = serie.get((e.produto, e.semana_evento - pd.Timedelta(days=7)))
    if base is None:
        continue
    for h in range(int(e.acompanhadas) + 1):
        valor = serie.get((e.produto, e.semana_evento + pd.Timedelta(days=7 * h)))
        if valor is not None:
            curva.append({"produto": e.produto, "semana_evento": e.semana_evento, "h": h,
                          "repasse_py": (round(valor, 4) - round(base, 4)) / e.esperado})
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
if eventos_divergentes or diferenca_eventos > TOLERANCIA or acompanhadas_divergentes:
    problemas.append(f"reajustes ({eventos_divergentes} divergentes, {acompanhadas_divergentes} com semanas acompanhadas diferentes)")
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

# %%
# Saída do notebook: o pipeline guarda este resumo no histórico da execução.
import json

cobertura = sql("""
SELECT (SELECT CAST(MIN(semana) AS varchar(10)) FROM gold.fato_preco_uf_semana WHERE uf = 'RS') AS primeira_semana_rs,
       (SELECT CAST(MAX(semana) AS varchar(10)) FROM gold.fato_preco_uf_semana WHERE uf = 'RS') AS ultima_semana_rs,
       (SELECT CAST(MAX(semana) AS varchar(10)) FROM gold.fato_preco_produtor_semana) AS ultima_semana_refinaria,
       (SELECT COUNT(DISTINCT cnpj) FROM silver.preco_revenda WHERE uf = 'RS') AS postos_rs,
       (SELECT COUNT(*) FROM silver.preco_revenda WHERE uf = 'RS') AS coletas_rs,
       (SELECT COUNT(*) FROM silver.preco_revenda) AS coletas_brasil,
       (SELECT COUNT(*) FROM silver.preco_revenda_quarentena) AS quarentena,
       (SELECT COUNT(DISTINCT municipio) FROM gold.fato_preco_municipio_semana
        WHERE uf = 'RS' AND amostra_suficiente = 1) AS municipios_rs_com_amostra""")
eventos_lista = sql("""
SELECT produto, CAST(semana_evento AS varchar(10)) AS semana, direcao, semanas_reajuste,
       CAST(variacao_refinaria AS float) AS refinaria, CAST(variacao_refinaria_pct AS float) AS refinaria_pct,
       CAST(repasse_esperado AS float) AS esperado, semanas_acompanhadas
FROM gold.repasse_evento ORDER BY produto, semana_evento""")
municipios = sql("""
SELECT produto, escopo, direcao, eventos, CAST(semanas_mediana_ate_50 AS float) AS ate_50,
       CAST(semanas_mediana_ate_80 AS float) AS ate_80
FROM gold.repasse_velocidade WHERE escopo <> 'RS (estado)'""")
notebookutils.notebook.exit(json.dumps({  # noqa: F821
    "conferencia": "ok", "cobertura": cobertura.to_dict(orient="records")[0],
    "resumo": resumo.to_dict(orient="records"), "velocidade": velocidade.to_dict(orient="records"),
    "eventos": eventos_lista.to_dict(orient="records"), "municipios": municipios.to_dict(orient="records"),
}, default=str, ensure_ascii=False))
