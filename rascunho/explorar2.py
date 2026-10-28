import io, requests, pandas as pd
H = {"User-Agent": "Mozilla/5.0"}
root = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc"
achados = []
for ano in (2023, 2024, 2025, 2026):
    for mes in (1, 6, 9, 10, 12):
        for pasta in (f"dsan/{ano}", f"dsas/{ano}", "dsan", "dsas/ca"):
            u = f"{root}/{pasta}/precos-gasolina-etanol-{mes:02d}.csv"
            try:
                r = requests.head(u, headers=H, timeout=30, allow_redirects=True)
                if r.status_code == 200 and "csv" in (r.headers.get("content-type") or ""):
                    achados.append((ano, mes, pasta, r.headers.get("content-length")))
            except Exception as e:
                pass
print("ACHADOS", achados)
p = requests.get("https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis", headers=H, timeout=60)
import re
links = sorted(set(re.findall(r'href="([^"]+?\.(?:csv|zip))"', p.text)))
print("PAGINA", p.status_code, len(links))
for l in links[-40:]:
    print(l)
r = requests.get(f"{root}/dsan/2023/precos-gasolina-etanol-01.csv", headers=H, timeout=120)
txt = r.content.decode("latin-1")
print(txt[:600])
df = pd.read_csv(io.StringIO(txt), sep=";", dtype=str)
print(df.columns.tolist())
print(df["Produto"].value_counts().to_dict())
print(df[df["Estado - Sigla"] == "RS"]["Municipio"].value_counts().head(15).to_dict())
print(df["Data da Coleta"].min(), df["Data da Coleta"].max(), len(df))
x = requests.get("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/ppidp/precos-medios-ponderados-semanais-2013.xls", headers=H, timeout=180)
t = pd.read_excel(io.BytesIO(x.content), header=None, skiprows=9)
t.columns = ["produto", "inicio", "fim", "regiao_vazia", "norte", "nordeste", "centro_oeste", "sul", "sudeste", "brasil"]
print(t["produto"].dropna().unique().tolist()[:40])
g = t[t["produto"].astype(str).str.contains("Gasolina A", na=False)]
print(g.tail(8).to_string())
print(t.iloc[8:9].to_string())
