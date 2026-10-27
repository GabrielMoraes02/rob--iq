import importlib.util
import json
import sys
from pathlib import Path
from caminhos import pasta_recursos, pasta_dados
from catalogo import acompanhar_catalogo
import expiracao_ordem  # Inclui o adaptador no motor empacotado.

if '--teste-processo' in sys.argv:
    # Processo inerte para testar a parada do EXE sem autenticação ou ordens.
    import os
    import time
    print(json.dumps({'teste_processo': True, 'pid': os.getpid()}), flush=True)
    while True:
        time.sleep(1)

if '--diagnostico-conexao' in sys.argv:
    from conexao_iq import diagnosticar_transporte
    print(json.dumps(diagnosticar_transporte()), flush=True)
    sys.exit(0)

if '--autoteste' in sys.argv:
    import requests
    import websocket
    import sqlite3
    import certifi
    import ssl
    from iqoptionapi.stable_api import IQ_Option
    from configuracao import PADRAO
    from historico_nuvem import Historico
    from saldo_painel import consultar_saldo_demo
    assert (pasta_recursos() / 'MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py').is_file()
    spec_teste = importlib.util.spec_from_file_location('motor_autoteste',
        pasta_recursos() / 'MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py')
    motor_teste = importlib.util.module_from_spec(spec_teste)
    spec_teste.loader.exec_module(motor_teste)
    from iqoptionapi.constants import ACTIVES
    resposta = {'turbo': {'actives': {str(ACTIVES['EURUSD']):
        {'name': 'front.EURUSD', 'enabled': 1, 'is_suspended': 0}}}}
    assert motor_teste.interpretar_disponibilidade(resposta, ['EURUSD'])['EURUSD'] is True
    resposta['turbo']['actives'][str(ACTIVES['EURUSD'])].pop('is_suspended')
    assert motor_teste.interpretar_disponibilidade(resposta, ['EURUSD'])['EURUSD'] is None
    assert Path(certifi.where()).is_file()
    contexto = ssl.create_default_context(cafile=certifi.where())
    print(json.dumps({'ok': True, 'frozen': bool(getattr(sys, 'frozen', False)),
        'corretora_importada': True, 'disponibilidade_testada': True, 'sqlite': sqlite3.sqlite_version,
        'requests': requests.__version__, 'certificados': True,
        'tls_inicializado': contexto.verify_mode == ssl.CERT_REQUIRED,
        'sem_conexao_e_sem_ordens': True}), flush=True)
    sys.exit(0)

# Credenciais recebidas apenas pela entrada do processo, sem arquivo ou argumento.
dados = json.loads(sys.stdin.readline())
arquivo = pasta_recursos() / 'MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py'
spec = importlib.util.spec_from_file_location('motor_marcos', arquivo)
motor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motor)
from configuracao import aplicar_no_motor
from historico_nuvem import Historico
from datetime import datetime
aplicar_no_motor(motor, dados.get('configuracao', {}))
historico = None
# Os CSVs legados não recebem novos dados e nunca são importados.
pasta_pendente = pasta_dados() / 'historico_contas' / 'sem_identidade'
pasta_pendente.mkdir(parents=True, exist_ok=True)
motor.LOG = str(pasta_pendente / 'EVENTOS.csv')
motor.RESULTADOS = str(pasta_pendente / 'RESULTADOS.csv')
demo = dados.get('modo') == 'demo'
respostas = iter(['2', 'DEMO', dados['email']] if demo else ['1', dados['email']])
motor.input = lambda prompt='': next(respostas)
motor.getpass = lambda prompt='': dados.pop('senha')
# Saldo consultado na corretora; resultados da sessao separados do saldo total.
from iqoptionapi import stable_api
from conexao_iq import instalar_compatibilidade
instalar_compatibilidade(stable_api)
import math
import threading
from saldo_painel import consultar_saldo_demo

saida_lock = threading.Lock()
def publicar(dados):
    with saida_lock:
        print('__PAINEL__' + json.dumps(dados), flush=True)

saldo_stop = None
saldo_agora = None

def acompanhar_saldo(iq, parar, atualizar):
    while not parar.is_set():
        atualizar.clear()
        try:
            detalhes = consultar_saldo_demo(iq, stable_api.global_value.balance_id, detalhado=True)
            if not parar.is_set():
                publicar({'tipo': 'saldo', **detalhes})
        except Exception as erro:
            if not parar.is_set():
                publicar({'tipo': 'saldo_erro', 'motivo': type(erro).__name__})
        # Atualiza periodicamente e logo apos um resultado confirmado.
        atualizar.wait(3.0)

ClasseOriginal = stable_api.IQ_Option
class ContaPainel(ClasseOriginal):
    def buy_by_raw_expirations(self, price, active, direction, option, expired):
        return expiracao_ordem.comprar_por_vencimento_api(self, price, active, direction, option, expired)

    def change_balance(self, tipo):
        global saldo_stop, saldo_agora
        if saldo_stop is not None:
            saldo_stop.set()
            saldo_agora.set()
        retorno = super().change_balance(tipo)
        if tipo == 'PRACTICE' and self.get_balance_mode() == 'PRACTICE':
            global historico
            perfil = self.api.profile.msg
            conta = str(perfil.get('user_id', perfil.get('id', ''))) if isinstance(perfil, dict) else ''
            try:
                historico = Historico(pasta_dados(), conta)
                motor.LOG = str(historico.pasta / 'EVENTOS.csv')
                motor.RESULTADOS = str(historico.pasta / 'RESULTADOS.csv')
                # IPC em memória; a sessão não é escrita em arquivos.
                publicar({'tipo': 'conta_historico', 'conta': conta, 'ssid': stable_api.global_value.SSID})
            except (ValueError, OSError):
                publicar({'tipo': 'historico_erro'})
            saldo_stop = threading.Event()
            saldo_agora = threading.Event()
            threading.Thread(target=acompanhar_catalogo,
                             args=(self, saldo_stop, publicar), daemon=True).start()
            threading.Thread(target=acompanhar_saldo,
                             args=(self, saldo_stop, saldo_agora), daemon=True).start()
        return retorno
stable_api.IQ_Option = ContaPainel
escrever_original = motor.escrever

def escrever(ativo, evento, detalhe=''):
    escrever_original(ativo, evento, detalhe)
    if historico is not None:
        historico.registrar('evento', {'DATA_HORA': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'ATIVO': str(ativo), 'EVENTO': str(evento), 'DETALHE': str(detalhe)})

motor.escrever = escrever
salvar_original = motor.salvar_resultado
def salvar(ativo, direcao, id_ordem, lucro, resultado):
    salvar_original(ativo, direcao, id_ordem, lucro, resultado)
    if historico is not None:
        historico.registrar('resultado', {'DATA_HORA': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'ATIVO': str(ativo), 'DIRECAO': str(direcao), 'ID_ORDEM': str(id_ordem),
            'RESULTADO': str(resultado), 'LUCRO_LIQUIDO': f'{lucro:.2f}'})
    publicar({'tipo': 'resultado', 'id': str(id_ordem), 'lucro': lucro, 'resultado': resultado})
motor.salvar_resultado = salvar
aguardar_original = motor.aguardar_resultado
def aguardar(iq, ativo, direcao, id_ordem):
    aguardar_original(iq, ativo, direcao, id_ordem)
    if saldo_agora is not None:
        saldo_agora.set()
motor.aguardar_resultado = aguardar
motor.main()
