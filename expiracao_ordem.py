"""Envia 30 segundos por timestamp explícito; nunca arredonda para um minuto."""
import math
import time
import uuid


def comprar_binaria_categoria(iq, valor, ativo, direcao, minutos, categoria, comprar_turbo):
    if not iq.check_connect() or iq.get_balance_mode() != 'PRACTICE':
        raise RuntimeError('Conta PRACTICE conectada não confirmada.')
    if categoria == 'turbo':
        return comprar_turbo(valor, ativo, direcao, minutos)
    if categoria != 'binary' or isinstance(minutos, bool) or minutos not in (1, 2, 3, 4, 5):
        raise ValueError('Modalidade ou expiração binária não suportada.')
    from iqoptionapi.expiration import get_expiration_time
    agora = iq.get_server_timestamp()
    if isinstance(agora, bool) or not isinstance(agora, (int, float)) or not math.isfinite(agora) or abs(time.time()-agora) > 3:
        raise RuntimeError('Relógio da corretora desatualizado; ordem bloqueada.')
    vencimento, _ = get_expiration_time(agora, minutos)
    return comprar_por_vencimento_api(iq, valor, ativo, direcao, categoria, vencimento)


def comprar_com_expiracao(iq, valor, ativo, direcao, minutos, registrar=None):
    if not iq.check_connect() or iq.get_balance_mode() != 'PRACTICE':
        raise RuntimeError('Conta PRACTICE conectada não confirmada; ordem bloqueada.')
    if minutos == 0.5:
        comprar = getattr(iq, 'buy_by_raw_expirations', None)
        relogio = getattr(iq, 'get_server_timestamp', None)
        if not callable(comprar) or not callable(relogio):
            raise RuntimeError('API sem suporte ao envio de 30 segundos por vencimento; nenhuma ordem enviada.')
        agora = relogio()
        if isinstance(agora, bool) or not isinstance(agora, (int, float)) or not math.isfinite(agora) or abs(time.time()-agora) > 3:
            raise RuntimeError('Relógio da corretora ausente ou desatualizado; ordem de 30 segundos bloqueada.')
        vencimento = int(agora) + 30
        if registrar is not None:
            registrar(vencimento)
        # Protocolo de vencimento absoluto em segundos da API binária/turbo.
        # O servidor pode recusar prazos não ofertados; não há fallback/reenvio.
        return comprar(valor, ativo, direcao, 'turbo', vencimento)
    if isinstance(minutos, bool) or minutos not in (1, 2, 3, 4, 5):
        raise ValueError('Expiração inválida; nenhuma ordem enviada.')
    return iq.buy(valor, ativo, direcao, int(minutos))


def comprar_por_vencimento_api(iq, valor, ativo, direcao, produto, vencimento, timeout=5):
    """Preserva correlação por ID; a rotina legada reutiliza o ID 'buyraw'."""
    from iqoptionapi.constants import ACTIVES
    if not iq.check_connect() or iq.get_balance_mode() != 'PRACTICE':
        raise RuntimeError('Conta PRACTICE conectada não confirmada.')
    if produto not in ('turbo', 'binary'):
        raise ValueError('Produto não permitido para esta solicitação.')
    req = uuid.uuid4().hex
    api = iq.api
    if not isinstance(api.buy_multi_option, dict):
        api.buy_multi_option = {}
    api.buy_multi_option[req] = None
    try:
        api.buyv3_by_raw_expired(float(valor), ACTIVES[ativo], direcao, produto,
                                 int(vencimento), request_id=req)
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            resposta = api.buy_multi_option.get(req)
            if isinstance(resposta, dict):
                if resposta.get('message'):
                    return False, resposta['message']
                identificador = resposta.get('id')
                if isinstance(identificador, (int, str)) and not isinstance(identificador, bool) and str(identificador).isdigit() and int(identificador) > 0:
                    return True, identificador
            time.sleep(0.05)
        raise TimeoutError('A corretora não confirmou a ordem de 30 segundos. Confira na plataforma; não será reenviada.')
    finally:
        api.buy_multi_option.pop(req, None)
