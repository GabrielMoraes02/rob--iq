"""Estresse deterministico offline; nao autentica e nao envia ordens."""
import concurrent.futures
import json
import queue
import random
import threading
import unittest
from types import SimpleNamespace
from catalogo import ConsultaCatalogo


class EstresseConsultas(unittest.TestCase):
    def test_400_consultas_concorrentes_respostas_fora_de_ordem(self):
        enviados = queue.Queue()
        api = SimpleNamespace(send_websocket_request=lambda nome, msg, request_id: enviados.put(request_id))
        consulta = ConsultaCatalogo(api)
        rng = random.Random(37)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for rodada in range(50):
                futuros = [pool.submit(consulta.consultar, 'get-initialization-data', '4.0', {}, 2) for _ in range(8)]
                chaves = [enviados.get(timeout=2) for _ in range(8)]
                rng.shuffle(chaves)
                for indice, chave in enumerate(chaves):
                    ack = json.dumps({'name': 'result', 'request_id': chave, 'msg': {'success': True}})
                    if indice % 2: consulta.receber(ack)
                    consulta.receber(json.dumps({'name': 'initialization-data', 'request_id': chave,
                                                'msg': {'marcador': chave, 'rodada': rodada}}))
                    consulta.receber(ack)
                recebidos = [f.result(timeout=2) for f in futuros]
                self.assertEqual({r['marcador'] for r in recebidos}, set(chaves))
                self.assertTrue(all(r['rodada'] == rodada for r in recebidos))
                self.assertEqual(consulta.pendentes, {})

    def test_200_timeouts_respostas_atrasadas_nao_contaminam_recuperacao(self):
        chaves = []
        api = SimpleNamespace(send_websocket_request=lambda nome, msg, request_id: chaves.append(request_id))
        consulta = ConsultaCatalogo(api)
        for _ in range(200):
            with self.assertRaises(TimeoutError):
                consulta.consultar('get-initialization-data', '4.0', {}, timeout=0)
            self.assertEqual(consulta.pendentes, {})
        for chave in chaves:
            self.assertTrue(consulta.receber(json.dumps({'request_id': chave, 'msg': {'antigo': True}})))
        def responder(nome, msg, request_id):
            consulta.receber(json.dumps({'request_id': request_id, 'msg': {'atual': True}}))
        api.send_websocket_request = responder
        self.assertEqual(consulta.consultar('get-initialization-data', '4.0', {}), {'atual': True})
        self.assertEqual(consulta.pendentes, {})

    def test_mensagens_estranhas_nao_encerram_consulta_correta(self):
        api = SimpleNamespace()
        consulta = ConsultaCatalogo(api)
        def responder(nome, msg, request_id):
            for bruto in ('{', 'null', '[]', '42', '{}', '{"request_id":123}', '{"name":"heartbeat","msg":1}'):
                self.assertFalse(consulta.receber(bruto))
            consulta.receber(json.dumps({'request_id': request_id, 'msg': {'ok': True}}))
        api.send_websocket_request = responder
        self.assertEqual(consulta.consultar('get-initialization-data', '4.0', {}), {'ok': True})

