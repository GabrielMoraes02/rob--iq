import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from catalogo import ConsultaCatalogo, ConsultaRecusada, instalar_consulta, normalizar_catalogo, filtrar, acompanhar_catalogo


def resposta_opcoes():
    item = {'name': 'front.EURUSD-OTC', 'title': 'Euro / Dólar (OTC)',
            'enabled': True, 'is_suspended': False, 'group_id': 1,
            'option': {'profit': {'commission': 10}}, 'senha': 'nao-publicar'}
    return {'groups': {'1': 'forex'}, 'turbo': {'actives': {'76': item}},
            'binary': {'actives': {'76': item}}, 'blitz': {'actives': {'76': item}}}


class Catalogo(unittest.TestCase):
    def test_diagnostico_distingue_envio_e_timeout_sem_payload(self):
        api = Mock()
        consulta = ConsultaCatalogo(api)
        api.send_websocket_request.side_effect = OSError('senha-ou-sessao-secreta')
        with self.assertRaises(OSError) as erro:
            consulta.consultar('get-initialization-data', '4.0', {})
        self.assertEqual(erro.exception.diagnostico_catalogo['etapa'], 'envio')
        self.assertNotIn('secreta', json.dumps(erro.exception.diagnostico_catalogo))
        api.send_websocket_request.side_effect = None
        with self.assertRaises(TimeoutError) as erro:
            consulta.consultar('get-initialization-data', '4.0', {}, timeout=0)
        self.assertEqual(erro.exception.diagnostico_catalogo['etapa'], 'aguardando_resposta')
        self.assertFalse(erro.exception.diagnostico_catalogo['ack_recebido'])

    def test_ack_positivo_nao_substitui_lista_em_nenhuma_ordem(self):
        for ack_primeiro in (True, False):
            with self.subTest(ack_primeiro=ack_primeiro):
                api = Mock()
                consulta = ConsultaCatalogo(api)
                def enviar(nome, msg, request_id):
                    ack = {'name': 'result', 'request_id': request_id, 'msg': {'success': True}}
                    lista = {'name': 'initialization-data', 'request_id': request_id, 'msg': resposta_opcoes()}
                    if ack_primeiro:
                        consulta.receber(json.dumps(ack))
                        self.assertFalse(consulta.pendentes[request_id]['evento'].is_set())
                    consulta.receber(json.dumps(lista))
                    consulta.receber(json.dumps(ack))
                api.send_websocket_request.side_effect = enviar
                self.assertEqual(consulta.consultar('get-initialization-data', '4.0', {}, timeout=.1), resposta_opcoes())

    def test_ack_sem_lista_expira_e_recusa_nao_expoe_resposta(self):
        for sucesso in (True, False):
            api = Mock()
            consulta = ConsultaCatalogo(api)
            def enviar(nome, msg, request_id):
                consulta.receber(json.dumps({'name': 'result', 'request_id': request_id,
                    'msg': {'success': sucesso, 'message': 'segredo-nao-publicar'}}))
            api.send_websocket_request.side_effect = enviar
            with self.assertRaises(TimeoutError if sucesso else ConsultaRecusada) as contexto:
                consulta.consultar('get-initialization-data', '4.0', {}, timeout=.01)
            self.assertNotIn('segredo', str(contexto.exception))
            self.assertEqual(consulta.pendentes, {})

    def test_dispatcher_real_preserva_mensagens_da_conexao(self):
        from websocket import WebSocketApp
        recebidas = []
        class Cliente:
            def on_message(self, mensagem):
                recebidas.append(mensagem)
        socket = WebSocketApp('wss://example.invalid', on_message=Cliente().on_message)
        api = SimpleNamespace(websocket=socket)
        instalar_consulta(api)
        socket._callback(socket.on_message, '{"name":"profile","msg":{}}')
        self.assertEqual(recebidas, ['{"name":"profile","msg":{}}'])
        def enviar(nome, msg, request_id):
            socket._callback(socket.on_message, json.dumps({'request_id': request_id, 'msg': resposta_opcoes()}))
        api.send_websocket_request = enviar
        self.assertEqual(api.consulta_catalogo.consultar('get-initialization-data', '4.0', {}, timeout=.1), resposta_opcoes())
        self.assertEqual(len(recebidas), 1)

    def test_preserva_modalidades_e_whitelist_sem_dados_privados(self):
        linhas = normalizar_catalogo('Opções', resposta_opcoes(), 100)
        self.assertEqual(len(linhas), 3)
        self.assertEqual(len({x['chave'] for x in linhas}), 3)
        self.assertEqual({x['modalidade'] for x in linhas}, {'Binárias', 'Turbo', 'Blitz'})
        self.assertEqual(linhas[0]['retorno'], 90)
        self.assertNotIn('senha', json.dumps(linhas))
        self.assertNotIn('nao-publicar', json.dumps(linhas))

    def test_catalogo_nao_limitado_a_dez_pares(self):
        dados = resposta_opcoes()
        dados['blitz']['actives'] = {str(i): {'name': f'front.Ativo{i}', 'enabled': True, 'is_suspended': False}
                                     for i in range(500)}
        self.assertEqual(len(filtrar(normalizar_catalogo('Opções', dados), modalidade='Blitz')), 500)

    def test_busca_filtros_combinados_e_watchlist(self):
        linhas = normalizar_catalogo('Opções', resposta_opcoes(), 100)
        self.assertEqual(len(filtrar(linhas, 'eur/usd', 'Blitz', 'Só OTC', 'Aberto')), 1)
        self.assertEqual(len(filtrar(linhas, 'dolar', 'Opções')), 3)
        self.assertEqual(filtrar(linhas, otc='Sem OTC'), [])
        self.assertEqual(filtrar(linhas, modalidade='Digital'), [])
        self.assertEqual(len(filtrar(linhas, favoritos={'Blitz:76'})), 1)

    def test_digital_margem_e_estado_desconhecido(self):
        linhas = normalizar_catalogo('Digital', {'underlying': [
            {'active_id': 1, 'underlying': 'EURUSD', 'schedule': [{'open': 50, 'close': 150}]}]}, 100)
        self.assertEqual(linhas[0]['estado'], 'Aberto')
        margem = normalizar_catalogo('Margem CFD', {'instruments': [
            {'id': 'AAPL', 'name': 'Apple', 'trading_hours': [[0, 50]]}]}, 100)
        self.assertEqual(margem[0]['estado'], 'Fechado')
        self.assertIsNone(margem[0]['retorno'])
        self.assertEqual(len(filtrar(margem, modalidade='Margem')), 1)
        linhas = normalizar_catalogo('Digital', {'underlying': [{'active_id': 1, 'underlying': 'EURUSD'}]}, 100)
        self.assertEqual(linhas[0]['estado'], 'Não confirmado')

    def test_transporte_correlacionado_nao_entrega_catalogo_ao_motor(self):
        original = Mock()
        api = SimpleNamespace(websocket=SimpleNamespace(on_message=original))
        instalar_consulta(api)
        def enviar(nome, msg, request_id):
            api.websocket.on_message(json.dumps({'request_id': request_id, 'msg': resposta_opcoes()}))
        api.send_websocket_request = Mock(side_effect=enviar)
        self.assertEqual(api.consulta_catalogo.consultar('get-initialization-data', '4.0', {}), resposta_opcoes())
        original.assert_not_called()
        api.websocket.on_message('mensagem-normal')
        original.assert_called_once_with('mensagem-normal')
        self.assertEqual(api.consulta_catalogo.pendentes, {})
        with self.assertRaises(ValueError):
            api.consulta_catalogo.consultar('binary-options.open-option', '1.0', {})
        self.assertEqual(api.send_websocket_request.call_count, 1)

    def test_timeout_nao_consumido_pelo_motor_e_falha_parcial_explicita(self):
        api = Mock()
        consulta = ConsultaCatalogo(api)
        with self.assertRaises(TimeoutError): consulta.consultar('get-initialization-data', '4.0', {}, timeout=0)
        self.assertEqual(consulta.pendentes, {})
        self.assertTrue(consulta.receber(json.dumps({'request_id': 'catalogo-atrasado', 'msg': {}})))
        parar = threading.Event()
        iq = Mock()
        iq.api.consulta_catalogo.consultar.side_effect = [resposta_opcoes(), TimeoutError(),
            {'instruments': []}, {'instruments': []}, {'instruments': []}]
        publicacoes = []
        def publicar(dados):
            publicacoes.append(dados)
            parar.set()
        acompanhar_catalogo(iq, parar, publicar, intervalo=0)
        self.assertEqual(len(publicacoes[0]['ativos']), 3)
        self.assertEqual(publicacoes[0]['falhas'], ['Digital: TimeoutError'])
        iq.buy.assert_not_called()
        iq.connect.assert_not_called()
