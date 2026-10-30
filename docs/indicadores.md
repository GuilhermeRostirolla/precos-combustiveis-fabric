# Indicadores da página "Visão geral"

Todos os números usam a **semana de referência** (a última semana com dados, de segunda a domingo), o **combustível** e o **estado** escolhidos nos filtros. Exemplos: gasolina comum, Brasil, semana de 19/10/2026.

## Cartões

### Preço no posto: R$ 6,49/litro
Quanto custa o litro hoje.
Média simples dos preços pesquisados pela ANP na semana, no estado escolhido. Para "Brasil", média de todos os postos pesquisados no país (cerca de 4.500 por semana). Não é ponderada por volume vendido, porque a ANP não publica o volume de cada posto.

### Variação em 4 semanas: −R$ 0,08 (−1,2%)
Se o preço está subindo ou caindo agora.
Preço desta semana − preço de 4 semanas antes (28 dias): 6,49 − 6,57 = −0,08; 6,49 ÷ 6,57 − 1 = −1,2%.

### Variação em 12 meses: +R$ 0,28 (+4,5%)
Quanto o preço mudou em um ano.
Preço desta semana − preço de 52 semanas antes (20/10/2025): 6,49 − 6,21 = +0,28; 6,49 ÷ 6,21 − 1 = +4,5%.
É o mesmo total do gráfico "O que mudou em 12 meses": 0,28 − 0,52 + 0,52 = 0,28.

### Impostos no litro: R$ 1,63 (25% do preço)
Quanto do litro é imposto.
ICMS + tributos federais por litro, nos valores fixos em R$ definidos por lei, contando os dias de cada semana:
- ICMS da gasolina: R$ 1,57 (o mesmo em todo o país desde 2023).
- Federais: a gasolina C é 68% gasolina A e 32% etanol anidro (E32). Desde 10/10/2026, PIS/Cofins e Cide da gasolina A estão zerados; o anidro paga R$ 0,19/litro: 0,68 × R$ 0 + 0,32 × R$ 0,19 = R$ 0,06.
- Total: 1,57 + 0,06 = R$ 1,63; 1,63 ÷ 6,49 = 25%.

"Há 12 meses R$ 2,15": a mesma conta em 20/10/2025 (ICMS R$ 1,47 + federais sem corte R$ 0,68).

### Etanol ÷ gasolina: 67% (gasolina escolhida)
Se compensa abastecer com etanol.
Preço médio do etanol hidratado ÷ preço médio da gasolina comum, no mesmo estado e semana. Abaixo de 70%, o etanol compensa (verde). A barra mostra o percentual e a marca ▲ indica os 70%.

### Refinaria em 12 meses: +13,3% (Diesel S10 escolhido)
Quanto o preço da refinaria mudou em um ano.
Preço da refinaria por litro de diesel A hoje ÷ o de 52 semanas antes − 1.

## Gráficos

### Do que é feito o preço do litro (últimas 52 semanas)
As três partes empilhadas somam o preço no posto de cada semana:
- **Refinaria**: preço de produtores e importadores (planilha semanal da ANP) da semana anterior, menos os tributos federais cobrados naquela semana, vezes a parcela fóssil do litro (68% na gasolina E32, 85% no diesel B15). Mediana de 3 semanas, porque a série oscila quando muda a proporção de importadores.
- **Impostos**: ICMS + tributos federais efetivamente cobrados.
- **Etanol/biodiesel, frete e margens**: o que sobra (preço no posto − refinaria − impostos).

### O que mudou em 12 meses
Variação de cada parte entre a semana de referência e a de 52 semanas antes, e na última coluna o resultado no posto. Gasolina, Brasil: refinaria +R$ 0,28, impostos −R$ 0,52, etanol/biodiesel, frete e margens +R$ 0,52; preço no posto +R$ 0,28.

### Diferença para a média do Brasil
Preço médio de cada região (média dos postos pesquisados nos estados dela) menos o do Brasil, na semana de referência. Vermelho: mais caro que a média; verde: mais barato. Com um estado escolhido, ele aparece em laranja. Gasolina: Norte +R$ 0,42, Nordeste +R$ 0,24, Centro-Oeste −R$ 0,02, Sudeste −R$ 0,11, Sul −R$ 0,15; SP −R$ 0,14.

## Método e conferência

O preço é dividido como na [Síntese Semanal da ANP](https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/sintese-semanal-do-comportamento-dos-precos-dos-combustiveis): o posto da semana é comparado com a refinaria da semana anterior. Há uma diferença deliberada: os **tributos federais são os efetivamente cobrados**. A Síntese usa sempre a alíquota cheia, o que, durante os cortes de 2026, joga o corte para dentro do preço da refinaria. Por exemplo, depois de 10/09/2026 a Síntese mostra a gasolina A a R$ 2,56, enquanto a Petrobras passou a vendê-la a R$ 3,05 sem tributos.

Conferência com a Síntese da semana de 20 a 26/09/2026:

| | ANP | Projeto |
|---|---|---|
| Gasolina C no posto | R$ 6,55 | R$ 6,57 |
| Gasolina: refinaria + tributos federais | R$ 2,41 | R$ 2,47 |
| Gasolina: ICMS | R$ 1,57 | R$ 1,57 |
| Gasolina: anidro + margens | R$ 2,57 | R$ 2,53 |
| Diesel S10 no posto | R$ 7,33 | R$ 7,33 |
| Diesel: refinaria + tributos federais | R$ 3,33 | R$ 3,33 |
| Diesel: biodiesel + margens | R$ 2,82 | R$ 2,82 |

Impostos de 2026 considerados (tabela `config.tributo`):
- PIS/Cofins do diesel zerado de 12/03 a 31/12/2026; o do biodiesel, de 08/04 a 31/07/2026.
- Decreto 13.116/2026: PIS/Cofins da gasolina A de R$ 0,79 para R$ 0,16 por litro, de 10/09 a 09/10/2026 (o etanol zerado é o hidratado; o anidro segue tributado).
- Decreto 13.134/2026: PIS/Cofins e Cide da gasolina zerados por 30 dias a partir de 10/10/2026.
- ICMS: gasolina R$ 1,57 e diesel R$ 1,17 em 2026; R$ 1,64 e R$ 1,30 a partir de 01/02/2027.

## Limites

- A ANP só publica o preço de refinaria por região: SP usa o do Sudeste, o RS o do Sul. A página mostra qual região está sendo usada.
- A amostra de postos muda de semana para semana; variações de poucos centavos podem ser só diferença de amostra.
- A série posto a posto da ANP sai por mês, com atraso. As semanas seguintes vêm do levantamento semanal por estado da ANP (mesma pesquisa, já agregada).
- As subvenções a produtores e importadores (diesel e gasolina) aparecem como preço menor da refinaria, porque a planilha da ANP traz o preço efetivamente praticado.
- "Etanol/biodiesel, frete e margens" é o que sobra da conta; não há fonte pública semanal que separe cada item.
