"""Resultado confirmado por ID, com espera limitada e recuperacao pelo historico."""
import math
import threading
import time

_HISTORICO_LOCK = threading.Lock()


def extrair(item):
    status = item.get('win')
    if status == 'equal':
        return status, 0.0
    aposta = float(item.get('sum', item.get('amount')))
    if status in ('loose', 'loss'):
        lucro = -aposta
    elif status == 'win':
        lucro = float(item['win_amount']) - aposta
    else:
        raise ValueError('Resultado ainda nao confirmado')
    if not math.isfinite(lucro) or aposta <= 0:
        raise ValueError('Valores de resultado invalidos')
    return status, lucro


def buscar_historico(iq, oid, timeout=3):
    if not _HISTORICO_LOCK.acquire(timeout=timeout):
        return None
    try:
        iq.api.get_options_v2_data = None
        iq.api.get_options_v2(100, 'binary,turbo')
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            resposta = iq.api.get_options_v2_data
            if isinstance(resposta, dict):
                for item in resposta.get('msg', {}).get('closed_options', []):
                    ids = item.get('id', [])
                    if not isinstance(ids, list):
                        ids = [ids]
                    if str(oid) in [str(x) for x in ids]:
                        return extrair(item)
                return None
            time.sleep(0.1)
    finally:
        _HISTORICO_LOCK.release()
    return None


def aguardar(iq, oid, timeout=660):
    limite = time.monotonic() + timeout
    proxima_consulta = time.monotonic() + 15
    while time.monotonic() < limite:
        for chave in (oid, str(oid)):
            mensagem = iq.api.socket_option_closed.get(chave)
            if isinstance(mensagem, dict):
                return extrair(mensagem['msg'])
        if time.monotonic() >= proxima_consulta:
            try:
                if iq.check_connect():
                    resultado = buscar_historico(iq, oid, timeout=min(3, max(0, limite-time.monotonic())))
                    if resultado is not None:
                        return resultado
            except (OSError, ValueError, KeyError, TypeError):
                pass
            proxima_consulta = time.monotonic() + 15
        time.sleep(0.2)
    raise TimeoutError('Resultado nao confirmado no prazo; confira o ID na corretora. Nenhuma ordem reenviada.')
