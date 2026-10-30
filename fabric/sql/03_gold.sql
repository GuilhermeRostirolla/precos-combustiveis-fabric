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
    -- A série histórica sai por mês, então a última semana dela pode estar incompleta (o mês acaba no meio da
    -- semana). Depois da última semana completa, vale o levantamento semanal da ANP, quando houver.
    DECLARE @ultima_coleta date = (SELECT MAX(data_coleta) FROM silver.preco_revenda);
    DECLARE @ultima_semana_completa date =
        DATEADD(day, -7, DATEADD(day, -(DATEDIFF(day, '19000101', DATEADD(day, 1, @ultima_coleta)) % 7),
                                 DATEADD(day, 1, @ultima_coleta)));
    DROP TABLE IF EXISTS #serie;
    SELECT semana, uf, produto,
           CAST(AVG(valor_venda) AS decimal(8,4)) AS preco_medio,
           COUNT(*) AS coletas,
           COUNT(DISTINCT cnpj) AS postos,
           COUNT(DISTINCT municipio) AS municipios
    INTO #serie
    FROM silver.preco_revenda
    GROUP BY semana, uf, produto;

    DROP TABLE IF EXISTS gold.fato_preco_uf_semana;
    CREATE TABLE gold.fato_preco_uf_semana AS
    SELECT s.semana, s.uf, s.produto, s.preco_medio, s.coletas, s.postos, s.municipios,
           CAST('Série histórica' AS varchar(20)) AS fonte
    FROM #serie AS s
    WHERE s.semana <= @ultima_semana_completa
       OR NOT EXISTS (SELECT 1 FROM silver.preco_uf_semanal AS w
                      WHERE w.semana = s.semana AND w.uf = s.uf AND w.produto = s.produto)
    UNION ALL
    SELECT w.semana, w.uf, w.produto, w.preco_medio, w.postos, w.postos, CAST(NULL AS int),
           CAST('Levantamento semanal' AS varchar(20))
    FROM silver.preco_uf_semanal AS w
    WHERE w.semana > @ultima_semana_completa;

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
           CONCAT(RIGHT(CONCAT('0', DAY(semana)), 2), '/', RIGHT(CONCAT('0', MONTH(semana)), 2), '/', YEAR(semana)) AS rotulo,
           DATEFROMPARTS(YEAR(semana), MONTH(semana), 1) AS mes_inicio,
           CONCAT(CHOOSE(MONTH(semana), 'jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'),
                  '/', RIGHT(CAST(YEAR(semana) AS varchar(4)), 2)) AS mes_rotulo
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
           CASE WHEN c.produto IS NULL THEN CAST(0 AS bit) ELSE CAST(1 AS bit) END AS tem_preco_refinaria,
           CASE r.produto WHEN 'GASOLINA' THEN 'Gasolina comum' WHEN 'DIESEL S10' THEN 'Diesel S10'
                          WHEN 'GASOLINA ADITIVADA' THEN 'Gasolina aditivada' WHEN 'ETANOL' THEN 'Etanol'
                          WHEN 'DIESEL' THEN 'Diesel S500' ELSE r.produto END AS nome,
           CASE r.produto WHEN 'GASOLINA' THEN 1 WHEN 'DIESEL S10' THEN 2 ELSE 9 END AS ordem
    FROM silver.preco_revenda AS r
    LEFT JOIN config.produto AS c ON c.produto = r.produto;

    -- Do que é feito o preço no posto, semana a semana, por estado e para o Brasil (uf = 'BR').
    -- Mesmo método da Síntese Semanal da ANP: preço no posto = refinaria (parte fóssil, sem tributos)
    -- + tributos federais + ICMS + o restante (etanol anidro ou biodiesel, frete e margens).
    -- Diferença em relação à Síntese: os tributos federais são os efetivamente cobrados. A Síntese usa sempre a
    -- alíquota cheia, o que, durante os cortes de 2026, joga o corte para dentro do preço da refinaria.
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
               -- a planilha da refinaria traz o tributo cobrado na semana dela (a anterior à do posto)
               s.fracao_fossil * (s.preco_produtor - tr.federal_fossil_cobrado) AS refinaria,
               s.fracao_fossil * t.federal_fossil_cobrado + (1 - s.fracao_fossil) * t.federal_bio AS tributos_federais
        FROM #posto AS p
        JOIN config.uf_regiao AS r ON r.uf = p.uf
        -- como na Síntese Semanal da ANP, o posto da semana é comparado com a refinaria da semana anterior
        JOIN #produtor_suavizado AS s ON s.produto = p.produto AND s.regiao = r.regiao
                                      AND s.semana = DATEADD(day, -7, p.semana)
        JOIN config.tributo AS t ON t.produto = p.produto AND p.semana BETWEEN t.vigente_de AND t.vigente_ate
        JOIN config.tributo AS tr ON tr.produto = p.produto AND s.semana BETWEEN tr.vigente_de AND tr.vigente_ate
    ) AS x;

    -- Semanas que podem ser escolhidas no relatório (sem relação com as tabelas: a página usa a escolhida
    -- e olha para trás a partir dela).
    DROP TABLE IF EXISTS gold.semana_referencia;
    CREATE TABLE gold.semana_referencia AS
    SELECT DISTINCT c.semana, d.rotulo
    FROM gold.composicao_preco_semana AS c
    JOIN gold.dim_semana AS d ON d.semana = c.semana;

    DROP TABLE IF EXISTS gold.dim_uf;
    CREATE TABLE gold.dim_uf AS
    SELECT uf, CASE WHEN uf = 'BR' THEN 'Brasil' ELSE uf END AS estado, regiao,
           CASE WHEN uf = 'BR' THEN 0 ELSE ROW_NUMBER() OVER (ORDER BY uf) END AS ordem
    FROM config.uf_regiao;

    -- Estados e regiões para a comparação por região (sem relação com as tabelas: o filtro de estado só destaca a
    -- região dele). A linha 'BR' representa o Brasil inteiro.
    DROP TABLE IF EXISTS gold.uf_ranking;
    DROP TABLE IF EXISTS gold.regiao_comparacao;
    CREATE TABLE gold.regiao_comparacao AS
    SELECT uf, regiao FROM config.uf_regiao;

    DROP TABLE IF EXISTS gold.componente;
    CREATE TABLE gold.componente AS
    SELECT componente, ordem
    FROM (VALUES ('Refinaria', 1), ('Impostos', 2), ('Etanol/biodiesel, frete e margens', 3)) AS c(componente, ordem);

    DROP TABLE IF EXISTS gold.evento;
    CREATE TABLE gold.evento AS
    SELECT data, DATEADD(day, -(DATEDIFF(day, '19000101', data) % 7), data) AS semana,
           produto, tipo, descricao
    FROM config.evento;
END;
GO
