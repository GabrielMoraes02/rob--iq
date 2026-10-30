"""Catalogo somente para consulta. Nao altera ACTIVES, estrategia ou ordens."""
import json
import math
import threading
import time
import unicodedata
import uuid
from types import MethodType

FONTES = (
    ('Opções', 'get-initialization-data', '4.0', {}),
    ('Digital', 'digital-option-instruments.get-underlying-list', '3.0', {'filter_suspended': False}),
    ('Margem Forex', 'get-instruments', '4.0', {'type': 'forex'}),
    ('Margem CFD', 'get-instruments', '4.0', {'type': 'cfd'}),
    ('Margem Cripto', 'get-instruments', '4.0', {'type': 'crypto'}),
)


class ConsultaRecusada(RuntimeError):
    """Recusa da consulta, sem divulgar o corpo retornado pela corretora."""


class RespostaCatalogoInvalida(ValueError):
    pass


class ConsultaCatalogo:
    """Correlacao isolada: respostas v4 nao sobrescrevem a consulta v3 do motor."""
    def __init__(self, api):
        self.api = api
        self.pendentes = {}
        self.lock = threading.Lock()
        self.opcoes_em_andamento = None

    def consultar_opcoes(self, timeout=12):
        """Catalogo e motor compartilham apenas a consulta em andamento, sem cache."""
        with self.lock:
            consulta = self.opcoes_em_andamento
            responsavel = consulta is None
            if responsavel:
                consulta = {'evento': threading.Event()}
                self.opcoes_em_andamento = consulta
        if responsavel:
            try:
                consulta['resposta'] = self.consultar('get-initialization-data', '4.0', {}, timeout=timeout)
            except Exception as erro:
                consulta['erro'] = erro
            finally:
                with self.lock:
                    self.opcoes_em_andamento = None
                    consulta['evento'].set()
        elif not consulta['evento'].wait(timeout):
            erro = TimeoutError('Consulta compartilhada sem resposta')
            erro.diagnostico_catalogo = {'etapa': 'aguardando_consulta_compartilhada',
                                        'duracao_s': timeout, 'ack_recebido': False}
            raise erro
        if 'erro' in consulta:
            raise consulta['erro']
        return consulta['resposta']

    def receber(self, bruto):
        try:
            mensagem = json.loads(bruto)
        except (ValueError, TypeError):
            return False
        if not isinstance(mensagem, dict):
            return False
        chave = mensagem.get('request_id')
        if not isinstance(chave, str) or not chave.startswith('catalogo-'):
            return False
        with self.lock:
            pendente = self.pendentes.get(chave)
            if pendente is not None and not pendente['evento'].is_set():
                # setOptions(sendResults=True) produz um ACK separado da lista.
                # O ACK positivo não conclui a consulta nem substitui seus dados.
                if mensagem.get('name') == 'result':
                    resultado = mensagem.get('msg')
                    if isinstance(resultado, dict) and resultado.get('success') is True:
                        pendente['ack'] = True
                        return True
                    pendente['erro'] = ConsultaRecusada()
                    pendente['evento'].set()
                    return True
                pendente['resposta'] = mensagem.get('msg')
                pendente['evento'].set()
        return True  # inclusive respostas atrasadas, sem interferir no motor

    def consultar(self, nome, versao, corpo, timeout=10):
        if not any((nome, versao, corpo) == (n, v, c) for _, n, v, c in FONTES):
            raise ValueError('Somente consultas de catalogo sao permitidas')
        chave = 'catalogo-' + uuid.uuid4().hex
        pendente = {'evento': threading.Event(), 'ack': False}
        inicio = time.monotonic()
        etapa = 'envio'
        with self.lock:
            self.pendentes[chave] = pendente
        try:
            self.api.send_websocket_request('sendMessage',
                {'name': nome, 'version': versao, 'body': corpo}, request_id=chave)
            etapa = 'aguardando_resposta'
            if not pendente['evento'].wait(timeout):
                raise TimeoutError('Sem resposta do catalogo')
            if 'erro' in pendente:
                etapa = 'recusa'
                raise pendente['erro']
            etapa = 'validacao_resposta'
            resultado = pendente.get('resposta')
            if not isinstance(resultado, dict):
                raise RespostaCatalogoInvalida()
            return resultado
        except Exception as erro:
            # Somente metadados locais: nunca mensagem, request_id ou corpo bruto.
            erro.diagnostico_catalogo = {'etapa': etapa,
                'duracao_s': round(time.monotonic() - inicio, 3),
                'ack_recebido': pendente['ack']}
            raise
        finally:
            with self.lock:
                self.pendentes.pop(chave, None)


def instalar_consulta(api):
    consulta = ConsultaCatalogo(api)
    original = api.websocket.on_message
    def receber(_websocket, *args):
        if args and consulta.receber(args[-1]):
            return
        try:
            return original(*args)
        finally:
            # O SDK deixa a trava de leitura presa se um handler falhar.
            from iqoptionapi import global_value
            global_value.ssl_Mutual_exclusion = False
    # websocket-client 0.56 injeta o socket em funções, mas não em métodos.
    # Preserve o método ligado para não repassar um argumento extra ao SDK.
    api.websocket.on_message = MethodType(receber, api.websocket)
    api.consulta_catalogo = consulta


def texto(valor, limite=160):
    return ''.join(c for c in str(valor or '') if c.isprintable())[:limite]


