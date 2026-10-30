-- Silver: tipagem, validação e deduplicação das duas fontes que chegam pelo lakehouse.
-- Registro inválido não some: vai para a quarentena com o motivo.

DROP TABLE IF EXISTS silver.preco_revenda;
GO
CREATE TABLE silver.preco_revenda (
    data_coleta date NOT NULL,
    semana date NOT NULL,
    regiao varchar(2) NOT NULL,
    uf char(2) NOT NULL,
    municipio varchar(100) NOT NULL,
    cnpj varchar(20) NOT NULL,
    revenda varchar(200) NULL,
    bandeira varchar(100) NULL,
    produto varchar(40) NOT NULL,
    valor_venda decimal(8,3) NOT NULL,
    arquivo_origem varchar(200) NOT NULL
);
GO
DROP TABLE IF EXISTS silver.preco_revenda_quarentena;
GO
CREATE TABLE silver.preco_revenda_quarentena (
    uf varchar(10) NULL,
    municipio varchar(100) NULL,
    cnpj varchar(40) NULL,
    produto varchar(60) NULL,
    data_coleta_original varchar(40) NULL,
    valor_venda_original varchar(40) NULL,
    unidade varchar(40) NULL,
    arquivo_origem varchar(200) NULL,
    motivo varchar(40) NOT NULL
);
GO
DROP TABLE IF EXISTS silver.preco_produtor;
GO
CREATE TABLE silver.preco_produtor (
    semana date NOT NULL,
    semana_fim date NOT NULL,
    produto_produtor varchar(80) NOT NULL,
    regiao varchar(40) NOT NULL,
    preco decimal(10,4) NOT NULL
);
GO
DROP TABLE IF EXISTS silver.preco_uf_semanal;
GO
CREATE TABLE silver.preco_uf_semanal (
    semana date NOT NULL,
    uf char(2) NOT NULL,
    produto varchar(40) NOT NULL,
    preco_medio decimal(8,4) NOT NULL,
    postos int NOT NULL
);
GO

CREATE OR ALTER PROCEDURE silver.sp_carregar
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @minimo decimal(18,6) = (SELECT valor FROM config.parametro WHERE nome = 'preco_minimo');
    DECLARE @maximo decimal(18,6) = (SELECT valor FROM config.parametro WHERE nome = 'preco_maximo');

    -- Só os produtos líquidos vendidos por litro entram na silver; GNV (m³) fica de fora do escopo.
    DROP TABLE IF EXISTS #tipado;
    SELECT
        b.regiao, b.uf, b.municipio, b.cnpj, b.revenda, b.bandeira, b.produto, b.unidade, b.arquivo_origem,
        b.data_coleta AS data_coleta_original,
        b.valor_venda AS valor_venda_original,
        TRY_CONVERT(date, b.data_coleta, 103) AS data_coleta,
        TRY_CAST(REPLACE(b.valor_venda, ',', '.') AS decimal(8,3)) AS valor_venda
    INTO #tipado
    FROM lh_combustiveis.dbo.bronze_revenda AS b
    WHERE b.produto IN ('GASOLINA', 'GASOLINA ADITIVADA', 'ETANOL', 'DIESEL', 'DIESEL S10');

    TRUNCATE TABLE silver.preco_revenda_quarentena;
    INSERT INTO silver.preco_revenda_quarentena
    SELECT uf, municipio, cnpj, produto, data_coleta_original, valor_venda_original, unidade, arquivo_origem,
        CASE
            WHEN data_coleta IS NULL THEN 'data_invalida'
            WHEN data_coleta > CAST(GETDATE() AS date) THEN 'data_futura'
            WHEN valor_venda IS NULL THEN 'valor_invalido'
            WHEN valor_venda < @minimo OR valor_venda > @maximo THEN 'valor_fora_da_faixa'
            WHEN unidade NOT LIKE 'R$%litro' THEN 'unidade_inesperada'
            WHEN uf IS NULL OR LEN(uf) <> 2 OR municipio = '' OR cnpj = '' THEN 'chave_incompleta'
        END
    FROM #tipado
    WHERE data_coleta IS NULL
       OR data_coleta > CAST(GETDATE() AS date)
       OR valor_venda IS NULL
       OR valor_venda < @minimo OR valor_venda > @maximo
       OR unidade NOT LIKE 'R$%litro'
       OR uf IS NULL OR LEN(uf) <> 2 OR municipio = '' OR cnpj = '';

    -- O mesmo posto, produto e dia pode aparecer em dois arquivos; fica a versão do arquivo mais recente.
    TRUNCATE TABLE silver.preco_revenda;
    INSERT INTO silver.preco_revenda
    SELECT data_coleta,
           DATEADD(day, -(DATEDIFF(day, '19000101', data_coleta) % 7), data_coleta) AS semana,
           regiao, uf, municipio, cnpj, revenda, bandeira, produto, valor_venda, arquivo_origem
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY cnpj, produto, data_coleta ORDER BY arquivo_origem DESC) AS ordem
        FROM #tipado
        WHERE data_coleta IS NOT NULL
          AND data_coleta <= CAST(GETDATE() AS date)
          AND valor_venda BETWEEN @minimo AND @maximo
          AND unidade LIKE 'R$%litro'
          AND LEN(uf) = 2 AND municipio <> '' AND cnpj <> ''
    ) AS t
    WHERE ordem = 1;

    -- Produtores: semanas de segunda a domingo; '***' (sem comercialização) já chega nulo e é descartado.
    TRUNCATE TABLE silver.preco_produtor;
    INSERT INTO silver.preco_produtor
    SELECT DISTINCT
        CAST(p.semana_inicio AS date), CAST(p.semana_fim AS date), p.produto, p.regiao,
        CAST(p.preco AS decimal(10,4))
    FROM lh_combustiveis.dbo.bronze_produtor AS p
    WHERE p.preco IS NOT NULL AND p.preco > 0;

    -- Levantamento semanal por estado: a pesquisa vai de domingo a sábado; a semana do relatório começa na
    -- segunda seguinte ao domingo (cobre seis dos sete dias).
    TRUNCATE TABLE silver.preco_uf_semanal;
    INSERT INTO silver.preco_uf_semanal
    SELECT DISTINCT
        DATEADD(day, -(DATEDIFF(day, '19000101', DATEADD(day, 1, CAST(s.semana_inicio AS date))) % 7),
                DATEADD(day, 1, CAST(s.semana_inicio AS date))),
        s.uf, s.produto, CAST(s.preco_medio AS decimal(8,4)), s.postos
    FROM lh_combustiveis.dbo.bronze_revenda_semanal AS s
    WHERE s.preco_medio BETWEEN @minimo AND @maximo AND s.postos > 0;
END;
GO
