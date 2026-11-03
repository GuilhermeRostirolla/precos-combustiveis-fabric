-- Análise do repasse: quando o preço na refinaria muda, quanto e em quanto tempo isso chega à bomba?
-- Roda para cada região (refinaria) e cada estado (bomba, com a refinaria da sua região); o Brasil é a soma dos
-- estados. Os municípios do RS com amostra suficiente também entram (e são usados na conferência em Python).
--
-- Método (estudo de eventos):
-- 1. Série da refinaria = preço médio de produtores e importadores da região, sem os tributos federais
--    efetivamente cobrados na semana (assim um corte de imposto, como o de setembro/2026, não vira "reajuste"),
--    suavizado pela mediana de 3 semanas (t-1, t, t+1). A planilha mistura refinarias e importadores e a proporção muda de uma semana para
--    outra; a mediana elimina os picos de uma semana só sem deslocar mudanças de patamar.
-- 2. Semana candidata = a série suavizada varia pelo menos `limiar_reajuste` em relação à semana anterior.
--    Semanas candidatas seguidas no mesmo sentido formam um reajuste só (um aumento pode chegar ao longo de
--    várias semanas).
-- 3. Variação na refinaria = nível na semana seguinte ao fim do reajuste menos o nível na semana anterior ao início.
-- 4. Repasse esperado na bomba = variação na refinaria x fração fóssil do litro (gasolina A na gasolina C,
--    diesel A no diesel B). O ICMS virou um valor fixo por litro em 2023 (diesel em maio, gasolina em junho), então
--    a partir daí não amplia o repasse.
-- 5. Repasse observado em h semanas = (preço médio na bomba em t+h) - (preço médio na semana anterior ao reajuste),
--    dividido pelo repasse esperado. 100% = a bomba acompanhou exatamente a refinaria.
-- 6. Cada reajuste é acompanhado por até `horizonte_semanas`, mas só até a semana anterior ao reajuste seguinte,
--    para um reajuste não contaminar a medição do outro.

