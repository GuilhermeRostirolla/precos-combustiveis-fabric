-- Esquemas e tabelas de configuração do Warehouse wh_combustiveis.
-- Idempotente: pode rodar de novo a cada instalação.

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'config') EXEC('CREATE SCHEMA config');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'silver') EXEC('CREATE SCHEMA silver');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'gold') EXEC('CREATE SCHEMA gold');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'qualidade') EXEC('CREATE SCHEMA qualidade');
GO

-- Produtos analisados: o nome na pesquisa de postos e o nome na planilha de produtores.
-- A gasolina vendida no posto (C) é gasolina A misturada com etanol anidro; o diesel S10 vendido (B)
-- é diesel A misturado com biodiesel. O repasse esperado na bomba é a parcela fóssil vezes a variação na refinaria.
DROP TABLE IF EXISTS config.produto;
GO
CREATE TABLE config.produto (
    produto varchar(40) NOT NULL,
    produto_produtor varchar(80) NOT NULL,
    descricao varchar(120) NOT NULL
);
GO
INSERT INTO config.produto VALUES
    ('GASOLINA', 'Gasolina A Comum (R$/litro)', 'Gasolina comum (C) vendida no posto x gasolina A na refinaria'),
    ('DIESEL S10', 'Óleo Diesel S-10 (R$/litro)', 'Diesel S10 (B) vendido no posto x diesel S10 A na refinaria');
GO

-- Fração fóssil do litro vendido no posto, conforme o mandato de mistura vigente.
-- Gasolina: E27 desde 16/03/2015, E30 desde 01/08/2025 e E32 desde 01/08/2026 (Resolução CNPE 9/2026).
-- Diesel: B10 em 2022, B12 (04/2023), B14 (03/2024) e B15 (08/2025). Antes de 2022 o mandato do biodiesel
-- mudou várias vezes (B10 a B13 entre 2020 e 2021); como a análise começa em 2023, a tabela parte de 2022.
DROP TABLE IF EXISTS config.mistura;
GO
CREATE TABLE config.mistura (
    produto varchar(40) NOT NULL,
    vigente_de date NOT NULL,
    vigente_ate date NOT NULL,
    fracao_fossil decimal(5,4) NOT NULL,
    mandato varchar(10) NOT NULL
);
GO
INSERT INTO config.mistura VALUES
    ('GASOLINA',   '2015-03-16', '2025-07-31', 0.7300, 'E27'),
    ('GASOLINA',   '2025-08-01', '2026-07-31', 0.7000, 'E30'),
    ('GASOLINA',   '2026-08-01', '2099-12-31', 0.6800, 'E32'),
    ('DIESEL S10', '2022-01-01', '2023-03-31', 0.9000, 'B10'),
    ('DIESEL S10', '2023-04-01', '2024-02-29', 0.8800, 'B12'),
    ('DIESEL S10', '2024-03-01', '2025-07-31', 0.8600, 'B14'),
    ('DIESEL S10', '2025-08-01', '2099-12-31', 0.8500, 'B15');
GO

-- Parâmetros da análise de repasse.
DROP TABLE IF EXISTS config.parametro;
GO
CREATE TABLE config.parametro (
    nome varchar(40) NOT NULL,
    valor decimal(18,6) NOT NULL,
    descricao varchar(200) NOT NULL
);
GO
INSERT INTO config.parametro VALUES
    ('limiar_reajuste', 0.020000, 'Variação semanal mínima do preço na refinaria para contar como reajuste (2%)'),
    ('horizonte_semanas', 8, 'Semanas acompanhadas depois do reajuste'),
    ('preco_minimo', 1.500000, 'Preço de venda abaixo disso vai para a quarentena (R$/litro)'),
    ('preco_maximo', 15.000000, 'Preço de venda acima disso vai para a quarentena (R$/litro)'),
    ('postos_minimos', 5, 'Postos pesquisados na semana para a média de um município entrar na análise');
GO

