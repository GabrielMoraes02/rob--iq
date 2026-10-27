"""Consulta de saldo demo com prazo limitado; nao envia ordens."""
import math
import time


def consultar_saldo_demo(iq, balance_id, timeout=4.0, detalhado=False):
    if not iq.check_connect() or iq.get_balance_mode() != 'PRACTICE':
        raise RuntimeError('Conta demo ou conexao nao confirmada')
    iq.api.balances_raw = None
    iq.api.get_balances()
    prazo = time.monotonic() + timeout
    while iq.api.balances_raw is None:
        if time.monotonic() >= prazo:
            raise TimeoutError('Saldo nao recebido dentro do prazo')
        time.sleep(0.05)
    for conta in iq.api.balances_raw['msg']:
        if str(conta['id']) == str(balance_id):
            if conta.get('type', 4) != 4:
                raise RuntimeError('Saldo recebido nao pertence a conta demo')
            valor = float(conta['amount'])
            if not math.isfinite(valor):
                raise ValueError('Saldo invalido')
            return {'valor': valor, 'moeda': str(conta.get('currency', 'não informada')), 'conta': str(conta['id']), 'consultado_em': time.time()} if detalhado else valor
    raise ValueError('Saldo da conta selecionada nao encontrado')
