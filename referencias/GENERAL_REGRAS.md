# Regras do indicador General fornecido pelo usuário

Fonte: `Texto colado.txt`, anexado à conversa em 27/10/2026. Apenas as condições
de sinal relevantes são documentadas aqui; comentários repetidos do original
não influenciam o cálculo. `close`, `open`, `high` e `low` sem índice se referem
à vela atual; `[1]`, `[2]` e `[3]` são velas anteriores.

Bolinha CALL:
`close[1] < open[1] and close > open and close > high[1] and close[2] >= open`.

Bolinha PUT:
`close[1] > open[1] and close < open and close < low[1] and close[2] <= open`.

Seta CALL:
`close > close[1] and close[1] > open[2] and close[3] > close[2]`.

Seta PUT:
`close < close[1] and close[1] < open[2] and close[3] < close[2]`.

Os desenhos de círculos e setas usam deslocamento zero. Portanto, a seta pode
aparecer na vela em formação e desaparecer se o preço deixar de cumprir a
condição. Esperar a confirmação pelo fechamento impede executar na mesma vela.

As médias, cores, suporte/resistência e zig-zag do script não são condições
adicionais nos blocos `if` que desenham a bolinha ou a seta. O requisito de
bolinha anterior, recuo em pips, limite de 29 segundos e uso de DEMO são regras
do robô mantidas a pedido do usuário, não condições presentes nesses `if`.
