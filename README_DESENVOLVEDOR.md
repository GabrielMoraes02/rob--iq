# Código-fonte do Bot Marcos — Windows 1.0.19

Esta pasta é o projeto original editável. O executável é gerado a partir
destes arquivos; alterar o código não modifica um EXE que já foi gerado.

Neste computador, a pasta é:

`C:\Users\liche\Documents\ChatGPT\App persona\bot-marcos`

## Onde editar

| Arquivo | Responsabilidade |
| --- | --- |
| `painel.py` | Interface, botões, resumo, atividade e destaque do par nas entradas. |
| `MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py` | Sinais, filtros, envio de ordens DEMO e consulta dos resultados. |
| `motor_visual.py` | Processo do motor, comunicação com a interface e gravação do histórico por conta. |
| `configuracao.py` | Parâmetros, validação e valores padrão. |
| `historico_nuvem.py` | SQLite por conta, fila de envio e sincronização com o Supabase. |
| `conexao_iq.py` | Conexão segura, certificados e tratamento de respostas da biblioteca IQ Option. |
| `saldo_painel.py` | Consulta do saldo virtual. |
| `caminhos.py` | Versão do programa, recursos do EXE e pasta de dados. |
| `iniciar_painel.py` | Entrada do aplicativo e autoteste offline do executável. |
| `gerar_exe.py` | Montagem do motor, do EXE final e do ZIP para o cliente. |
| `supabase/functions/historico-conta/index.ts` | Validação da sessão na corretora e acesso ao histórico no servidor. |

Abra os arquivos `.py` em um editor de código, altere e salve. Para mudanças
no painel, comece por `painel.py`. Para uma nova versão, altere `VERSAO` em
`caminhos.py` e atualize o título do guia `LEIA_ME_WINDOWS_EXE.txt`.

## Gerar o EXE neste computador

Abra PowerShell ou Terminal na pasta do projeto e execute:

```powershell
Set-Location -LiteralPath 'C:\Users\liche\Documents\ChatGPT\App persona\bot-marcos'
..\.venv-bot\Scripts\python.exe gerar_exe.py
```

O comando usa o ambiente de desenvolvimento que já foi preparado. Não é
necessário reiniciar nem fechar uma sessão de outro EXE para montar uma
nova versão; porém, não execute dois robôs na mesma conta ao testar.

## Preparar outro computador para desenvolvimento

Somente quem edita e gera o programa precisa de Python. O cliente que
recebe o EXE não precisa instalar Python, Tkinter ou PyInstaller.

No Windows 64 bits, instale Python 3.12 com Tkinter. Na pasta deste código:

```powershell
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\.venv-build\Scripts\python.exe gerar_exe.py
```

O build usa certificados do runtime quando eles existem e inclui o pacote
de CAs do `certifi`. Não remova esses recursos nem desative a verificação TLS.
Uma versão Windows deve ser gerada no Windows; este build não gera `.app`.

## O que o comando entrega

- `dist-windows\BotMarcos.exe`: aplicativo final para o cliente, com o motor e o Python incluídos.
- `dist-windows\BOT_MARCOS_WINDOWS_1.0.19.zip`: pacote com o EXE e `LEIA-ME.txt`.
- `dist-motor\MotorMarcos.exe`: componente interno; não é o arquivo para o cliente abrir.
- `build-*`: arquivos intermediários; não precisam ser enviados ao cliente.

O número do ZIP acompanha `VERSAO` em `caminhos.py`. Distribua o ZIP novo;
um arquivo antigo na pasta Downloads não se atualiza sozinho.

## Verificação antes de distribuir

Execute os testes a partir da pasta do projeto. Os testes de destaque usam
janelas ocultas e entradas fictícias; não se conectam nem enviam ordens.

```powershell
..\.venv-bot\Scripts\python.exe -m unittest test_destaque_entrada test_conexao_iq test_configuracao test_periodo test_entrada test_historico_nuvem -q
```

Em outro computador, substitua o prefixo acima por
`.\.venv-build\Scripts\python.exe`. Os testes de períodos e histórico usam
uma pasta temporária `..\.bot-temp`; crie-a se não existir.

O EXE inclui dois modos de verificação opcionais, sem autenticação ou ordens:

```powershell
Start-Process -Wait -FilePath '.\dist-windows\BotMarcos.exe' -ArgumentList '--autoteste', 'resultado-autoteste.json'
Start-Process -Wait -FilePath '.\dist-windows\BotMarcos.exe' -ArgumentList '--diagnostico-conexao', 'resultado-conexao.json'
```