CREATE OR ALTER PROCEDURE gold.sp_analise_repasse
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @limiar decimal(18,6) = (SELECT valor FROM config.parametro WHERE nome = 'limiar_reajuste');
    DECLARE @horizonte int = (SELECT CAST(valor AS int) FROM config.parametro WHERE nome = 'horizonte_semanas');
    DECLARE @inicio_bomba date = (SELECT MIN(semana) FROM gold.fato_preco_uf_semana);

    -- 1. Série da refinaria de cada região, sem os tributos federais cobrados na semana (média dos dias), suavizada
    --    pela mediana de 3 semanas.
    --    Antes de 2024 (sem valores em config.tributo) vale o primeiro valor da tabela, para não criar um degrau; os
    --    reajustes que caem em cima das mudanças de tributo daquele período são descartados no passo 3.
    DROP TABLE IF EXISTS #tributo_semana;
    SELECT w.semana, c.produto,
           AVG(COALESCE(t.federal_fossil_cobrado, primeiro.federal_fossil_cobrado)) AS federal_fossil_cobrado
    INTO #tributo_semana
    FROM (SELECT DISTINCT semana FROM gold.fato_preco_produtor_semana) AS w
    CROSS JOIN (VALUES (0),(1),(2),(3),(4),(5),(6)) AS d(n)
    CROSS JOIN (SELECT DISTINCT produto FROM config.tributo) AS c
    JOIN config.tributo AS primeiro
      ON primeiro.produto = c.produto
     AND primeiro.vigente_de = (SELECT MIN(vigente_de) FROM config.tributo AS x WHERE x.produto = c.produto)
    LEFT JOIN config.tributo AS t
      ON t.produto = c.produto AND DATEADD(day, d.n, w.semana) BETWEEN t.vigente_de AND t.vigente_ate
    GROUP BY w.semana, c.produto;

    DROP TABLE IF EXISTS #vizinhos;
    SELECT f.produto, f.regiao, f.semana, f.fracao_fossil,
           CAST(f.preco_produtor - t.federal_fossil_cobrado AS decimal(10,4)) AS preco_produtor,
           LAG(CAST(f.preco_produtor - t.federal_fossil_cobrado AS decimal(10,4)))
               OVER (PARTITION BY f.produto, f.regiao ORDER BY f.semana) AS anterior,
           LEAD(CAST(f.preco_produtor - t.federal_fossil_cobrado AS decimal(10,4)))
               OVER (PARTITION BY f.produto, f.regiao ORDER BY f.semana) AS seguinte
    INTO #vizinhos
    FROM gold.fato_preco_produtor_semana AS f
    JOIN #tributo_semana AS t ON t.produto = f.produto AND t.semana = f.semana
    WHERE f.regiao <> 'Brasil';

    DROP TABLE IF EXISTS gold.refinaria_suavizada;
    CREATE TABLE gold.refinaria_suavizada AS
    SELECT produto, regiao, semana, preco_produtor, fracao_fossil,
           CAST(CASE
               WHEN anterior IS NULL OR seguinte IS NULL THEN preco_produtor
               -- mediana de três valores = soma - maior - menor
               ELSE preco_produtor + anterior + seguinte
                    - CASE WHEN preco_produtor >= anterior AND preco_produtor >= seguinte THEN preco_produtor
                           WHEN anterior >= seguinte THEN anterior ELSE seguinte END
                    - CASE WHEN preco_produtor <= anterior AND preco_produtor <= seguinte THEN preco_produtor
                           WHEN anterior <= seguinte THEN anterior ELSE seguinte END
           END AS decimal(10,4)) AS preco_suavizado
    FROM #vizinhos;

    -- 2. Semanas candidatas e agrupamento das semanas seguidas no mesmo sentido.
    DROP TABLE IF EXISTS #candidato;
    SELECT produto, regiao, semana, sinal,
           DATEDIFF(day, '19000101', semana) / 7
               - ROW_NUMBER() OVER (PARTITION BY produto, regiao, sinal ORDER BY semana) AS grupo
    INTO #candidato
    FROM (
        SELECT produto, regiao, semana,
               CASE WHEN preco_suavizado > LAG(preco_suavizado) OVER (PARTITION BY produto, regiao ORDER BY semana)
                    THEN 1 ELSE -1 END AS sinal,
               ABS(preco_suavizado / LAG(preco_suavizado) OVER (PARTITION BY produto, regiao ORDER BY semana) - 1)
                   AS variacao,
               DATEDIFF(day, LAG(semana) OVER (PARTITION BY produto, regiao ORDER BY semana), semana) AS distancia
        FROM gold.refinaria_suavizada
    ) AS s
    WHERE distancia = 7 AND variacao >= @limiar;

    DROP TABLE IF EXISTS #sequencia;
    SELECT produto, regiao, sinal, MIN(semana) AS inicio, MAX(semana) AS fim, COUNT(*) AS semanas
    INTO #sequencia
    FROM #candidato
    GROUP BY produto, regiao, sinal, grupo;

    -- 3 e 4. Reajustes: nível antes do início e depois do fim; só os que mudam o patamar de fato.
    DROP TABLE IF EXISTS #evento;
    SELECT q.produto, q.regiao, q.inicio AS semana_evento, q.fim AS semana_fim_reajuste, q.semanas, q.sinal,
           antes.preco_suavizado AS preco_antes, depois.preco_suavizado AS preco_depois, depois.fracao_fossil
    INTO #evento
    FROM #sequencia AS q
    JOIN gold.refinaria_suavizada AS antes
      ON antes.produto = q.produto AND antes.regiao = q.regiao AND antes.semana = DATEADD(day, -7, q.inicio)
    JOIN gold.refinaria_suavizada AS depois
      ON depois.produto = q.produto AND depois.regiao = q.regiao AND depois.semana = DATEADD(day, 7, q.fim)
    WHERE q.inicio >= DATEADD(day, 7, @inicio_bomba)
      AND SIGN(depois.preco_suavizado - antes.preco_suavizado) = q.sinal
      AND ABS(depois.preco_suavizado / antes.preco_suavizado - 1) >= @limiar
      -- fora os que coincidem com uma mudança de tributo anterior a 2024 (semana antes até a semana depois)
      AND NOT EXISTS (SELECT 1 FROM config.mudanca_tributo AS m
                      WHERE m.produto = q.produto
                        AND m.data BETWEEN DATEADD(day, -7, q.inicio) AND DATEADD(day, 13, q.fim));

    DROP TABLE IF EXISTS gold.repasse_evento;
    CREATE TABLE gold.repasse_evento AS
    SELECT produto, regiao, semana_evento, semana_fim_reajuste, CAST(semanas AS int) AS semanas_reajuste,
           CAST(CASE WHEN sinal = 1 THEN 'alta' ELSE 'baixa' END AS varchar(5)) AS direcao,
           preco_antes, preco_depois,
           CAST(preco_depois - preco_antes AS decimal(10,4)) AS variacao_refinaria,
           CAST(preco_depois / preco_antes - 1 AS decimal(10,6)) AS variacao_refinaria_pct,
           fracao_fossil,
           CAST((preco_depois - preco_antes) * fracao_fossil AS decimal(10,4)) AS repasse_esperado,
           proximo_reajuste,
           CAST(CASE WHEN proximo_reajuste IS NULL
                       OR DATEDIFF(day, semana_evento, proximo_reajuste) / 7 - 1 > @horizonte THEN @horizonte
                     ELSE DATEDIFF(day, semana_evento, proximo_reajuste) / 7 - 1 END AS int) AS semanas_acompanhadas
    FROM (SELECT *, LEAD(semana_evento) OVER (PARTITION BY produto, regiao ORDER BY semana_evento) AS proximo_reajuste
          FROM #evento) AS e;

    -- Séries da bomba: cada estado (com a região da refinaria) e cada município do RS com amostra suficiente.
    DROP TABLE IF EXISTS #bomba;
    SELECT CAST(CONCAT(u.uf, ' (estado)') AS varchar(120)) AS escopo, CAST(u.uf AS varchar(2)) AS uf,
           CAST(NULL AS varchar(100)) AS municipio, r.regiao, u.produto, u.semana, u.preco_medio
    INTO #bomba
    FROM gold.fato_preco_uf_semana AS u
    JOIN config.uf_regiao AS r ON r.uf = u.uf
    WHERE u.fonte = 'Série histórica'  -- o estudo usa só a série posto a posto
    UNION ALL
    SELECT CAST(m.municipio AS varchar(120)), CAST(m.uf AS varchar(2)), m.municipio, r.regiao, m.produto, m.semana,
           m.preco_medio
    FROM gold.fato_preco_municipio_semana AS m
    JOIN config.uf_regiao AS r ON r.uf = m.uf
    WHERE m.uf = 'RS' AND m.amostra_suficiente = 1;

    DROP TABLE IF EXISTS #horizonte;
    SELECT TOP (@horizonte + 1) CAST(ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS int) AS h
    INTO #horizonte
    FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11),(12)) AS v(x);

    -- 5 e 6. Curva de repasse, semana a semana, até o reajuste seguinte.
    DROP TABLE IF EXISTS gold.repasse_curva;
    CREATE TABLE gold.repasse_curva AS
    SELECT e.produto, e.regiao, e.semana_evento, e.direcao, b0.escopo, b0.uf, b0.municipio, hz.h,
           DATEADD(day, 7 * hz.h, e.semana_evento) AS semana,
           b0.preco_medio AS preco_bomba_antes,
           bh.preco_medio AS preco_bomba,
           CAST(bh.preco_medio - b0.preco_medio AS decimal(10,4)) AS variacao_bomba,
           e.repasse_esperado,
           CAST((bh.preco_medio - b0.preco_medio) / e.repasse_esperado AS decimal(10,4)) AS repasse
    FROM gold.repasse_evento AS e
    JOIN #bomba AS b0
      ON b0.produto = e.produto AND b0.regiao = e.regiao AND b0.semana = DATEADD(day, -7, e.semana_evento)
    JOIN #horizonte AS hz
      ON hz.h <= e.semanas_acompanhadas
    JOIN #bomba AS bh
      ON bh.produto = e.produto AND bh.escopo = b0.escopo AND bh.semana = DATEADD(day, 7 * hz.h, e.semana_evento);

    -- Resumo por semana depois do reajuste, separando altas e baixas:
    -- repasse ponderado = soma das variações na bomba / soma dos repasses esperados (cada reajuste pesa pelo
    -- tamanho; é a medida principal) e, para comparar, a mediana e a média das razões de cada reajuste.
    DROP TABLE IF EXISTS #curva_escopo;
    SELECT produto, escopo, direcao, h, semana_evento, variacao_bomba, repasse_esperado, repasse
    INTO #curva_escopo
    FROM gold.repasse_curva
    UNION ALL
    -- o Brasil junta os estados: cada par estado x reajuste da região dele conta uma vez
    SELECT produto, 'Brasil', direcao, h, semana_evento, variacao_bomba, repasse_esperado, repasse
    FROM gold.repasse_curva
    WHERE municipio IS NULL;

    DROP TABLE IF EXISTS gold.repasse_resumo;
    CREATE TABLE gold.repasse_resumo AS
    SELECT DISTINCT produto, escopo, direcao, h,
           COUNT(*) OVER (PARTITION BY produto, escopo, direcao, h) AS eventos,
           CAST(SUM(variacao_bomba) OVER (PARTITION BY produto, escopo, direcao, h)
                / SUM(repasse_esperado) OVER (PARTITION BY produto, escopo, direcao, h) AS decimal(10,4))
               AS repasse_ponderado,
           CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY repasse)
                OVER (PARTITION BY produto, escopo, direcao, h) AS decimal(10,4)) AS repasse_mediano,
           CAST(AVG(repasse) OVER (PARTITION BY produto, escopo, direcao, h) AS decimal(10,4)) AS repasse_medio
    FROM #curva_escopo;

    -- Velocidade: em quantas semanas a bomba chega a metade e a 80% do repasse esperado. Entra só o reajuste em
    -- que a marca foi atingida ou que foi acompanhado pelo horizonte inteiro sem atingi-la (contado como 99).
    DROP TABLE IF EXISTS #marcos;
    SELECT c.produto, c.escopo, c.direcao, c.semana_evento, MAX(c.h) AS ultima_semana,
           MIN(CASE WHEN c.repasse >= 0.5 THEN c.h END) AS semanas_ate_50,
           MIN(CASE WHEN c.repasse >= 0.8 THEN c.h END) AS semanas_ate_80
    INTO #marcos
    FROM gold.repasse_curva AS c
    GROUP BY c.produto, c.escopo, c.direcao, c.semana_evento;

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
    FROM #marcos
    WHERE semanas_ate_80 IS NOT NULL OR ultima_semana = @horizonte;
END;
GO
