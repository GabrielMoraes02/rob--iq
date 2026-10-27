# MARCOS 2027 V19 CORRECAO 3 PIPS - Tradução de regras do General
# Modo padrao SIMULACAO. Somente PRACTICE permite envio opcional.
# Sinais inferidos de velas; precisam ser comparados com o General visual antes de confiar nas ordens.
import csv
import math
import threading
import os
import sys
import time
from datetime import datetime
from getpass import getpass
from configuracao import formatar_expiracao
from expiracao_ordem import comprar_com_expiracao

ATIVOS = ['EURUSD-OTC', 'GBPUSD-OTC', 'USDJPY-OTC', 'EURJPY-OTC', 'GBPJPY-OTC']
VALOR = 20
EXPIRACAO = 1
LIMITE_SEGUNDO = 29
CORRECAO_PIPS = 3
MARGEM_SEGURANCA = 0   # confirma horario novamente antes da chamada de ordem
PIP_REJEICAO = 0.5
INTERVALO = 1.0
MAX_FALHAS_LEITURA = 3
MAX_RECONEXOES = 3
PAUSA_RECONEXAO = 12
PASTA = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(PASTA, 'V19_GENERAL_3PIPS_OTC_5_EVENTOS.csv')
RESULTADOS = os.path.join(PASTA, 'V19_GENERAL_3PIPS_OTC_5_RESULTADOS.csv')
LOG_LOCK = threading.Lock()
ORDENS_PENDENTES = {}
PEND_LOCK = threading.Lock()


def pip(ativo):
    return 0.01 if 'JPY' in ativo else 0.0001


class Disponibilidade(dict):
    """Estados de abertura e motivos, sem dados pessoais da resposta da API."""
    def __init__(self):
        super().__init__()
        self.motivos = {}


def flag_disponibilidade(valor):
    # JSON booleano e as variantes numericas 0/1 da API; sem bool("false").
    if type(valor) is bool:
        return valor
    if type(valor) is int and valor in (0, 1):
        return bool(valor)
    return None


def interpretar_disponibilidade(dados, codigos, selecionados):
    if not isinstance(dados, dict):
        raise ValueError('Dados de opcoes binarias/turbo nao recebidos da corretora')
    bloco = dados.get('turbo')
    ativos = bloco.get('actives') if isinstance(bloco, dict) else None
    saida = Disponibilidade()
    for nome in selecionados:
        codigo = codigos.get(nome)
        motivo = 'Resposta de Binarias/Turbo incompleta.'
        estado = None
        if codigo is None:
            motivo = 'Codigo do par nao encontrado na biblioteca de ordens.'
        elif isinstance(ativos, dict):
            # O codigo e o mesmo utilizado por get_candles/buy. Nomes podem
            # variar, mas nunca substituimos um instrumento por outro codigo.
            itens = [valor for chave, valor in ativos.items() if str(chave) == str(codigo)]
            if len(itens) != 1 or not isinstance(itens[0], dict):
                motivo = 'Par ausente ou ambiguo na lista de Binarias/Turbo.'
            else:
                item = itens[0]
                habilitado = flag_disponibilidade(item.get('enabled'))
                suspenso = flag_disponibilidade(item.get('is_suspended'))
                if habilitado is False or suspenso is True:
                    estado = False
                    motivo = ('Corretora informou par desabilitado em Binarias/Turbo.'
                              if habilitado is False else 'Corretora informou par suspenso em Binarias/Turbo.')
                elif habilitado is True and suspenso is False:
                    estado = True
                    motivo = 'Abertura confirmada em Binarias/Turbo.'
                else:
                    motivo = 'Corretora nao confirmou os campos de abertura em Binarias/Turbo.'
        saida[nome] = estado
        saida.motivos[nome] = motivo
    return saida


def consultar_abertura_binaria(iq):
    """Consulta Turbo por codigo: True aberto, False fechado, None desconhecido.

    As expiracoes suportadas (30 s a 5 min) usam Turbo. Disponibilidade em
    Digital ou Binary nao autoriza uma ordem Turbo.
    """
    import inspect
    from iqoptionapi.constants import ACTIVES
    metodo = iq.get_all_init_v2
    parametros = inspect.signature(metodo).parameters
    dados = metodo(polling=0.1) if 'polling' in parametros else metodo()
    return interpretar_disponibilidade(dados, ACTIVES, ATIVOS)


