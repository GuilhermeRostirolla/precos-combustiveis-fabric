-- Análise do repasse: quando o preço na refinaria muda, quanto e em quanto tempo isso chega à bomba no RS?
--
-- Método (estudo de eventos):
-- 1. Reajuste = semana em que o preço médio de produtores e importadores da região Sul varia pelo menos
--    `limiar_reajuste` em relação à semana anterior. Semanas seguidas no mesmo sentido contam como um reajuste só
--    (um reajuste no meio da semana aparece dividido entre duas médias semanais).
-- 2. Variação na refinaria = preço na semana seguinte ao reajuste menos o preço na semana anterior a ele.
-- 3. Repasse esperado na bomba = variação na refinaria x fração fóssil do litro (gasolina A na gasolina C,
--    diesel A no diesel B). O ICMS dos combustíveis é um valor fixo por litro desde 2023, então não amplia o repasse.
-- 4. Repasse observado em h semanas = (preço médio na bomba em t+h) - (preço médio na semana anterior ao reajuste),
--    dividido pelo repasse esperado. 100% = a bomba acompanhou exatamente a refinaria.
-- 5. Reajuste isolado = nenhum outro reajuste nas `janela_isolamento` semanas seguintes. Só os isolados entram no
--    resumo, para um reajuste não contaminar a medição do outro.