O primeiro testa interface, destaque com uma entrada fictícia, motor e TLS.
O segundo abre somente o canal público da corretora, sem fazer login.
Confira `ok: true` nos relatórios. Login real e envio de ordens devem ser
validados separadamente, apenas na DEMO com saldo virtual.

## Histórico, dados e Supabase

O EXE guarda parâmetros e fila local em `%LOCALAPPDATA%\BotMarcos`.
A execução por código-fonte guarda esses dados nesta pasta do projeto.
Essas duas pastas locais são diferentes; o histórico já enviado à nuvem
é recuperado após confirmar a mesma conta na corretora.

Nunca inclua CSVs, SQLite, sessões, senhas, `.venv-*` ou configurações pessoais
no pacote do cliente. A chave publicável pode fazer parte do programa;
chaves administrativas devem permanecer somente no servidor Supabase.

Alterar a interface e gerar o EXE não exige publicar novamente a função do
Supabase. Alterações no TypeScript do servidor só entram em vigor depois
de uma publicação separada no projeto correto. Não apague as tabelas para
atualizar o programa. As regras de envio continuam limitadas a PRACTICE/DEMO.

## Seleção de pares e vela da seta (1.0.3)

`configuracao.py` valida e salva `pares`. O painel permite escolher antes de
iniciar a sessão; `aplicar_no_motor` passa essa lista para `motor.ATIVOS`.
O laço do motor consulta somente os escolhidos e ainda verifica a abertura
turbo/binária na corretora. Versões normais e OTC são ativos distintos.

As fórmulas da bolinha e da seta correspondem às condições do General enviado.
A seta usa o fechamento/preço corrente da vela em formação e o deslocamento
do desenho é zero. O robô registra a detecção intrabar e espera o recuo da
abertura dessa mesma vela, com limite de 29 segundos. Sinal contrário cancela.
A detecção neutra posterior não apaga a seta já observada, mas ela pode deixar
de aparecer no indicador ao fechar a vela. Isso não é uma seta confirmada no
fechamento. Não se faz replay de sinais históricos ou entrada na vela seguinte.

Os testes incluem CALL e PUT na mesma vela, recusa de transferência para a
próxima, bloqueios DEMO/REAL, recuo sem seta, sinal contrário e seleção de pares.
É necessário comparar timestamps e gráfico em DEMO; os testes locais não
comprovam correspondência visual em tempo real nem resultados financeiros.

## Abas Início e Atividade ao vivo (1.0.4)

O Início reúne os campos de login, saldo, resultados, histórico, parâmetros
e pares selecionados. O conteúdo permite rolagem em janelas menores.
A confirmação PRACTICE abre a Atividade ao vivo, que mostra os mercados e
eventos somente da sessão atual. Atualizações do Supabase atualizam o resumo
e o histórico de transações sem substituir os eventos ao vivo.
Essa reorganização não altera as regras do motor nem exclui dados salvos.

## Versionamento

Por orientação do responsável pelo projeto, toda alteração concluída deve
ser salva em um commit próprio e enviada ao repositório GitHub configurado.
Inclua os testes e a documentação da mudança. Não versione credenciais,
históricos, ambientes locais ou executáveis gerados.

## Expiração de 30 segundos (1.0.5)

`configuracao.py` aceita 0.5 minuto ou o rótulo `30 segundos`, preservando
as configurações anteriores de 1 a 5 minutos. A interface exibe as unidades.
`expiracao_ordem.py` usa `buy_by_raw_expirations` com produto turbo e
vencimento igual ao segundo inteiro do relógio do servidor mais 30 segundos.
O método `buy` de minutos continua sendo usado somente para 1–5 minutos.
Relógio inválido, conta REAL ou adaptador ausente bloqueiam o envio. Uma
recusa não dispara fallback ou reenvio com outro prazo. O evento
`EXPIRACAO_SOLICITADA` registra o timestamp que pode ser auditado.

O envio é testado com corretora simulada. A aceitação e o vencimento efetivo
devem ser validados na DEMO; o prazo não é garantido por um teste local.
Veja [a referência técnica](referencias/EXPIRACAO_30S.md).

## Parada do executável (1.0.6)

O onefile cria um bootloader e um processo filho. Usar apenas terminate()
no bootloader deixava o motor filho com stdout aberto, mantinha os controles
bloqueados e podia continuar o acompanhamento. `processos.py` usa taskkill
com /T /F no Windows e grupo próprio no macOS, limitado ao PID do motor.
A parada ocorre em uma thread; a interface recebe a confirmação pela fila
e só então volta ao estado parado. Fechar a janela também espera a parada.