def ativo_aberto(iq, ativo, tempos=None):
    if not isinstance(tempos, dict):
        return None
    return tempos.get(ativo)


def escrever(ativo, evento, detalhe=''):
    with LOG_LOCK:
        novo = not os.path.exists(LOG)
        with open(LOG, 'a', encoding='utf-8-sig', newline='') as arquivo:
            w = csv.writer(arquivo, delimiter=';')
            if novo:
                w.writerow(['DATA_HORA', 'ATIVO', 'EVENTO', 'DETALHE'])
            w.writerow([datetime.now().strftime('%d/%m/%Y %H:%M:%S'), ativo, evento, detalhe])
        print(f'[{datetime.now():%H:%M:%S}] {ativo} | {evento} | {detalhe}', flush=True)


def salvar_resultado(ativo, direcao, id_ordem, lucro, resultado):
    with LOG_LOCK:
        novo = not os.path.exists(RESULTADOS)
        with open(RESULTADOS, 'a', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f, delimiter=';')
            if novo:
                w.writerow(['DATA_HORA', 'ATIVO', 'DIRECAO', 'ID_ORDEM', 'RESULTADO', 'LUCRO_LIQUIDO'])
            w.writerow([datetime.now().strftime('%d/%m/%Y %H:%M:%S'), ativo, direcao,
                        id_ordem, resultado, f'{lucro:.2f}'])


def interpretar_resultado(retorno):
    # check_win_v4 desta biblioteca retorna (status, lucro_liquido).
    # Outras versoes retornam somente o valor numerico.
    status = None
    if isinstance(retorno, (tuple, list)):
        if len(retorno) != 2:
            raise ValueError(f'formato de resultado invalido: {retorno!r}')
        status, retorno = retorno
        if status not in ('win', 'loose', 'loss', 'equal'):
            raise ValueError(f'status de resultado desconhecido: {status!r}')
    if isinstance(retorno, bool) or retorno is None:
        raise ValueError(f'resultado nao numerico: {retorno!r}')
    lucro = float(retorno)
    if not math.isfinite(lucro):
        raise ValueError('lucro nao finito')
    if status is not None:
        coerente = ((status == 'win' and lucro > 0)
                    or (status in ('loose', 'loss') and lucro < 0)
                    or (status == 'equal' and lucro == 0))
        if not coerente:
            raise ValueError(f'status e lucro inconsistentes: {status!r}, {lucro}')
    resultado = 'WIN' if lucro > 0 else 'LOSS' if lucro < 0 else 'EMPATE'
    return lucro, resultado


def aguardar_resultado(iq, ativo, direcao, id_ordem):
    # A consulta bloqueia so esta thread, nunca a leitura de outros pares.
    try:
        metodo_resultado = getattr(iq, 'check_win_v4', None)
        if not callable(metodo_resultado):
            raise RuntimeError('check_win_v4 indisponivel nesta biblioteca; confira resultado na corretora')
        lucro, resultado = interpretar_resultado(metodo_resultado(id_ordem))
        salvar_resultado(ativo, direcao, id_ordem, lucro, resultado)
        escrever(ativo, 'RESULTADO_' + resultado, f'id={id_ordem} lucro_liquido={lucro:.2f}')
    except Exception as exc:
        escrever(ativo, 'RESULTADO_NAO_CONFIRMADO', f'id={id_ordem} erro={exc!r}; verificar na plataforma')
    finally:
        with PEND_LOCK:
            ORDENS_PENDENTES.pop(str(id_ordem), None)


def normalizar(v):
    return {
        't': int(v['from']), 'o': float(v['open']),
        'h': float(v['max']), 'l': float(v['min']), 'c': float(v['close'])
    }


