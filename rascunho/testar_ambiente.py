import json, requests
import notebookutils
ws = notebookutils.runtime.context.get("currentWorkspaceId")
print("WS", ws)
tok = notebookutils.credentials.getToken("pbi")
print("TOKEN", len(tok))
h = {"Authorization": f"Bearer {tok}"}
r = requests.get(f"https://api.fabric.microsoft.com/v1/workspaces/{ws}/items", headers=h, timeout=60)
print("ITEMS", r.status_code, [(i["type"], i["displayName"]) for i in r.json().get("value", [])])
try:
    import pyodbc
    print("PYODBC", pyodbc.version, pyodbc.drivers())
except Exception as e:
    print("PYODBC_ERRO", repr(e))
import sys, platform
print("PY", sys.version.split()[0], platform.platform())
try:
    import pandas, pyarrow
    print("PANDAS", pandas.__version__, "ARROW", pyarrow.__version__)
except Exception as e:
    print("PKG_ERRO", e)
print("SPARK", spark.version)
