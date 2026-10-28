-- Regras de qualidade: cada regra conta violações. Severidade 'erro' interrompe o pipeline; 'aviso' só registra.

IF OBJECT_ID('qualidade.resultado') IS NULL
    CREATE TABLE qualidade.resultado (
        execucao varchar(60) NOT NULL,
        executado_em datetime2(6) NOT NULL,
        regra varchar(60) NOT NULL,
        severidade varchar(10) NOT NULL,
        violacoes bigint NOT NULL,
        aprovado bit NOT NULL
    );
GO

CREATE OR ALTER PROCEDURE qualidade.sp_verificar @execucao varchar(60) = 'manual'
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @agora datetime2(6) = SYSUTCDATETIME();
    DROP TABLE IF EXISTS #r;
    CREATE TABLE #r (regra varchar(60), severidade varchar(10), violacoes bigint);

    -- Reconciliação: tudo o que entrou na bronze (produtos no escopo) está na silver, na quarentena ou é duplicata.
    INSERT INTO #r SELECT 'reconciliacao_bronze_silver', 'erro',
        ABS((SELECT COUNT(*) FROM lh_combustiveis.dbo.bronze_revenda
             WHERE produto IN ('GASOLINA', 'GASOLINA ADITIVADA', 'ETANOL', 'DIESEL', 'DIESEL S10'))
            - (SELECT COUNT(*) FROM silver.preco_revenda)
            - (SELECT COUNT(*) FROM silver.preco_revenda_quarentena)
            - (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(cnpj, '|', produto, '|', data_coleta)) FROM (
                   SELECT cnpj, produto, TRY_CONVERT(date, data_coleta, 103) AS data_coleta
                   FROM lh_combustiveis.dbo.bronze_revenda
                   WHERE produto IN ('GASOLINA', 'GASOLINA ADITIVADA', 'ETANOL', 'DIESEL', 'DIESEL S10')
                     AND TRY_CONVERT(date, data_coleta, 103) IS NOT NULL
                     AND TRY_CONVERT(date, data_coleta, 103) <= CAST(GETDATE() AS date)
                     AND TRY_CAST(REPLACE(valor_venda, ',', '.') AS decimal(8,3)) BETWEEN
                         (SELECT valor FROM config.parametro WHERE nome = 'preco_minimo') AND
                         (SELECT valor FROM config.parametro WHERE nome = 'preco_maximo')
                     AND unidade LIKE 'R$%litro' AND LEN(uf) = 2 AND municipio <> '' AND cnpj <> '') AS v));

    INSERT INTO #r SELECT 'silver_chave_duplicada', 'erro', COUNT(*) FROM (
        SELECT cnpj, produto, data_coleta FROM silver.preco_revenda
        GROUP BY cnpj, produto, data_coleta HAVING COUNT(*) > 1) AS d;

    INSERT INTO #r SELECT 'gold_municipio_semana_duplicada', 'erro', COUNT(*) FROM (
        SELECT semana, uf, municipio, produto FROM gold.fato_preco_municipio_semana
        GROUP BY semana, uf, municipio, produto HAVING COUNT(*) > 1) AS d;

    INSERT INTO #r SELECT 'produtor_semana_duplicada', 'erro', COUNT(*) FROM (
        SELECT semana, produto, regiao FROM gold.fato_preco_produtor_semana
        GROUP BY semana, produto, regiao HAVING COUNT(*) > 1) AS d;

    INSERT INTO #r SELECT 'produtor_sem_mistura_configurada', 'erro',
        (SELECT COUNT(*) FROM silver.preco_produtor AS p JOIN config.produto AS c ON c.produto_produtor = p.produto_produtor)
        - (SELECT COUNT(*) FROM gold.fato_preco_produtor_semana);

    -- Buracos na série semanal da refinaria (região Sul) desde o início da série de postos.
    INSERT INTO #r SELECT 'refinaria_semana_faltando', 'aviso', COUNT(*) FROM (
        SELECT produto, semana, LAG(semana) OVER (PARTITION BY produto ORDER BY semana) AS anterior
        FROM gold.fato_preco_produtor_semana
        WHERE regiao = 'Sul' AND semana >= (SELECT MIN(semana) FROM gold.fato_preco_uf_semana)) AS s
    WHERE anterior IS NOT NULL AND DATEDIFF(day, anterior, semana) > 7;

    INSERT INTO #r SELECT 'media_rs_fora_da_faixa', 'erro', COUNT(*)
    FROM gold.fato_preco_uf_semana
    WHERE uf = 'RS' AND produto IN ('GASOLINA', 'DIESEL S10') AND (preco_medio < 3 OR preco_medio > 10);

    INSERT INTO #r SELECT 'rs_semana_com_poucos_postos', 'aviso', COUNT(*)
    FROM gold.fato_preco_uf_semana
    WHERE uf = 'RS' AND produto = 'GASOLINA' AND postos < 50;

    INSERT INTO #r SELECT 'refinaria_desatualizada', 'aviso',
        CASE WHEN (SELECT MAX(semana) FROM gold.fato_preco_produtor_semana) < DATEADD(day, -28, GETDATE()) THEN 1 ELSE 0 END;

    INSERT INTO #r SELECT 'postos_desatualizados', 'aviso',
        CASE WHEN (SELECT MAX(data_coleta) FROM silver.preco_revenda) < DATEADD(day, -75, GETDATE()) THEN 1 ELSE 0 END;

    INSERT INTO #r SELECT 'sem_reajustes_isolados', 'erro',
        CASE WHEN (SELECT COUNT(*) FROM gold.repasse_evento WHERE isolado = 1) = 0 THEN 1 ELSE 0 END;

    INSERT INTO #r SELECT 'curva_sem_semana_zero', 'erro', COUNT(*)
    FROM gold.repasse_evento AS e
    WHERE e.isolado = 1
      AND NOT EXISTS (SELECT 1 FROM gold.repasse_curva AS c
                      WHERE c.produto = e.produto AND c.semana_evento = e.semana_evento
                        AND c.escopo = 'RS (estado)' AND c.h = 0)
      AND e.semana_evento > (SELECT MIN(semana) FROM gold.fato_preco_uf_semana);

    INSERT INTO qualidade.resultado
    SELECT @execucao, @agora, regra, severidade, violacoes, CASE WHEN violacoes = 0 THEN 1 ELSE 0 END FROM #r;

    SELECT regra, severidade, violacoes FROM #r ORDER BY CASE WHEN violacoes = 0 THEN 1 ELSE 0 END, severidade, regra;

    IF EXISTS (SELECT 1 FROM #r WHERE severidade = 'erro' AND violacoes > 0)
    BEGIN
        DECLARE @falhas varchar(4000) = (SELECT STRING_AGG(CONCAT(regra, ' (', violacoes, ')'), ', ')
                                          FROM #r WHERE severidade = 'erro' AND violacoes > 0);
        DECLARE @mensagem varchar(4000) = CONCAT('Regras de qualidade com erro: ', @falhas);
        THROW 50001, @mensagem, 1;
    END
END;
GO