def bolinha(v, prev, prev2):
    # Transcricao LITERAL do indicador, inclusive o "open" sem indice
    call = prev['c'] < prev['o'] and v['c'] > v['o'] and v['c'] > prev['h'] and prev2['c'] >= v['o']
    put = prev['c'] > prev['o'] and v['c'] < v['o'] and v['c'] < prev['l'] and prev2['c'] <= v['o']
    return 'CALL' if call else 'PUT' if put else None


def seta(v, prev, prev2, prev3):
    call = v['c'] > prev['c'] and prev['c'] > prev2['o'] and prev3['c'] > prev2['c']
    put = v['c'] < prev['c'] and prev['c'] < prev2['o'] and prev3['c'] < prev2['c']
    return 'CALL' if call else 'PUT' if put else None


def verificar_sinal_historico(velas, ativo):
    # Usa somente velas fechadas, sem filtro de suporte/resistencia.
    i = len(velas) - 1
    if i < 3:
        return None
    atual, ant, ant2, ant3 = velas[i], velas[i-1], velas[i-2], velas[i-3]
    return {'bolinha': bolinha(atual, ant, ant2),
            'seta': seta(atual, ant, ant2, ant3)}


def segundos_m1(agora):
    return agora % 60


def processar(ativo, velas, estado, agora, enviar_ordem, iq, disponibilidade_confirmada=False):
    atual = next((v for v in reversed(velas) if v['t'] <= agora < v['t'] + 60), None)
    if atual is None:
        return
    fechadas = [v for v in velas if v['t'] + 60 <= agora - 0.1]
    if len(fechadas) < 15:
        return
    ultima = fechadas[-1]
    if estado['ultima_fechada'] != ultima['t']:
        novos = [v for v in fechadas if estado['ultima_fechada'] is None or v['t'] > estado['ultima_fechada']]
        estado['ultima_fechada'] = ultima['t']
        for item in novos:
            idx = next((j for j, x in enumerate(fechadas) if x['t'] == item['t']), None)
            if idx is None or idx < 12:
                continue
            info = verificar_sinal_historico(fechadas[:idx+1], ativo)
            # Cada vela fechada e processada UMA vez, inclusive sinais contrarios.
            # Registra o horario exato da vela, e nao apenas o momento da leitura.
            lado_novo = info['bolinha']
            seta_nova = info['seta']
            anterior = estado['alerta']
            if anterior is not None:
                direcao = anterior['lado']
                # Sinal contrario invalida alerta antigo, mesmo depois da seta.
                if (lado_novo and lado_novo != direcao) or (seta_nova and seta_nova != direcao):
                    escrever(ativo, 'CANCELADO_POR_CONTRARIO',
                             f"antigo={direcao} nova_bolinha={lado_novo} nova_seta={seta_nova} candle={item['t']}")
                    estado['alerta'] = None
                    anterior = None
                elif item['t'] >= anterior['t']+60:
                    # A vela da seta acabou; nunca transfere a entrada para a seguinte.
                    escrever(ativo, 'DESCARTADO', f"vela_da_seta_encerrada bolinha_t={anterior['t']} entrada_t={anterior['t']+60}")
                    estado['alerta'] = None
            # Só arma a vela imediatamente após uma bolinha fechada, sem replay.
            if lado_novo and estado['alerta'] is None and item['t']+60 == atual['t']:
                estado['alerta'] = {'lado':lado_novo, 't':item['t'], 'seta':False}
                escrever(ativo, 'BOLINHA_CALCULADA',
                         f"lado={lado_novo} candle={item['t']} fecha_em={item['t']+60}")

    a = estado['alerta']
    if not a:
        return
    # A seta é observada INTRABAR na vela seguinte à bolinha, sem esperar fechar.
    t_entrada = a['t'] + 60
    if agora >= t_entrada + LIMITE_SEGUNDO + 1:
        escrever(ativo, 'DESCARTADO', f'seta_ou_recuo_ausente_ate_segundo_29 pips={CORRECAO_PIPS:g} seta_t={t_entrada} entrada_t={t_entrada}')
        estado['alerta'] = None
        return
    if agora < t_entrada or atual['t'] != t_entrada:
        return
    segundo = agora - t_entrada
    if segundo < 0 or segundo > LIMITE_SEGUNDO:
        return
    if abs(time.time()-agora) > 2:
        escrever(ativo, 'BLOQUEADO', 'dados de tempo desatualizados')
        return
    if any(fechadas[-i]['t'] != t_entrada - i*60 for i in (1, 2, 3)):
        escrever(ativo, 'BLOQUEADO', 'velas_nao_consecutivas_para_calcular_seta')
        return
    seta_atual = seta(atual, fechadas[-1], fechadas[-2], fechadas[-3])
    bolinha_atual = bolinha(atual, fechadas[-1], fechadas[-2])
    if (seta_atual and seta_atual != a['lado']) or (bolinha_atual and bolinha_atual != a['lado']):
        escrever(ativo, 'CANCELADO_POR_CONTRARIO', f"antigo={a['lado']} nova_seta={seta_atual} nova_bolinha={bolinha_atual} candle={atual['t']} intrabar=1")
        estado['alerta'] = None
        return
    if not a['seta']:
        if seta_atual != a['lado']:
            return
        a.update(seta=True, t_seta=atual['t'], preco_seta=atual['c'])
        escrever(ativo, 'SETA_DETECTADA', f"lado={a['lado']} bolinha_t={a['t']} seta_t={atual['t']} entrada_t={t_entrada} segundo={segundo:.1f} preco={atual['c']:.6f} intrabar=1")
    # Após detectar a seta, espera o recuo NA MESMA vela. Um estado neutro
    # posterior não apaga a detecção; sinal contrário cancela, e a janela expira.
    # A seta intrabar pode sumir antes do fechamento do indicador visual.
    referencia = atual['o']
    alvo = (referencia - CORRECAO_PIPS*pip(ativo) if a['lado'] == 'CALL'
            else referencia + CORRECAO_PIPS*pip(ativo))
    # Verifica o ultimo preco informado pela API, nao um extremo antigo da vela.
    # CALL: preco atual precisa estar no alvo ou abaixo; PUT: no alvo ou acima.
    # A consulta por velas nao garante captura do instante exato do toque.
    preco_atual = atual['c']
    corrigiu = (preco_atual <= alvo if a['lado'] == 'CALL' else preco_atual >= alvo)
    if not corrigiu:
        return
    if atual['t'] == estado['ultima_operada']:
        return
    estado['ultima_operada'] = atual['t']
    detalhe = f"{a['lado']} segundo={segundo:.1f} referencia={referencia:.6f} base=abertura_entrada alvo={alvo:.6f} preco_lido={atual['c']:.6f} pips={CORRECAO_PIPS:g} valor={VALOR:.2f} expiracao={EXPIRACAO} seta_t={a['t_seta']} entrada_t={t_entrada} modo=mesma_vela_seta"
    escrever(ativo, 'CORRECAO_PIPS', detalhe + f" bolinha_t={a['t']}")
    if not enviar_ordem:
        escrever(ativo, 'SINAL_SIMULADO', detalhe)
    else:
        try:
            # Nunca permitir operar se a conta nao for PRACTICE.
            if not iq.check_connect() or iq.get_balance_mode() != 'PRACTICE':
                escrever(ativo, 'BLOQUEADO', 'conexao ou conta PRACTICE nao confirmada')
            elif not disponibilidade_confirmada:
                escrever(ativo, 'BLOQUEADO', 'ativo nao confirmado aberto para binaria/turbo')
            elif time.time() - t_entrada > LIMITE_SEGUNDO:
                escrever(ativo, 'FORA_DA_JANELA', '29 segundos excedidos antes de enviar')
            else:
                ok, id_ordem = comprar_com_expiracao(iq, VALOR, ativo, a['lado'].lower(), EXPIRACAO,
                    registrar=lambda vencimento: escrever(ativo, 'EXPIRACAO_SOLICITADA',
                        f'duracao_segundos=30 vencimento_ts={vencimento} produto=turbo sem_fallback=1'))
                escrever(ativo, 'DEMO_ENVIADA' if ok else 'ORDEM_RECUSADA',
                         f'{detalhe} id={id_ordem}')
                if ok and id_ordem:
                    with PEND_LOCK:
                        ORDENS_PENDENTES[str(id_ordem)] = (ativo, a['lado'])
                    threading.Thread(target=aguardar_resultado,
                        args=(iq, ativo, a['lado'], id_ordem), daemon=True).start()
        except Exception as exc:
            escrever(ativo, 'ERRO_ORDEM', repr(exc))
    estado['alerta'] = None


