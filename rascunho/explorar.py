import io, subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "xlrd"], check=False)
import requests, pandas as pd
H = {"User-Agent": "Mozilla/5.0"}
base = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan"
for ano, mes, nome in [(2026, 9, "precos-gasolina-etanol"), (2026, 9, "precos-diesel-gnv"), (2026, 10, "precos-gasolina-etanol"), (2023, 1, "precos-gasolina-etanol"), (2022, 1, "precos-gasolina-etanol")]:
    u = f"{base}/{ano}/{nome}-{mes:02d}.csv"
    r = requests.get(u, headers=H, timeout=120)
    print(ano, mes, nome, r.status_code, len(r.content), r.headers.get("content-type"))
r = requests.get(f"{base}/2026/precos-gasolina-etanol-09.csv", headers=H, timeout=120)
print(r.content[:700].decode("latin-1"))
x = requests.get("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/ppidp/precos-medios-ponderados-semanais-2013.xls", headers=H, timeout=180)
print("xls", x.status_code, len(x.content))
xl = pd.ExcelFile(io.BytesIO(x.content))
print(xl.sheet_names)
for s in xl.sheet_names:
    full = xl.parse(s, header=None)
    print("=====", s, full.shape)
    print(full.iloc[:12, :10].to_string(max_colwidth=24))
    print(full.iloc[-3:, :10].to_string(max_colwidth=24))
