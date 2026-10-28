"""Selecao de pares durante a sessao. Nunca seleciona Blitz ou Digital."""
import threading
import time
from configuracao import validar_pares
from catalogo import normalizar_catalogo


def listar_binarias(dados, agora=None):
    linhas = normalizar_catalogo('Opções', dados, agora)
    agrupados = {}
    for item in linhas:
        if item['modalidade'] not in ('Binárias', 'Turbo'):
            continue
        par = item['simbolo'].removesuffix('-op')
        try:
            validar_pares([par])
        except ValueError:
            continue
        atual = agrupados.setdefault(par, {'par': par, 'nome': item['nome'], 'otc': item['otc'],
            'estado': 'Não confirmado', 'modalidades': []})
        atual['modalidades'].append(item['modalidade'])
        if item['estado'] == 'Aberto' or atual['estado'] != 'Aberto' and item['estado'] == 'Fechado':
            atual['estado'] = item['estado']
    return sorted(agrupados.values(), key=lambda x: x['par'].casefold())


class ParesAoVivo:
    def __init__(self, pares, publicar):
        self.pares = list(pares)
        self.publicar = publicar
        self.pendente = None
        self.lock = threading.Lock()
        self.dados = None
        self.consultado_em = 0

    def atualizar_catalogo(self, dados, consultado_em=None):
        with self.lock:
            self.dados = dados
            self.consultado_em = time.time() if consultado_em is None else consultado_em

    def receber(self, comando):
        if not isinstance(comando, dict) or comando.get('tipo') != 'selecionar_pares':
            return
        pedido = comando.get('pedido')
        if not isinstance(pedido, str) or len(pedido) > 80:
            return
        try:
            pares = validar_pares(comando.get('pares'))
            with self.lock:
                self.pendente = (pedido, pares)
        except ValueError:
            self.publicar({'tipo': 'pares_recusados', 'pedido': pedido, 'motivo': 'Lista de pares inválida.'})

    def consumir(self):
        with self.lock:
            pendente = self.pendente
            self.pendente = None
            dados, consultado = self.dados, self.consultado_em
        if pendente is None:
            return None
        pedido, pares = pendente
        novos = set(pares) - set(self.pares)
        if novos:
            disponiveis = {r['par'] for r in listar_binarias(dados or {}) if r['estado'] == 'Aberto'} if dados else set()
            if time.time() - consultado > 20 or not novos <= disponiveis:
                self.publicar({'tipo': 'pares_recusados', 'pedido': pedido,
                    'motivo': 'A lista mudou ou ficou desatualizada. Selecione as Binárias abertas na consulta mais recente.'})
                return None
        self.pares = pares
        self.publicar({'tipo': 'pares_aplicados', 'pedido': pedido, 'pares': pares})
        return pares

    def permite(self, par):
        with self.lock:
            # Um pedido de remocao impede nova ordem mesmo antes do proximo ciclo.
            desejados = self.pendente[1] if self.pendente is not None else self.pares
            return par in self.pares and par in desejados


def acompanhar_binarias(iq, parar, selecao, intervalo=3):
    while not parar.is_set():
        espera = intervalo
        try:
            dados = iq.api.consulta_catalogo.consultar('get-initialization-data', '4.0', {}, timeout=6)
            linhas = listar_binarias(dados)
            consultado = time.time()
            if parar.is_set(): return
            selecao.atualizar_catalogo(dados, consultado)
            selecao.publicar({'tipo': 'binarias_ao_vivo', 'ativos': linhas, 'consultado_em': consultado, 'erro': ''})
        except Exception as erro:
            if parar.is_set(): return
            # Um timeout nao equivale a suspensao. Preserve somente a ultima
            # confirmacao ainda dentro do limite original de 20s, sem renova-lo.
            with selecao.lock:
                anteriores, confirmado = selecao.dados, selecao.consultado_em
            recente = isinstance(erro, TimeoutError) and anteriores is not None and time.time() - confirmado <= 20
            if not recente:
                selecao.atualizar_catalogo(None, 0)
            selecao.publicar({'tipo': 'binarias_ao_vivo',
                             'ativos': listar_binarias(anteriores) if recente else [],
                             'consultado_em': confirmado if recente else 0,
                             'erro': ('Atualização atrasada; repetindo consulta. Última confirmação ainda válida.'
                                      if recente else 'Consulta indisponível: ' + type(erro).__name__)})
            espera = min(intervalo, 1)
        parar.wait(espera)
