# Expiração solicitada de 30 segundos em Binárias/Turbo

O usuário confirmou que o prazo aparece em Binárias/Turbo na sua plataforma.
O adaptador preserva essa modalidade; não muda automaticamente para Blitz.

O método `buy` da versão instalada da iqoptionapi converte a duração para
`int` e usa minutos. Por isso enviar `0.5` a esse método não implementa 30s.
O método separado `buy_by_raw_expirations` aceita o horário absoluto de
vencimento e o produto `turbo`.

Documentação do mantenedor:
https://iqoptionapi.github.io/iqoptionapi/en/binary%20option/binary%20option/

Implementação do protocolo na dependência:
https://github.com/iqoptionapi/iqoptionapi/blob/master/iqoptionapi/ws/chanels/buyv3.py

O adaptador solicita `int(server_timestamp) + 30`, sem alinhar a outro minuto,
sem usar relógio local como substituto e sem fallback para 1 minuto. O prazo
é medido a partir do segundo inteiro do relógio do servidor no envio. A
granularidade de segundos e a latência podem reduzir o tempo restante no
instante da aceitação; isso não é garantia de 30s contados após a execução.

A API e a disponibilidade da plataforma não garantem que todo par aceite
um vencimento arbitrário. A corretora pode recusar. O bot registra a recusa,
mantém o prazo escolhido e não reenvia com outro produto ou vencimento.
A confirmação final deve comparar o timestamp solicitado com os detalhes
da ordem aceita em uma conta DEMO.

A documentação oficial de Blitz descreve outro produto com prazos a partir
de 30s; essa informação não é usada como prova de suporte em Binárias/Turbo:
https://blog.iqoption.com/pt/iq-option-introduces-blitz-options-up-to-95-profit-from-5-seconds/
