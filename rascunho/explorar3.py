import io, re, requests, pandas as pd
H = {"User-Agent": "Mozilla/5.0"}
p = requests.get("https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis", headers=H, timeout=60)
links = sorted(set(re.findall(r'href="([^"]+?\.(?:csv|zip))"', p.text)))
rel = [l.split("/arquivos/shpc/")[-1] for l in links if ("gasolina" in l or "diesel" in l or "/ca" in l or "dsan" in l)]
print("N", len(rel))
print(" | ".join(rel[-60:]))
r = requests.get("https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2023/precos-gasolina-etanol-01.csv", headers=H, timeout=120)
df = pd.read_csv(io.StringIO(r.content.decode("latin-1")), sep=";", dtype=str)
print("COLS", df.columns.tolist())
print("PROD", df["Produto"].value_counts().to_dict())
print("UNID", df["Unidade de Medida"].value_counts().to_dict(), "EX_VALOR", df["Valor de Venda"].head(3).tolist(), "EX_DATA", df["Data da Coleta"].head(3).tolist())
rs = df[df["Estado - Sigla"] == "RS"]
print("RS", len(rs), "CIDADES", rs["Municipio"].nunique(), "DATAS", sorted(rs["Data da Coleta"].unique())[:12])
x = requests.get("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/ppidp/precos-medios-ponderados-semanais-2013.xls", headers=H, timeout=180)
t = pd.read_excel(io.BytesIO(x.content), header=None)
print("XLS_ROW8", t.iloc[8].tolist())
print("XLS_ROW9", t.iloc[9].tolist())
prods = t.iloc[9:, 0].dropna().astype(str)
print("XLS_PRODS", prods[~prods.str.contains("partir|prática|estimativa|Fonte|Nota", case=False)].unique().tolist())
g = t[t[0].astype(str).str.startswith("Gasolina A")]
print("GASA_ULTIMAS", g.tail(4).iloc[:, [0, 1, 2, 7, 9]].values.tolist())
d = t[t[0].astype(str).str.contains("Diesel S10", na=False)]
print("S10_ULTIMAS", d.tail(2).iloc[:, [0, 1, 2, 7, 9]].values.tolist())
