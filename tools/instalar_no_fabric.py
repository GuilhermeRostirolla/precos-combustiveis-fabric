"""Instala ou atualiza o projeto num workspace do Fabric. Rodar numa célula de notebook do workspace:

    import requests
    COMMIT = "<sha-completo-do-commit-revisado>"
    exec(requests.get(f"https://raw.githubusercontent.com/GuilhermeRostirolla/precos-combustiveis-fabric/{COMMIT}/tools/instalar_no_fabric.py").text)

Cria (ou atualiza, se já existirem) o lakehouse, o warehouse, os notebooks, os objetos SQL e o pipeline.
Com EXECUTAR = True, roda o pipeline no fim e mostra o resultado de cada atividade.
"""
import base64
import json
import re
import struct
import time

import requests
from sempy.fabric import FabricRestClient

REPOSITORIO = globals().get("REPOSITORIO", "GuilhermeRostirolla/precos-combustiveis-fabric")
COMMIT = globals().get("COMMIT", "main")
EXECUTAR = globals().get("EXECUTAR", False)
LAKEHOUSE = "lh_combustiveis"
WAREHOUSE = "wh_combustiveis"
PIPELINE = "pl_combustiveis_semanal"
NOTEBOOKS = ["nb_01_ingestao", "nb_02_conferencia"]
SCRIPTS_SQL = ["01_esquemas_config.sql", "02_silver.sql", "03_gold.sql", "04_analise_repasse.sql", "05_qualidade.sql"]

if not re.fullmatch(r"[0-9a-f]{40}", COMMIT):
    COMMIT = requests.get(f"https://api.github.com/repos/{REPOSITORIO}/commits/{COMMIT}", timeout=60).json()["sha"]
print(f"instalando {REPOSITORIO} no commit {COMMIT[:7]}")

_cliente = FabricRestClient()
_ws = notebookutils.runtime.context["currentWorkspaceId"]  # noqa: F821 (existe no Fabric)


def _arquivo(caminho: str) -> str:
    resposta = requests.get(f"https://raw.githubusercontent.com/{REPOSITORIO}/{COMMIT}/{caminho}", timeout=60)
    resposta.raise_for_status()
    return resposta.text


def _esperar(resposta, o_que):
    if resposta.status_code not in (200, 201, 202):
        raise RuntimeError(f"{o_que}: HTTP {resposta.status_code} {resposta.text[:500]}")
    if resposta.status_code != 202:
        return resposta
    operacao = resposta.headers["x-ms-operation-id"]
    for _ in range(120):
        time.sleep(int(resposta.headers.get("Retry-After", 3)))
        estado = _cliente.get(f"v1/operations/{operacao}").json()
        if estado["status"] == "Succeeded":
            return resposta
        if estado["status"] == "Failed":
            raise RuntimeError(f"{o_que} falhou: {estado.get('error')}")
    raise TimeoutError(o_que)


def _itens(tipo):
    return {i["displayName"]: i for i in _cliente.get(f"v1/workspaces/{_ws}/items?type={tipo}").json()["value"]}


def _garantir(tipo, rota, nome, descricao):
    if nome not in _itens(tipo):
        _esperar(_cliente.post(f"v1/workspaces/{_ws}/{rota}", json={"displayName": nome, "description": descricao}),
                 f"criar {nome}")
        print(f"criado      {nome}")
        time.sleep(10)
    return _itens(tipo)[nome]["id"]


_lakehouse = _garantir("Lakehouse", "lakehouses", LAKEHOUSE, "Dados brutos da ANP (bronze)")
_warehouse = _garantir("Warehouse", "warehouses", WAREHOUSE, "Modelo silver/gold e análise do repasse")

# --- notebooks: o fonte fica em fabric/notebooks/*.py com células separadas por "# %%" ---------------------------
_ANP = _arquivo("src/anp.py")