`test_botoes.py` exercita os callbacks dos controles, sem login real ou
ordens. O autoteste do EXE inicia um MotorMarcos inerte com --teste-processo,
clica no botão de parada e verifica a ausência do processo filho. Esse modo
inerte não se conecta à corretora e não executa o motor de negociação.

## Disponibilidade e codigos dos pares (1.0.8)

O motor resolve os nomes devolvidos pela propria resposta `turbo.actives`,
aceitando o nome exato selecionado ou sua variante `-op`. OTC nunca e
substituido pelo par normal. O ID vem da chave do instrumento recebido, sem
IDs de variantes fixados no codigo. Nomes ausentes ou divergentes bloqueiam.

Uma unica correspondencia aberta e necessaria. Se duas variantes estiverem
abertas, a resposta e ambigua e nenhuma e escolhida automaticamente. Uma
variante aberta pode substituir a variante legada suspensa do mesmo par.
Abertura exige enabled=true/1 e is_suspended=false/0. Digital/Binary nao
liberam Turbo. Respostas incompletas continuam bloqueadas.

Antes das velas, aplica o ID descoberto ao ACTIVES compartilhado pela SDK.
Get_candles, buy e envio raw de 30 segundos usam assim o mesmo ID.
Troca de ID descarta os sinais anteriores. Uma consulta fechada/desconhecida
limpa o alerta, e a reabertura comeca com velas novas. A consulta e refeita
a cada minuto. Nenhum mapeamento e salvo nas configuracoes do cliente.

O motivo exibido inclui somente nomes de pares permitidos, IDs numericos e
flags de abertura; nunca a resposta integral, credenciais ou sessoes.
Testes simulam a resposta e exercitam os metodos reais da SDK com transporte
falso para conferir os IDs de velas e ordens. A disponibilidade e aceitacao
atuais dependem da resposta da corretora na sessao do cliente.

## Entrada sem recuo (1.0.9)

`sem_recuo` e booleano, persistido e enviado ao motor. Configuracoes antigas
continuam com False. O valor positivo de pips fica preservado para voltar ao
modo com recuo. Nao se usa pips=0 para simular desativacao do filtro.
Quando ativado, SEM_RECUO ignora apenas a comparacao entre preco e alvo.
Bolinha anterior, seta da mesma direcao, cancelamento contrario, prazo de
29 segundos, disponibilidade, PRACTICE e limite por vela continuam obrigatorios.
O evento ENTRADA_SEM_RECUO identifica a condicao atingida; DEMO_ENVIADA
continua dependendo da aceitacao da ordem pela corretora.

## Catalogo de consulta (1.0.10)

`catalogo.py` consulta get-initialization-data v4 (binary/turbo/blitz),
digital-option-instruments.get-underlying-list v3 e get-instruments v4
(forex/cfd/crypto). A resposta v4 e interceptada por request_id exclusivo
antes de chegar aos handlers da SDK, preservando a consulta v3 do motor.
Os endpoints e formatos foram conferidos no codigo da SDK instalada e em
https://github.com/celiovmjr/iq-core/blob/main/iq_core/services/instrument_service.py
Nao ha dependencia nova nem codigo de terceiros executado para isso.

Um worker de consulta e iniciado junto da conta PRACTICE e encerrado com
a sessao. Consultas tem espera limitada e falhas parciais sao publicadas
sem corpo de erro bruto. Nao reconecta nem autentica por conta propria.
A thread publica somente campos permitidos de instrumentos (nome, ticker,
modalidade, grupo, disponibilidade, retorno quando informado).

`catalogo_painel.py` fornece busca, modalidade, OTC, disponibilidade e
watchlist local. Nao altera ACTIVES nem a configuracao de pares. O mesmo
ativo em duas modalidades ocupa duas linhas. Fechar a sessao mantem a ultima
consulta marcada como antiga; uma nova sessao limpa o catalogo anterior.
A lista depende do retorno da conta/regiao e pode diferir dos destaques e
rankings da interface web. Nao inventa percentuais, tendencias ou mercados
que a API nao retornou. Nao habilita negociacao em Blitz/Digital/Margem.

## Selecao de Binarias durante a conexao (1.0.19)

`pares_ao_vivo.py` consulta a lista de Binarias/Turbo a cada 10 segundos
mais tempo de resposta. Blitz/Digital nao entram no seletor. A lista perde
a validade apos 20 segundos sem consulta confirmada. Dados v4 alimentam
a disponibilidade do motor e a checagem imediatamente anterior a ordem.