-- Região de cada estado, para usar o preço de produtores e importadores da região certa.
DROP TABLE IF EXISTS config.uf_regiao;
GO
CREATE TABLE config.uf_regiao (
    uf char(2) NOT NULL,
    regiao varchar(20) NOT NULL
);
GO
INSERT INTO config.uf_regiao VALUES
    ('AC','Norte'), ('AM','Norte'), ('AP','Norte'), ('PA','Norte'), ('RO','Norte'), ('RR','Norte'), ('TO','Norte'),
    ('AL','Nordeste'), ('BA','Nordeste'), ('CE','Nordeste'), ('MA','Nordeste'), ('PB','Nordeste'),
    ('PE','Nordeste'), ('PI','Nordeste'), ('RN','Nordeste'), ('SE','Nordeste'),
    ('DF','Centro-Oeste'), ('GO','Centro-Oeste'), ('MS','Centro-Oeste'), ('MT','Centro-Oeste'),
    ('ES','Sudeste'), ('MG','Sudeste'), ('RJ','Sudeste'), ('SP','Sudeste'),
    ('PR','Sul'), ('RS','Sul'), ('SC','Sul'),
    ('BR','Brasil');
GO

-- Tributos por litro, para dividir o preço do posto em partes (mesmo método da Síntese Semanal da ANP).
-- icms: valor fixo por litro vendido no posto, igual em todo o país (Convênios ICMS do Confaz).
-- federal_fossil: PIS/Pasep, Cofins e Cide por litro de gasolina A ou diesel A.
-- federal_bio: PIS/Pasep e Cofins por litro de etanol anidro ou biodiesel.
-- Os valores federais são as alíquotas cheias que a ANP soma ao preço de produtores e importadores.
-- As reduções temporárias de 2026 (diesel desde 12/03; gasolina a partir de 10/09) não entram nessa
-- planilha da ANP, então também não entram aqui: ficam registradas em config.evento.
DROP TABLE IF EXISTS config.tributo;
GO
-- Tributos por litro (R$). federal_fossil é a alíquota cheia e federal_fossil_cobrado é o que de fato está sendo
-- cobrado no período (os cortes de 2026). A planilha de produtores e importadores da ANP traz o preço com o tributo
-- cobrado: quando a gasolina teve os tributos federais zerados (10/10/2026), o preço caiu R$ 0,28, quase o valor
-- que saiu (R$ 0,26). Por isso a refinaria é o preço da planilha menos o tributo cobrado.
CREATE TABLE config.tributo (
    produto varchar(40) NOT NULL,
    vigente_de date NOT NULL,
    vigente_ate date NOT NULL,
    icms decimal(8,4) NOT NULL,
    federal_fossil decimal(8,4) NOT NULL,
    federal_fossil_cobrado decimal(8,4) NOT NULL,
    federal_bio decimal(8,4) NOT NULL
);
GO
INSERT INTO config.tributo VALUES
    ('GASOLINA',   '2024-01-01', '2024-01-31', 1.2200, 0.8925, 0.8925, 0.1922),
    ('GASOLINA',   '2024-02-01', '2025-01-31', 1.3700, 0.8925, 0.8925, 0.1922),
    ('GASOLINA',   '2025-02-01', '2025-12-31', 1.4700, 0.8925, 0.8925, 0.1922),
    ('GASOLINA',   '2026-01-01', '2026-09-09', 1.5700, 0.8925, 0.8925, 0.1922),
    -- Decreto 13.116/2026: PIS/Cofins da gasolina cai R$ 0,63 (fica R$ 0,16) de 10/09 a 09/10/2026
    ('GASOLINA',   '2026-09-10', '2026-10-09', 1.5700, 0.8925, 0.2625, 0.1922),
    -- tributos federais da gasolina zerados por 30 dias a partir de 10/10/2026
    ('GASOLINA',   '2026-10-10', '2026-11-08', 1.5700, 0.8925, 0.0000, 0.1922),
    ('GASOLINA',   '2026-11-09', '2027-01-31', 1.5700, 0.8925, 0.8925, 0.1922),
    ('GASOLINA',   '2027-02-01', '2099-12-31', 1.6400, 0.8925, 0.8925, 0.1922),
    ('DIESEL S10', '2024-01-01', '2024-01-31', 0.9456, 0.3515, 0.3515, 0.1480),
    ('DIESEL S10', '2024-02-01', '2025-01-31', 1.0635, 0.3515, 0.3515, 0.1480),
    ('DIESEL S10', '2025-02-01', '2025-12-31', 1.1200, 0.3515, 0.3515, 0.1480),
    ('DIESEL S10', '2026-01-01', '2026-03-11', 1.1700, 0.3515, 0.3515, 0.1480),
    -- PIS/Cofins do diesel zerado a partir de 12/03/2026, previsto até o fim do ano
    ('DIESEL S10', '2026-03-12', '2026-12-31', 1.1700, 0.3515, 0.0000, 0.1480),
    ('DIESEL S10', '2027-01-01', '2027-01-31', 1.1700, 0.3515, 0.3515, 0.1480),
    ('DIESEL S10', '2027-02-01', '2099-12-31', 1.3000, 0.3515, 0.3515, 0.1480);