def _para_ipynb(fonte: str) -> dict:
    celulas = []
    for bloco in re.split(r"^# %%", fonte, flags=re.M)[1:]:
        cabecalho, _, corpo = bloco.partition("\n")
        corpo = corpo.strip("\n")
        if "[markdown]" in cabecalho:
            texto = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") for l in corpo.splitlines())
            celulas.append({"cell_type": "markdown", "metadata": {}, "source": texto})
            continue
        corpo = corpo.replace("# <<ANP>>  (o instalador substitui esta linha pelo conteúdo de src/anp.py)", _ANP.strip())
        metadados = {"tags": ["parameters"]} if "parameters" in cabecalho else {}
        celulas.append({"cell_type": "code", "metadata": metadados, "source": corpo,
                        "execution_count": None, "outputs": []})
    return {"nbformat": 4, "nbformat_minor": 5, "cells": celulas, "metadata": {
        "kernel_info": {"name": "synapse_pyspark"},
        "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
        "language_info": {"name": "python"},
        "dependencies": {"lakehouse": {"default_lakehouse": _lakehouse, "default_lakehouse_name": LAKEHOUSE,
                                       "default_lakehouse_workspace_id": _ws,
                                       "known_lakehouses": [{"id": _lakehouse}]}}}}


_existentes = _itens("Notebook")
_ids_notebooks = {}
for _nome in NOTEBOOKS:
    _nb = _para_ipynb(_arquivo(f"fabric/notebooks/{_nome}.py"))
    _definicao = {"format": "ipynb", "parts": [{
        "path": "notebook-content.ipynb", "payloadType": "InlineBase64",
        "payload": base64.b64encode(json.dumps(_nb, ensure_ascii=False).encode("utf-8")).decode()}]}
    if _nome in _existentes:
        _esperar(_cliente.post(f"v1/workspaces/{_ws}/notebooks/{_existentes[_nome]['id']}/updateDefinition",
                               json={"definition": _definicao}), f"atualizar {_nome}")
        print(f"atualizado  {_nome}")
    else:
        _esperar(_cliente.post(f"v1/workspaces/{_ws}/notebooks", json={"displayName": _nome, "definition": _definicao}),
                 f"criar {_nome}")
        print(f"criado      {_nome}")
_ids_notebooks = {n: i["id"] for n, i in _itens("Notebook").items()}

# --- SQL no warehouse ---------------------------------------------------------------------------------------------
import pyodbc  # noqa: E402

_servidor = _cliente.get(f"v1/workspaces/{_ws}/warehouses/{_warehouse}").json()["properties"]["connectionString"]


def conectar_warehouse():
    token = notebookutils.credentials.getToken("https://database.windows.net/").encode("utf-16-le")  # noqa: F821
    estrutura = struct.pack(f"<I{len(token)}s", len(token), token)
    return pyodbc.connect(f"Driver={{ODBC Driver 18 for SQL Server}};Server={_servidor},1433;Database={WAREHOUSE};"
                          "Encrypt=yes;TrustServerCertificate=no", attrs_before={1256: estrutura}, autocommit=True)


with conectar_warehouse() as _conexao:
    for _script in SCRIPTS_SQL:
        _lotes = [l for l in re.split(r"^\s*GO\s*$", _arquivo(f"fabric/sql/{_script}"), flags=re.M | re.I) if l.strip()]
        for _lote in _lotes:
            _conexao.execute(_lote)
        print(f"sql         {_script} ({len(_lotes)} lotes)")

# --- pipeline -----------------------------------------------------------------------------------------------------
_politica = {"timeout": "0.02:00:00", "retry": 1, "retryIntervalInSeconds": 120, "secureOutput": False, "secureInput": False}
_servico_warehouse = {"name": WAREHOUSE, "properties": {"annotations": [], "type": "DataWarehouse", "typeProperties": {
    "endpoint": _servidor, "artifactId": _warehouse, "workspaceId": _ws}}}


def _depois(atividade):
    return [{"activity": atividade, "dependencyConditions": ["Succeeded"]}]


def _procedure(nome, procedure, depois_de, parametros=None):
    atividade = {"name": nome, "type": "SqlServerStoredProcedure", "dependsOn": _depois(depois_de),
                 "policy": _politica, "typeProperties": {"storedProcedureName": procedure},
                 "linkedService": _servico_warehouse}
    if parametros:
        atividade["typeProperties"]["storedProcedureParameters"] = parametros
    return atividade