def main():
    print('\nMARCOS 2027 - V19 GENERAL 3 PIPS | PROTOTIPO PARA VALIDACAO')
    print('Bolinha e seta CALCULADAS pelas velas (NAO sao leitura do indicador visual).')
    print(f'Seta intrabar; recuo de {CORRECAO_PIPS:g} pips na mesma vela da seta; ate 29s.')
    print(f'M1, {len(ATIVOS)} pares selecionados, expiracao {formatar_expiracao(EXPIRACAO)}, valor {VALOR:.2f} na moeda da conta, sem MG.')
    escrever('GERAL', 'CONFIGURACAO', f'pips={CORRECAO_PIPS:g} valor={VALOR:.2f} expiracao={EXPIRACAO} pares={",".join(ATIVOS)} modo=mesma_vela_seta')
    print('NAO executar V16 ao mesmo tempo. CTRL+C para sair.\n')
    print('1 = SIMULACAO (PADRAO; SEM ORDENS)')
    print('2 = TESTE DEMO (sinais matematicos NAO validados contra General visual)')
    modo = input('Escolha 1 ou 2 [1]: ').strip() or '1'
    if modo not in ('1','2'):
        print('Opcao invalida.'); return
    envia = modo=='2'
    if envia and input('Para confirmar OPERACOES NA DEMO digite DEMO: ').strip() != 'DEMO':
        print('Sem confirmacao: encerrando.'); return
    print(f'Sem toque no pavio. Correcao configurada: {CORRECAO_PIPS:g} pips. Sem filtro suporte/resistencia.')
    print('Ativos:', ', '.join(ATIVOS))
    print('ATENCAO: sinal Python pode divergir do GENERAL visual; confirme antes de usar ordens.\n')
    print('Resultados so apos confirmacao da corretora.')
    try:
        from iqoptionapi.stable_api import IQ_Option
    except ImportError:
        print('Biblioteca iqoptionapi indisponivel. Instale no seu ambiente Python.')
        return
    email = input('Email da IQ Option: ').strip()
    senha = getpass('Senha (nao aparece na tela): ')
    def criar_sessao():
        # Sempre cria um objeto novo: nao reutiliza WebSocket encerrado.
        nova = IQ_Option(email, senha)
        resultado = nova.connect()
        if not nova.check_connect():
            raise ConnectionError(f'Conexao IQ indisponivel: {resultado!r}')
        nova.change_balance('PRACTICE')
        if nova.get_balance_mode() != 'PRACTICE':
            raise RuntimeError('BLOQUEIO: conta PRACTICE nao confirmada')
        return nova

    try:
        iq = criar_sessao()
    except Exception as exc:
        print('Falha na conexao inicial:', repr(exc)); return
    print('Conta confirmada: PRACTICE. Modo:', 'ORDENS DEMO' if envia else 'SIMULACAO')
    print('Disponibilidade obrigatoria: somente ativos confirmados ABERTOS.')
    print('Sinais sao estimados de velas; ainda requerem comparacao com o General visual.')
    estados = {a:{'ultima_fechada':None,'alerta':None,'ultima_operada':None} for a in ATIVOS}
    ultima_checagem = {a:0 for a in ATIVOS}
    ultima_disponibilidade = {a:0 for a in ATIVOS}
    status_disponibilidade = {a:None for a in ATIVOS}
    falhas_consecutivas = 0
    reconexoes = 0
    cache_disponibilidade = None
    cache_disponibilidade_em = 0
    while True:
        try:
            if not iq.check_connect():
                raise ConnectionError('Conexao IQ encerrada')
            for ativo in ATIVOS:
                agora = time.time()
                if agora - ultima_checagem[ativo] < 1:
                    continue
                ultima_checagem[ativo] = agora
                if agora - ultima_disponibilidade[ativo] >= 60 or ultima_disponibilidade[ativo] == 0:
                    if cache_disponibilidade is None or agora - cache_disponibilidade_em >= 60:
                        try:
                            cache_disponibilidade = consultar_abertura_binaria(iq)
                        except Exception as erro_disp:
                            escrever('GERAL', 'ERRO_DISPONIBILIDADE', repr(erro_disp))
                            cache_disponibilidade = {}
                        cache_disponibilidade_em = agora
                    status_disponibilidade[ativo] = ativo_aberto(iq, ativo, cache_disponibilidade)
                    ultima_disponibilidade[ativo] = agora
                    valor = status_disponibilidade[ativo]
                    situacao = 'ABERTO' if valor is True else 'FECHADO' if valor is False else 'NAO_CONFIRMADA'
                    motivo = getattr(cache_disponibilidade, 'motivos', {}).get(ativo, 'Consulta de abertura indisponivel.')
                    escrever(ativo, 'DISPONIBILIDADE', situacao + '; ' + motivo)
                if status_disponibilidade[ativo] is not True:
                    continue
                try:
                    bruto = iq.get_candles(ativo,60,35,int(agora))
                    if not bruto:
                        falhas_consecutivas += 1
                        escrever(ativo, 'SEM_VELAS', f'falhas consecutivas={falhas_consecutivas}')
                        if falhas_consecutivas >= MAX_FALHAS_LEITURA:
                            raise ConnectionError('Tres leituras sem velas')
                        continue
                    falhas_consecutivas = 0
                    velas = sorted((normalizar(v) for v in bruto), key=lambda x:x['t'])
                    # Primeiro ciclo nao usa alertas historicos.
                    if estados[ativo]['ultima_fechada'] is None:
                        fechadas = [v for v in velas if v['t']+60 <= agora-0.1]
                        if fechadas:
                            estados[ativo]['ultima_fechada'] = fechadas[-1]['t']
                    processar(ativo,velas,estados[ativo],time.time(),envia,iq,status_disponibilidade[ativo] is True)
                except Exception as exc:
                    falhas_consecutivas += 1
                    escrever(ativo,'ERRO_LEITURA',repr(exc))
                    if falhas_consecutivas >= MAX_FALHAS_LEITURA or not iq.check_connect():
                        raise ConnectionError('Falhas de leitura repetidas / WebSocket fechado') from exc
            time.sleep(INTERVALO)
        except (ConnectionError, OSError, AttributeError) as exc:
            escrever('GERAL', 'RECONEXAO_NECESSARIA', repr(exc))
            # Descartar alertas antigos: evita ordem baseada em dados obsoletos.
            for ativo in ATIVOS:
                estados[ativo]['alerta'] = None
                estados[ativo]['ultima_fechada'] = None
                ultima_checagem[ativo] = 0
                ultima_disponibilidade[ativo] = 0
                status_disponibilidade[ativo] = None
            falhas_consecutivas = 0
            cache_disponibilidade = None
            cache_disponibilidade_em = 0
            conectado = False
            while reconexoes < MAX_RECONEXOES and not conectado:
                reconexoes += 1
                escrever('GERAL', 'TENTATIVA_RECONEXAO', f'{reconexoes}/{MAX_RECONEXOES}')
                time.sleep(PAUSA_RECONEXAO)
                try:
                    iq = criar_sessao()
                    conectado = True
                    escrever('GERAL', 'RECONECTADO', 'PRACTICE confirmada; sinais antigos descartados')
                    reconexoes = 0
                except Exception as err:
                    escrever('GERAL', 'FALHA_RECONEXAO', repr(err))
            if not conectado:
                escrever('GERAL', 'ENCERRADO_SEGURO', 'Tres tentativas sem conexao; nao enviou novas ordens')
                return
        except KeyboardInterrupt:
            print('V19 encerrado. CSV:',LOG)
            return


if __name__ == '__main__':
    main()