GO

-- Acontecimentos que ajudam a explicar as mudanças de preço (aparecem no relatório).
DROP TABLE IF EXISTS config.evento;
GO
CREATE TABLE config.evento (
    data date NOT NULL,
    produto varchar(40) NOT NULL, -- GASOLINA, DIESEL S10 ou TODOS
    tipo varchar(20) NOT NULL,    -- Imposto, Mistura, Mercado
    descricao varchar(300) NOT NULL
);
GO
INSERT INTO config.evento VALUES
    ('2024-02-01', 'GASOLINA',   'Imposto', 'ICMS da gasolina sobe de R$ 1,22 para R$ 1,37 por litro'),
    ('2024-02-01', 'DIESEL S10', 'Imposto', 'ICMS do diesel sobe de R$ 0,95 para R$ 1,06 por litro'),
    ('2024-03-01', 'DIESEL S10', 'Mistura', 'Mistura de biodiesel no diesel passa de 12% para 14%'),
    ('2025-02-01', 'GASOLINA',   'Imposto', 'ICMS da gasolina sobe de R$ 1,37 para R$ 1,47 por litro'),
    ('2025-02-01', 'DIESEL S10', 'Imposto', 'ICMS do diesel sobe de R$ 1,06 para R$ 1,12 por litro'),
    ('2025-08-01', 'GASOLINA',   'Mistura', 'Mistura de etanol na gasolina passa de 27% para 30%'),
    ('2025-08-01', 'DIESEL S10', 'Mistura', 'Mistura de biodiesel no diesel passa de 14% para 15%'),
    ('2026-01-01', 'GASOLINA',   'Imposto', 'ICMS da gasolina sobe de R$ 1,47 para R$ 1,57 por litro'),
    ('2026-01-01', 'DIESEL S10', 'Imposto', 'ICMS do diesel sobe de R$ 1,12 para R$ 1,17 por litro'),
    ('2026-03-01', 'TODOS',      'Mercado', 'Petróleo dispara com o conflito no Oriente Médio'),
    ('2026-03-12', 'DIESEL S10', 'Imposto', 'Governo zera PIS/Cofins do diesel e cria subvenção a produtores e importadores'),
    ('2026-08-01', 'GASOLINA',   'Mistura', 'Mistura de etanol na gasolina passa de 30% para 32%'),
    ('2026-09-10', 'GASOLINA',   'Imposto', 'Governo reduz PIS/Cofins da gasolina em R$ 0,63 por litro até 09/10'),
    ('2026-10-10', 'GASOLINA',   'Imposto', 'Tributos federais da gasolina zerados por 30 dias'),
    ('2027-02-01', 'GASOLINA',   'Imposto', 'ICMS da gasolina sobe de R$ 1,57 para R$ 1,64 por litro'),
    ('2027-02-01', 'DIESEL S10', 'Imposto', 'ICMS do diesel sobe de R$ 1,17 para R$ 1,30 por litro');
GO
