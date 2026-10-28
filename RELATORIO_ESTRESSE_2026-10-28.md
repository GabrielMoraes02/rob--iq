# Testes ampliados — 28/10/2026

Versão executável: 1.0.18. Resultado: 116 testes passaram.

- 400 consultas em 50 lotes de 8 threads, respostas fora de ordem e confirmações antes/depois: sem mistura de respostas ou pendências residuais.
- 200 timeouts seguidos de respostas atrasadas: limpeza das pendências e recuperação na consulta seguinte.
- Mensagens inválidas e alheias à consulta: não encerram a requisição correta.
- Fila de 1.000 mensagens, incluindo JSON inválido: timer real continua, confirmação de parada processada e nova conexão simulada liberada.
- Suíte inclui suspensão, exclusão de Blitz, validade da confirmação, seleção durante a sessão, expiração, resultados e proteção PRACTICE.
- Autoteste do EXE 1.0.18 passou em ambiente isolado, incluindo encerramento do motor e filho, seleção por IPC, TLS e histórico. Não usa autenticação ou ordens.

## Leitura da sessão em observação

Início do motor às 14:50:42; última leitura às 15:06:59 (America/Sao_Paulo). Sem novos DIAGNOSTICO_CONSULTA. Um aviso inicial às 14:50:45, seguido de confirmações de abertura. Às 15:06 havia seis sinais simulados e nenhuma DEMO_ENVIADA nesta sessão.

## Limites

Não reproduzimos a falha intermitente nesta janela. O diagnóstico novo não permite atribuir retroativamente a causa de falhas antigas. Os testes não comprovam estabilidade indefinida nem execução de ordens na corretora. Nenhuma alteração na sessão ativa ou no algoritmo de entradas foi feita durante estes testes.