O stdin do motor permanece aberto depois do envio inicial das credenciais.
Comandos selecionar_pares possuem ID; a interface so aplica e persiste
a selecao depois da confirmacao pares_aplicados. Pedidos com novos ativos
nao confirmados abertos sao recusados. Remover todos deixa a conta conectada
sem novas entradas. Retirar um par bloqueia novas ordens desde o recebimento
do pedido; ordens pendentes continuam sendo acompanhadas.

A fila e consumida pelo loop do motor antes da leitura dos pares. Novos
ativos comecam sem sinais anteriores. Retidos mantem estado; removidos saem
da analise. A categoria binary/turbo e preservada no envio; raw binary usa
o vencimento calculado pela SDK para a expiracao pedida. Trinta segundos
continuam restritos a Turbo. A corretora pode recusar prazo nao oferecido.

O seletor aceita nomes novos da resposta da corretora. A configuracao valida
a sintaxe e tamanho; a disponibilidade e identidade sao verificadas na
sessao. Busca, OTC, so disponiveis, selecionados e marcar visiveis nao
alteram valor, recuo, modo de operacao nem expiracao.

## Correcao do recebimento WebSocket (1.0.19)

O interceptador do catalogo preserva um metodo ligado, conforme o dispatcher do websocket-client instalado. Uma funcao simples recebia um argumento extra e impedia o SDK de processar mensagens normais da conexao. O teste usa WebSocketApp._callback real para verificar tanto mensagens normais quanto respostas correlacionadas do catalogo, sem login ou ordens.

## Respostas de confirmacao do catalogo (1.0.19)

O SDK ativa setOptions(sendResults=True). O coletor agora ignora result/success=True e aguarda a lista correlacionada ao mesmo request_id. Recusas encerram a consulta com ConsultaRecusada, sem divulgar a resposta. Uma confirmacao tardia nao sobrescreve a lista. Testes cobrem ACK antes/depois, ACK sem lista, recusa e limpeza das consultas pendentes. Validacao autenticada depende da sessao do usuario.

## Recuperacao de consultas (1.0.19)
Atualiza Binarias a cada 3s apos resposta e repete apos 1s em falha. Timeout preserva apenas snapshot confirmado com no maximo 20s, sem renovar sua data. Dados expirados, respostas invalidas e recusas invalidam o snapshot. Suspensao recebida substitui imediatamente o estado anterior. O limite pre-ordem de 20s permanece. Testes locais; estabilidade autenticada ainda requer observacao.

## Continuidade do painel (1.0.19)
O timer de consumo da fila agora e reagendado em finally mesmo quando uma mensagem falha. O lote fica limitado a 100 itens para devolver controle ao Tk. Erros exibem apenas a classe da excecao, sem payload ou credenciais. Teste com timer real injeta JSON invalido antes da confirmacao de parada, verifica liberacao do botao Iniciar e atualizacao subsequente. Isso reproduz a vulnerabilidade; o payload causador na sessao original nao foi capturado.

## Atividade ampliada (1.0.19)
Historico com 12 linhas de 34px em pagina rolavel, evitando compressao pela altura da janela. Avisos identicos consecutivos por par nao repetem no historico visual; mudancas continuam visiveis. Registros persistidos permanecem completos. Inclui correcao do timer da 1.0.16.

## Diagnostico de consulta (1.0.19)
Eventos DIAGNOSTICO_CONSULTA registram falhas e recuperacoes com etapa (envio, resposta, recusa ou interpretacao), classe de erro, duracao, ACK e falhas consecutivas. Nao registram payload, texto de excecao, identificador da requisicao ou credenciais. Os registros antigos nao permitem atribuir a causa exata. Esta versao instrumenta o problema, nao declara a instabilidade resolvida.

## Consulta unica em andamento (1.0.19)
Catalogo e monitor usam consultar_opcoes: consumidores simultaneos compartilham o mesmo envio, resultado ou erro; consultas posteriores nao reutilizam cache. Prazo de resposta de 12s (antes 6s no monitor). Confirmacoes para ordens continuam limitadas a 20s. Testes cobrem concorrencia, timeout, liberacao e nova consulta. Os timeouts reais de 16:10-16:11 motivaram a alteracao; nao ha evidencia suficiente para atribuir o atraso a IQ, rede ou limitacao de frequencia. Estabilidade em sessao autenticada ainda pendente.
