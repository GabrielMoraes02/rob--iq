# Código-fonte do Bot Marcos — Windows 1.0.3

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
- `dist-windows\BOT_MARCOS_WINDOWS_1.0.3.zip`: pacote com o EXE e `LEIA-ME.txt`.
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