def numero(valor):
    if isinstance(valor, bool):
        return None
    try:
        n = float(valor)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def disponibilidade(item, agora):
    enabled, suspended = item.get('enabled'), item.get('is_suspended')
    valido = lambda v: type(v) is bool or (type(v) is int and v in (0, 1))
    if (valido(enabled) and not enabled) or (valido(suspended) and suspended):
        return 'Fechado'
    horarios = item.get('schedule', item.get('trading_hours'))
    if isinstance(horarios, list) and horarios:
        intervalos = []
        for h in horarios:
            if isinstance(h, dict):
                inicio, fim = numero(h.get('open', h.get('from'))), numero(h.get('close', h.get('to')))
            elif isinstance(h, (list, tuple)) and len(h) == 2:
                inicio, fim = map(numero, h)
            else:
                return 'Não confirmado'
            if inicio is None or fim is None or fim <= inicio:
                return 'Não confirmado'
            intervalos.append((inicio, fim))
        return 'Aberto' if any(a <= agora < b for a, b in intervalos) else 'Fechado'
    return 'Aberto' if valido(enabled) and enabled and valido(suspended) and not suspended else 'Não confirmado'


def linha(item, codigo, modalidade, grupo, agora):
    simbolo = texto(item.get('name') or item.get('underlying') or item.get('id')).removeprefix('front.')
    if not simbolo or not texto(codigo):
        return None
    titulo = texto(item.get('title') or item.get('display_name') or item.get('description') or simbolo)
    comissao = item.get('option', {}).get('profit', {}).get('commission') if isinstance(item.get('option'), dict) and isinstance(item['option'].get('profit'), dict) else None
    comissao = numero(comissao)
    retorno = 100-comissao if comissao is not None and 0 <= comissao <= 100 else None
    return {'chave': modalidade + ':' + texto(codigo), 'codigo': texto(codigo),
            'simbolo': simbolo, 'nome': titulo, 'modalidade': modalidade,
            'grupo': texto(grupo).removeprefix('front.') or 'Não informado',
            'otc': 'OTC' in simbolo.upper(), 'estado': disponibilidade(item, agora),
            'retorno': retorno}


def normalizar_catalogo(fonte, dados, agora=None):
    agora = time.time() if agora is None else agora
    resultado = {}
    def adicionar(item, codigo, modalidade, grupo):
        if isinstance(item, dict):
            registro = linha(item, codigo, modalidade, grupo, agora)
            if registro:
                resultado[registro['chave']] = registro
    if fonte == 'Opções':
        grupos = dados.get('groups', {})
        grupos = grupos if isinstance(grupos, dict) else {}
        encontrados = 0
        for chave, modalidade in (('binary', 'Binárias'), ('turbo', 'Turbo'), ('blitz', 'Blitz')):
            bloco = dados.get(chave)
            ativos = bloco.get('actives') if isinstance(bloco, dict) else None
            if not isinstance(ativos, dict):
                continue
            encontrados += 1
            for codigo, item in ativos.items():
                if isinstance(item, dict):
                    grupo = grupos.get(str(item.get('group_id')), '')
                    if isinstance(grupo, dict): grupo = grupo.get('name', '')
                    adicionar(item, codigo, modalidade, grupo)
        if not encontrados:
            raise ValueError('Lista de opcoes ausente')
    elif fonte == 'Digital':
        if not isinstance(dados.get('underlying'), list):
            raise ValueError('Lista Digital ausente')
        for item in dados['underlying']:
            if isinstance(item, dict): adicionar(item, item.get('active_id'), 'Digital', item.get('group', ''))
    else:
        if not isinstance(dados.get('instruments'), list):
            raise ValueError('Lista de margem ausente')
        for item in dados['instruments']:
            if isinstance(item, dict): adicionar(item, item.get('id'), fonte, item.get('group', item.get('type', '')))
    return list(resultado.values())


def acompanhar_catalogo(iq, parar, publicar, intervalo=60):
    while not parar.is_set():
        registros, falhas = [], []
        for fonte, nome, versao, corpo in FONTES:
            if parar.is_set(): return
            try:
                if fonte == 'Opções':
                    dados = iq.api.consulta_catalogo.consultar_opcoes()
                else:
                    dados = iq.api.consulta_catalogo.consultar(nome, versao, corpo)
                registros.extend(normalizar_catalogo(fonte, dados))
                if fonte == 'Opções':
                    for categoria in ('binary', 'turbo', 'blitz'):
                        bloco = dados.get(categoria)
                        if not isinstance(bloco, dict) or not isinstance(bloco.get('actives'), dict):
                            falhas.append(categoria + ': lista nao retornada')
            except Exception as erro:
                # Nunca publica resposta bruta ou texto de erro que possa conter sessao.
                falhas.append(fonte + ': ' + type(erro).__name__)
        if not parar.is_set():
            publicar({'tipo': 'catalogo', 'ativos': registros, 'falhas': falhas,
                      'consultado_em': time.time()})
        parar.wait(intervalo)


def pesquisar(valor):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(valor)).casefold() if c.isalnum())


def filtrar(registros, busca='', modalidade='Todas', otc='Todos', estado='Todos', favoritos=None):
    termo = pesquisar(busca)
    return [r for r in registros
            if (not termo or termo in pesquisar(r['nome']+' '+r['simbolo']+' '+r['codigo']))
            and (modalidade == 'Todas' or r['modalidade'] == modalidade
                 or modalidade == 'Opções' and not r['modalidade'].startswith('Margem')
                 or modalidade == 'Margem' and r['modalidade'].startswith('Margem'))
            and (otc == 'Todos' or (otc == 'Só OTC') == r['otc'])
            and (estado == 'Todos' or r['estado'] == estado)
            and (favoritos is None or r['chave'] in favoritos)]
