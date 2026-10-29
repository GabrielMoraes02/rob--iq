"""Parâmetros de operação; nunca guarda credenciais da corretora."""
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

PARES_OTC = ['EURUSD-OTC', 'GBPUSD-OTC', 'USDJPY-OTC', 'EURJPY-OTC', 'GBPJPY-OTC']
PARES_DISPONIVEIS = PARES_OTC + [par.removesuffix('-OTC') for par in PARES_OTC]
PADRAO = {'espera_segundos': 0, 'vela_segundos': 60, 'modo_valor': 'Fixo', 'percentual': 10.0, 'sem_recuo': False, 'pips': 3.0, 'valor': 20.0, 'expiracao': 1, 'pares': PARES_OTC.copy()}
OPCOES_EXPIRACAO = {'30 segundos': 0.5, '1 minuto': 1, '2 minutos': 2,
                    '3 minutos': 3, '4 minutos': 4, '5 minutos': 5}

OPCOES_VELA = {'1 segundo': 1, '5 segundos': 5, '10 segundos': 10, '15 segundos': 15,
               '30 segundos': 30, '1 minuto': 60, '2 minutos': 120, '5 minutos': 300,
               '10 minutos': 600, '15 minutos': 900, '30 minutos': 1800, '1 hora': 3600,
               '2 horas': 7200, '4 horas': 14400, '8 horas': 28800, '12 horas': 43200,
               '1 dia': 86400, '1 semana': 604800, '1 mês (30 dias)': 2592000}


def formatar_vela(segundos):
    return next((nome for nome, valor in OPCOES_VELA.items() if valor == segundos), str(segundos))


def formatar_expiracao(valor):
    try:
        numero = Decimal(str(valor).strip().replace(',', '.'))
    except InvalidOperation:
        return str(valor)
    return next((rotulo for rotulo, minutos in OPCOES_EXPIRACAO.items()
                 if numero == Decimal(str(minutos))), str(valor))


def validar_pares(pares):
    if not isinstance(pares, list) or len(pares) > 1000 or any(
            not isinstance(par, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.&/()# -]{0,95}', par)
            for par in pares):
        raise ValueError('Lista de pares inválida.')
    return list(dict.fromkeys(pares))


def validar_configuracao(dados):
    if not isinstance(dados, dict):
        raise ValueError('Configuração inválida: revise os parâmetros.')
    def numero(chave, titulo):
        try:
            entrada = dados.get(chave, PADRAO[chave])
            if chave == 'vela_segundos':
                entrada = OPCOES_VELA.get(str(entrada).strip(), entrada)
            if chave == 'expiracao':
                entrada = OPCOES_EXPIRACAO.get(str(entrada).strip(), entrada)
            valor = Decimal(str(entrada).strip().replace(',', '.'))
        except InvalidOperation:
            raise ValueError(f'{titulo}: digite um número válido.') from None
        if not valor.is_finite():
            raise ValueError(f'{titulo}: digite um número finito.')
        return valor
    sem_recuo = dados.get('sem_recuo', False)
    if type(sem_recuo) is not bool:
        raise ValueError('Selecione um modo de recuo válido.')
    pips = numero('pips', 'Recuo em pips')
    valor = numero('valor', 'Valor por entrada')
    expiracao = numero('expiracao', 'Expiração')
    if not 0 < pips <= 1000:
        raise ValueError('O recuo deve ser maior que zero e de até 1.000 pips.')
    if not 1 <= valor <= 1000000 or valor != valor.quantize(Decimal('0.01')):
        raise ValueError('O valor deve ser de 1 a 1.000.000, com até duas casas decimais. A corretora ainda pode recusar pelo limite da conta.')
    if expiracao not in {Decimal(str(v)) for v in OPCOES_EXPIRACAO.values()}:
        raise ValueError('Escolha 30 segundos ou de 1 a 5 minutos (binária/turbo).')
    espera = numero('espera_segundos', 'Espera desde o início da vela')
    vela = numero('vela_segundos', 'Duração da vela')
    percentual = numero('percentual', 'Percentual da banca')
    modo_valor = dados.get('modo_valor', 'Fixo')
    if espera != int(espera) or not 0 <= espera <= 29:
        raise ValueError('A espera deve ser de 0 a 29 segundos inteiros.')
    if vela not in OPCOES_VELA.values():
        raise ValueError('Escolha uma duração de vela da lista.')
    if espera >= vela:
        raise ValueError('A espera precisa ser menor que a duração da vela.')
    if modo_valor not in ('Fixo', 'Percentual da banca'):
        raise ValueError('Escolha valor fixo ou percentual da banca.')
    if not 0 < percentual <= 100:
        raise ValueError('O percentual deve ser maior que zero e de até 100%.')
    pares = validar_pares(dados.get('pares', PARES_OTC))
    return {'espera_segundos': int(espera), 'vela_segundos': int(vela), 'modo_valor': modo_valor, 'percentual': float(percentual), 'sem_recuo': sem_recuo, 'pips': float(pips), 'valor': float(valor), 'expiracao': 0.5 if expiracao == Decimal('0.5') else int(expiracao),
            'pares': list(dict.fromkeys(pares))}


def carregar_configuracao(base):
    arquivo = Path(base) / 'configuracao.json'
    if not arquivo.exists():
        return dict(PADRAO)
    return validar_configuracao(json.loads(arquivo.read_text(encoding='utf-8')))


def salvar_configuracao(base, dados):
    dados = validar_configuracao(dados)
    arquivo = Path(base) / 'configuracao.json'
    temporario = arquivo.with_suffix('.json.tmp')
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporario, arquivo)
    return dados


def aplicar_no_motor(motor, dados):
    dados = validar_configuracao(dados)
    motor.ESPERA_SEGUNDOS = dados['espera_segundos']
    motor.VELA_SEGUNDOS = dados['vela_segundos']
    motor.MODO_VALOR = dados['modo_valor']
    motor.PERCENTUAL = dados['percentual']
    motor.VALOR = dados['valor']
    motor.CORRECAO_PIPS = dados['pips']
    motor.SEM_RECUO = dados['sem_recuo']
    motor.EXPIRACAO = dados['expiracao']
    motor.ATIVOS = dados['pares'].copy()
    return dados
