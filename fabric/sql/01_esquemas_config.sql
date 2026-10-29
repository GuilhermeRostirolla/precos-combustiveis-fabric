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
-- Gasolina: E27 desde 16/03/2015 e E30 desde 01/08/2025.
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
    ('GASOLINA',   '2025-08-01', '2099-12-31', 0.7000, 'E30'),
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
    ('janela_isolamento', 6, 'Semanas sem outro reajuste depois do evento para ele contar como isolado'),
    ('preco_minimo', 1.500000, 'Preço de venda abaixo disso vai para a quarentena (R$/litro)'),
    ('preco_maximo', 15.000000, 'Preço de venda acima disso vai para a quarentena (R$/litro)'),
    ('postos_minimos', 5, 'Postos pesquisados na semana para a média de um município entrar na análise');
GO
