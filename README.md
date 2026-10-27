# Bot Marcos

Aplicativo Windows para acompanhamento de sinais do General e operações
automáticas na conta **PRACTICE/DEMO**, com saldo virtual. Versão atual: **1.0.6**.

- Início com login, saldo, histórico e parâmetros; Atividade ao vivo para a sessão atual.
- Escolha dos pares OTC e normais antes de iniciar a sessão.
- Detecção da seta na vela em formação, com recuo e entrada na mesma vela
  até o segundo 29. Oportunidades vencidas não passam para a próxima vela.
- Destaque do par, direção, valor, horário e resultado na interface.
- Histórico futuro por conta, com fila local e sincronização com Supabase.
- Executável com Python, Tkinter, dependências e motor incluídos.

## Para o cliente

Use o pacote `BOT_MARCOS_WINDOWS_1.0.6.zip`, extraia e abra `BotMarcos.exe`.
Não é necessário instalar Python. Veja [o guia de uso](LEIA_ME_WINDOWS_EXE.txt).

## Para editar ou gerar uma versão

A interface está em [painel.py](painel.py). As regras de entrada estão em
[MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py](MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py).
Consulte [README_DESENVOLVEDOR.md](README_DESENVOLVEDOR.md) para configurar o
ambiente, rodar os testes e gerar o executável com `gerar_exe.py`.

As condições do indicador fornecido estão documentadas em
[referencias/GENERAL_REGRAS.md](referencias/GENERAL_REGRAS.md).
Uma seta intrabar pode desaparecer antes do fechamento; ela não equivale
a uma seta confirmada no fechamento. O robô calcula os sinais com as velas
da API, e sua correspondência com o gráfico deve ser conferida na DEMO.

## Dados e acesso

Senhas, sessões, históricos de clientes, configurações pessoais, ambientes
virtuais e binários gerados não fazem parte do código versionado. O programa
cliente contém apenas a chave publicável do Supabase. Chaves administrativas
ficam exclusivamente no servidor. Não publique arquivos de dados locais.
