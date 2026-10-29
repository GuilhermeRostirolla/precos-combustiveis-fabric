-- Gold: modelo estrela semanal para o relatório e para a análise de repasse.

CREATE OR ALTER PROCEDURE gold.sp_carregar
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @postos_minimos int = (SELECT CAST(valor AS int) FROM config.parametro WHERE nome = 'postos_minimos');

    -- Postos distintos na semana (COUNT DISTINCT não funciona em janela).
    DROP TABLE IF EXISTS #postos;
    SELECT semana, uf, municipio, produto, COUNT(DISTINCT cnpj) AS postos
    INTO #postos
    FROM silver.preco_revenda
    GROUP BY semana, uf, municipio, produto;

    -- Preço médio, mediano e faixa por município, produto e semana (segunda a domingo).
    DROP TABLE IF EXISTS gold.fato_preco_municipio_semana;
    CREATE TABLE gold.fato_preco_municipio_semana AS
    SELECT f.semana, f.uf, f.municipio, f.produto, f.preco_medio, f.preco_mediano, f.preco_minimo, f.preco_maximo,
           f.coletas, p.postos,
           CAST(CASE WHEN p.postos >= @postos_minimos THEN 1 ELSE 0 END AS bit) AS amostra_suficiente
    FROM (
        SELECT DISTINCT
            semana, uf, municipio, produto,
            CAST(AVG(valor_venda) OVER (PARTITION BY semana, uf, municipio, produto) AS decimal(8,4)) AS preco_medio,
            CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY valor_venda)
                 OVER (PARTITION BY semana, uf, municipio, produto) AS decimal(8,4)) AS preco_mediano,
            MIN(valor_venda) OVER (PARTITION BY semana, uf, municipio, produto) AS preco_minimo,
            MAX(valor_venda) OVER (PARTITION BY semana, uf, municipio, produto) AS preco_maximo,
            COUNT(*) OVER (PARTITION BY semana, uf, municipio, produto) AS coletas
        FROM silver.preco_revenda
    ) AS f
    JOIN #postos AS p
      ON p.semana = f.semana AND p.uf = f.uf AND p.municipio = f.municipio AND p.produto = f.produto;

    -- Média do estado: média simples dos postos pesquisados na semana.
    DROP TABLE IF EXISTS gold.fato_preco_uf_semana;
    CREATE TABLE gold.fato_preco_uf_semana AS
    SELECT semana, uf, produto,
           CAST(AVG(valor_venda) AS decimal(8,4)) AS preco_medio,
           COUNT(*) AS coletas,
           COUNT(DISTINCT cnpj) AS postos,
           COUNT(DISTINCT municipio) AS municipios
    FROM silver.preco_revenda
    GROUP BY semana, uf, produto;

    -- Refinaria (produtores e importadores) com a parcela fóssil que chega ao litro vendido no posto.
    DROP TABLE IF EXISTS gold.fato_preco_produtor_semana;
    CREATE TABLE gold.fato_preco_produtor_semana AS
    SELECT p.semana, p.semana_fim, c.produto, p.regiao, p.preco AS preco_produtor,
           m.fracao_fossil, m.mandato,
           CAST(p.preco * m.fracao_fossil AS decimal(10,4)) AS custo_fossil_por_litro
    FROM silver.preco_produtor AS p
    JOIN config.produto AS c ON c.produto_produtor = p.produto_produtor
    JOIN config.mistura AS m ON m.produto = c.produto AND p.semana BETWEEN m.vigente_de AND m.vigente_ate;

    -- Calendário semanal cobrindo as duas fontes.
    DECLARE @inicio date = (SELECT MIN(semana) FROM (SELECT semana FROM gold.fato_preco_uf_semana
                                                     UNION ALL SELECT semana FROM gold.fato_preco_produtor_semana) AS s);
    DECLARE @fim date = (SELECT MAX(semana) FROM (SELECT semana FROM gold.fato_preco_uf_semana
                                                  UNION ALL SELECT semana FROM gold.fato_preco_produtor_semana) AS s);
    DROP TABLE IF EXISTS gold.dim_semana;
    CREATE TABLE gold.dim_semana AS
    SELECT semana,
           DATEADD(day, 6, semana) AS semana_fim,
           YEAR(semana) AS ano,
           MONTH(semana) AS mes,
           CONCAT(YEAR(semana), '-', RIGHT(CONCAT('0', MONTH(semana)), 2)) AS ano_mes,
           CONCAT(RIGHT(CONCAT('0', DAY(semana)), 2), '/', RIGHT(CONCAT('0', MONTH(semana)), 2), '/', YEAR(semana)) AS rotulo
    FROM (
        SELECT DATEADD(day, 7 * n, @inicio) AS semana
        FROM (SELECT a.d + 10 * b.d + 100 * c.d AS n
              FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) AS a(d)
              CROSS JOIN (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) AS b(d)
              CROSS JOIN (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) AS c(d)) AS numeros
        WHERE n <= DATEDIFF(day, @inicio, @fim) / 7
    ) AS semanas;

    DROP TABLE IF EXISTS gold.dim_municipio;
    CREATE TABLE gold.dim_municipio AS
    SELECT DISTINCT uf, municipio, CONCAT(municipio, ' (', uf, ')') AS municipio_uf
    FROM silver.preco_revenda;

    DROP TABLE IF EXISTS gold.dim_produto;
    CREATE TABLE gold.dim_produto AS
    SELECT DISTINCT r.produto,
           CASE WHEN c.produto IS NULL THEN CAST(0 AS bit) ELSE CAST(1 AS bit) END AS tem_preco_refinaria
    FROM silver.preco_revenda AS r
    LEFT JOIN config.produto AS c ON c.produto = r.produto;

    -- Do que é feito o preço no posto, semana a semana, por estado e para o Brasil (uf = 'BR').
    -- Mesmo método da Síntese Semanal da ANP: preço no posto = refinaria (parte fóssil, sem tributos)
    -- + tributos federais + ICMS + o restante (etanol anidro ou biodiesel, frete e margens).
    -- A série de produtores e importadores oscila quando muda a proporção de importadores; usa-se a
    -- mediana de três semanas, como na análise de repasse.
    DROP TABLE IF EXISTS #produtor;
    SELECT produto, regiao, semana, fracao_fossil, preco_produtor,
           LAG(preco_produtor) OVER (PARTITION BY produto, regiao ORDER BY semana) AS anterior,
           LEAD(preco_produtor) OVER (PARTITION BY produto, regiao ORDER BY semana) AS seguinte
    INTO #produtor
    FROM gold.fato_preco_produtor_semana;

    DROP TABLE IF EXISTS #produtor_suavizado;
    SELECT produto, regiao, semana, fracao_fossil,
           CASE WHEN anterior IS NULL OR seguinte IS NULL THEN preco_produtor
                ELSE preco_produtor + anterior + seguinte
                     - CASE WHEN preco_produtor >= anterior AND preco_produtor >= seguinte THEN preco_produtor
                            WHEN anterior >= seguinte THEN anterior ELSE seguinte END
                     - CASE WHEN preco_produtor <= anterior AND preco_produtor <= seguinte THEN preco_produtor
                            WHEN anterior <= seguinte THEN anterior ELSE seguinte END
           END AS preco_produtor
    INTO #produtor_suavizado
    FROM #produtor;

    -- Preço no posto por estado e a média do Brasil (média de todos os postos pesquisados).
    DROP TABLE IF EXISTS #posto;
    SELECT u.semana, u.uf, u.produto, u.preco_medio AS preco_posto, u.coletas
    INTO #posto
    FROM gold.fato_preco_uf_semana AS u
    JOIN config.produto AS c ON c.produto = u.produto
    UNION ALL
    SELECT u.semana, 'BR', u.produto,
           CAST(SUM(u.preco_medio * u.coletas) / SUM(u.coletas) AS decimal(8,4)), SUM(u.coletas)
    FROM gold.fato_preco_uf_semana AS u
    JOIN config.produto AS c ON c.produto = u.produto
    GROUP BY u.semana, u.produto;

    DROP TABLE IF EXISTS gold.composicao_preco_semana;
    CREATE TABLE gold.composicao_preco_semana AS
    SELECT x.semana, x.uf, x.produto, x.preco_posto, x.fracao_fossil,
           CAST(x.refinaria AS decimal(8,4)) AS refinaria,
           CAST(x.tributos_federais AS decimal(8,4)) AS tributos_federais,
           x.icms,
           CAST(x.preco_posto - x.refinaria - x.tributos_federais - x.icms AS decimal(8,4)) AS outros
    FROM (
        SELECT p.semana, p.uf, p.produto, p.preco_posto, s.fracao_fossil, t.icms,
               s.fracao_fossil * (s.preco_produtor - t.federal_fossil) AS refinaria,
               s.fracao_fossil * t.federal_fossil + (1 - s.fracao_fossil) * t.federal_bio AS tributos_federais
        FROM #posto AS p
        JOIN config.uf_regiao AS r ON r.uf = p.uf
        JOIN #produtor_suavizado AS s ON s.produto = p.produto AND s.regiao = r.regiao AND s.semana = p.semana
        JOIN config.tributo AS t ON t.produto = p.produto AND p.semana BETWEEN t.vigente_de AND t.vigente_ate
    ) AS x;

    DROP TABLE IF EXISTS gold.evento;
    CREATE TABLE gold.evento AS
    SELECT data, DATEADD(day, -(DATEDIFF(day, '19000101', data) % 7), data) AS semana,
           produto, tipo, descricao
    FROM config.evento;
END;
GO