_pipeline = {"properties": {"description": "Carga semanal: ANP -> lakehouse -> warehouse -> análise -> qualidade -> conferência",
                            "activities": [
    {"name": "Ingestao ANP", "type": "TridentNotebook", "dependsOn": [], "policy": _politica,
     "typeProperties": {"notebookId": _ids_notebooks["nb_01_ingestao"], "workspaceId": _ws}},
    _procedure("Silver", "[silver].[sp_carregar]", "Ingestao ANP"),
    _procedure("Gold", "[gold].[sp_carregar]", "Silver"),
    _procedure("Analise do repasse", "[gold].[sp_analise_repasse]", "Gold"),
    _procedure("Qualidade", "[qualidade].[sp_verificar]", "Analise do repasse",
               {"execucao": {"value": {"value": "@pipeline().RunId", "type": "Expression"}, "type": "String"}}),
    {"name": "Conferencia", "type": "TridentNotebook", "dependsOn": _depois("Qualidade"), "policy": _politica,
     "typeProperties": {"notebookId": _ids_notebooks["nb_02_conferencia"], "workspaceId": _ws}},
]}}
_definicao_pipeline = {"parts": [{"path": "pipeline-content.json", "payloadType": "InlineBase64",
                                  "payload": base64.b64encode(json.dumps(_pipeline).encode("utf-8")).decode()}]}
_pipelines = _itens("DataPipeline")
if PIPELINE in _pipelines:
    _id_pipeline = _pipelines[PIPELINE]["id"]
    _esperar(_cliente.post(f"v1/workspaces/{_ws}/dataPipelines/{_id_pipeline}/updateDefinition",
                           json={"definition": _definicao_pipeline}), "atualizar pipeline")
    print(f"atualizado  {PIPELINE}")
else:
    _esperar(_cliente.post(f"v1/workspaces/{_ws}/dataPipelines",
                           json={"displayName": PIPELINE, "definition": _definicao_pipeline}), "criar pipeline")
    _id_pipeline = _itens("DataPipeline")[PIPELINE]["id"]
    print(f"criado      {PIPELINE}")

# Agenda semanal: quartas às 8h (a ANP atualiza a planilha de produtores com cerca de 12 dias de atraso).
_agendas = _cliente.get(f"v1/workspaces/{_ws}/items/{_id_pipeline}/jobs/Pipeline/schedules").json().get("value", [])
if not _agendas:
    _resposta = _cliente.post(f"v1/workspaces/{_ws}/items/{_id_pipeline}/jobs/Pipeline/schedules", json={
        "enabled": True, "configuration": {
            "type": "Weekly", "weekdays": ["Wednesday"], "times": ["08:00"],
            "startDateTime": "2026-10-28T00:00:00", "endDateTime": "2027-12-31T23:59:00",
            "localTimeZoneId": "E. South America Standard Time"}})
    print("agenda      quartas 08:00 (Brasília):", _resposta.status_code)

print("\ninstalação concluída")

if EXECUTAR:
    _resposta = _cliente.post(f"v1/workspaces/{_ws}/items/{_id_pipeline}/jobs/instances?jobType=Pipeline")
    _execucao = _resposta.headers["Location"].rstrip("/").split("/")[-1]
    print(f"pipeline em execução ({_execucao})")
    while True:
        time.sleep(30)
        _estado = _cliente.get(f"v1/workspaces/{_ws}/items/{_id_pipeline}/jobs/instances/{_execucao}").json()
        if _estado["status"] not in ("NotStarted", "InProgress"):
            break
    print("status:", _estado["status"], _estado.get("failureReason") or "")
    _atividades = _cliente.post(f"v1/workspaces/{_ws}/datapipelines/pipelineruns/{_execucao}/queryactivityruns",
                                json={"lastUpdatedAfter": "2026-01-01T00:00:00Z",
                                      "lastUpdatedBefore": "2099-01-01T00:00:00Z"})
    if _atividades.ok:
        for _a in sorted(_atividades.json().get("value", []), key=lambda a: a.get("activityRunStart") or ""):
            _erro = (_a.get("error") or {}).get("message", "")
            print(f"  {_a['activityName']:<22} {_a['status']:<10} {int(_a.get('durationInMs') or 0) // 1000:>5}s {_erro[:300]}")