CREATE OR ALTER PROCEDURE gold.sp_analise_repasse
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @limiar decimal(18,6) = (SELECT valor FROM config.parametro WHERE nome = 'limiar_reajuste');
    DECLARE @horizonte int = (SELECT CAST(valor AS int) FROM config.parametro WHERE nome = 'horizonte_semanas');
    DECLARE @janela int = (SELECT CAST(valor AS int) FROM config.parametro WHERE nome = 'janela_isolamento');

    DROP TABLE IF EXISTS #refinaria;
    SELECT produto, semana, preco_produtor, fracao_fossil,
           LAG(preco_produtor) OVER (PARTITION BY produto ORDER BY semana) AS preco_anterior,
           LAG(semana) OVER (PARTITION BY produto ORDER BY semana) AS semana_anterior
    INTO #refinaria
    FROM gold.fato_preco_produtor_semana
    WHERE regiao = 'Sul';

    DROP TABLE IF EXISTS #candidato;
    SELECT produto, semana, preco_produtor, fracao_fossil,
           CAST(preco_produtor / preco_anterior - 1 AS decimal(18,6)) AS variacao,
           CASE WHEN preco_produtor > preco_anterior THEN 1 ELSE -1 END AS sinal
    INTO #candidato
    FROM #refinaria
    WHERE preco_anterior IS NOT NULL
      AND DATEDIFF(day, semana_anterior, semana) = 7
      AND ABS(preco_produtor / preco_anterior - 1) >= @limiar;

    -- Primeira semana de cada reajuste (a anterior não é candidata no mesmo sentido).
    DROP TABLE IF EXISTS #evento;
    SELECT c.produto, c.semana, c.sinal, c.fracao_fossil,
           antes.preco_produtor AS preco_antes,
           depois.preco_produtor AS preco_depois
    INTO #evento
    FROM #candidato AS c
    JOIN gold.fato_preco_produtor_semana AS antes
      ON antes.produto = c.produto AND antes.regiao = 'Sul' AND antes.semana = DATEADD(day, -7, c.semana)
    JOIN gold.fato_preco_produtor_semana AS depois
      ON depois.produto = c.produto AND depois.regiao = 'Sul' AND depois.semana = DATEADD(day, 7, c.semana)
    WHERE NOT EXISTS (
        SELECT 1 FROM #candidato AS p
        WHERE p.produto = c.produto AND p.sinal = c.sinal AND p.semana = DATEADD(day, -7, c.semana)
    );

    DROP TABLE IF EXISTS gold.repasse_evento;
    CREATE TABLE gold.repasse_evento AS
    SELECT e.produto, e.semana AS semana_evento,
           CAST(CASE WHEN e.sinal = 1 THEN 'alta' ELSE 'baixa' END AS varchar(5)) AS direcao,
           e.preco_antes, e.preco_depois,
           CAST(e.preco_depois - e.preco_antes AS decimal(10,4)) AS variacao_refinaria,
           CAST(e.preco_depois / e.preco_antes - 1 AS decimal(10,6)) AS variacao_refinaria_pct,
           e.fracao_fossil,
           CAST((e.preco_depois - e.preco_antes) * e.fracao_fossil AS decimal(10,4)) AS repasse_esperado,
           CAST(CASE WHEN EXISTS (
                    SELECT 1 FROM #evento AS o
                    WHERE o.produto = e.produto AND o.semana > e.semana
                      AND o.semana <= DATEADD(day, 7 * @janela, e.semana)
                ) THEN 0 ELSE 1 END AS bit) AS isolado
    FROM #evento AS e
    WHERE e.preco_depois <> e.preco_antes
      AND SIGN(e.preco_depois - e.preco_antes) = e.sinal;

    -- Séries da bomba no RS: o estado e cada município com amostra suficiente.
    DROP TABLE IF EXISTS #bomba;
    SELECT CAST('RS (estado)' AS varchar(120)) AS escopo, CAST(NULL AS varchar(100)) AS municipio,
           produto, semana, preco_medio
    INTO #bomba
    FROM gold.fato_preco_uf_semana
    WHERE uf = 'RS'
    UNION ALL
    SELECT CAST(municipio AS varchar(120)), municipio, produto, semana, preco_medio
    FROM gold.fato_preco_municipio_semana
    WHERE uf = 'RS' AND amostra_suficiente = 1;

    DROP TABLE IF EXISTS #horizonte;
    SELECT TOP (@horizonte + 1) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS h
    INTO #horizonte
    FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12)) AS v(x);

    DROP TABLE IF EXISTS gold.repasse_curva;
    CREATE TABLE gold.repasse_curva AS
    SELECT e.produto, e.semana_evento, e.direcao, e.isolado, b0.escopo, b0.municipio, hz.h,
           DATEADD(day, 7 * hz.h, e.semana_evento) AS semana,
           b0.preco_medio AS preco_bomba_antes,
           bh.preco_medio AS preco_bomba,
           CAST(bh.preco_medio - b0.preco_medio AS decimal(10,4)) AS variacao_bomba,
           e.repasse_esperado,
           CAST((bh.preco_medio - b0.preco_medio) / e.repasse_esperado AS decimal(10,4)) AS repasse
    FROM gold.repasse_evento AS e
    JOIN #bomba AS b0
      ON b0.produto = e.produto AND b0.semana = DATEADD(day, -7, e.semana_evento)
    CROSS JOIN #horizonte AS hz
    JOIN #bomba AS bh
      ON bh.produto = e.produto AND bh.escopo = b0.escopo AND bh.semana = DATEADD(day, 7 * hz.h, e.semana_evento);

    -- Resumo: repasse mediano por semana depois do reajuste, separando altas e baixas (só reajustes isolados).
    DROP TABLE IF EXISTS gold.repasse_resumo;
    CREATE TABLE gold.repasse_resumo AS
    SELECT DISTINCT produto, escopo, direcao, h,
           COUNT(*) OVER (PARTITION BY produto, escopo, direcao, h) AS eventos,
           CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY repasse)
                OVER (PARTITION BY produto, escopo, direcao, h) AS decimal(10,4)) AS repasse_mediano,
           CAST(AVG(repasse) OVER (PARTITION BY produto, escopo, direcao, h) AS decimal(10,4)) AS repasse_medio
    FROM gold.repasse_curva
    WHERE isolado = 1;

    -- Velocidade: em quantas semanas a bomba chega a metade e a 80% do repasse esperado.
    DROP TABLE IF EXISTS #marcos;
    SELECT produto, escopo, direcao, semana_evento,
           MIN(CASE WHEN repasse >= 0.5 THEN h END) AS semanas_ate_50,
           MIN(CASE WHEN repasse >= 0.8 THEN h END) AS semanas_ate_80
    INTO #marcos
    FROM gold.repasse_curva
    WHERE isolado = 1
    GROUP BY produto, escopo, direcao, semana_evento;

    DROP TABLE IF EXISTS gold.repasse_velocidade;
    CREATE TABLE gold.repasse_velocidade AS
    SELECT DISTINCT produto, escopo, direcao,
           COUNT(*) OVER (PARTITION BY produto, escopo, direcao) AS eventos,
           SUM(CASE WHEN semanas_ate_80 IS NULL THEN 1 ELSE 0 END) OVER (PARTITION BY produto, escopo, direcao)
               AS eventos_sem_80_no_horizonte,
           CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY COALESCE(semanas_ate_50, 99))
                OVER (PARTITION BY produto, escopo, direcao) AS decimal(6,2)) AS semanas_mediana_ate_50,
           CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY COALESCE(semanas_ate_80, 99))
                OVER (PARTITION BY produto, escopo, direcao) AS decimal(6,2)) AS semanas_mediana_ate_80
    FROM #marcos;
END;
GO
