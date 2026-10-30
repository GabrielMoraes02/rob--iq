import json
import ssl
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from conexao_iq import instalar_compatibilidade


class Conexao(unittest.TestCase):
    def api(self, resposta):
        class Original:
            def connect(self): return resposta
            def close(self): self.fechado = True
            @property
            def websocket(self): return self.websocket_client.wss
        stable = SimpleNamespace(IQOptionAPI=Original)
        instalar_compatibilidade(stable)
        return stable.IQOptionAPI()

    def test_ping_encerra_sem_isalive_removido(self):
        import threading
        from websocket import _app
        from conexao_iq import compatibilizar_thread_websocket
        compatibilizar_thread_websocket()
        self.assertFalse(hasattr(threading.Thread,'isAlive'))
        erros=[]
        app=_app.WebSocketApp('wss://exemplo.test',on_error=lambda *args:erros.append(type(args[-1]).__name__))
        app.on_open=lambda *args:setattr(app,'keep_running',False)
        dispatcher=Mock()
        dispatcher.read.side_effect=lambda sock,read,check:read()
        with patch.object(_app,'WebSocket') as socket:
            app.run_forever(ping_interval=20,ping_timeout=10,dispatcher=dispatcher)
            socket.return_value.close.assert_called()
        self.assertEqual(erros,[])
        self.assertIsNone(app.sock)

    def test_erro_nao_json_nao_mascara_causa(self):
        for motivo in ('[Errno 11001] getaddrinfo failed', '[Errno 2] No such file or directory', '', None):
            with self.subTest(motivo=motivo):
                ok, texto = self.api((False, motivo)).connect()
                self.assertFalse(ok)
                self.assertEqual(json.loads(texto)['code'], 'connection_error')

    def test_preserva_verificacao_e_sucesso(self):
        motivo = json.dumps({'code': 'verify', 'token': 'token-simulado'})
        self.assertEqual(self.api((False, motivo)).connect(), (False, motivo))
        self.assertEqual(self.api((True, None)).connect(), (True, None))

    def test_certificados_absolutos_e_tls_verificado(self):
        from iqoptionapi import global_value
        with patch('iqoptionapi.api.WebsocketClient', return_value=SimpleNamespace(wss=Mock())), patch('threading.Thread') as thread:
            def abrir(): global_value.check_websocket_if_connect = 1
            thread.return_value.start.side_effect = abrir
            self.assertEqual(self.api((True,None)).start_websocket(), (True,None))
            self.assertEqual(thread.call_args.kwargs['kwargs']['ping_interval'],20)
            self.assertEqual(thread.call_args.kwargs['kwargs']['ping_timeout'],10)
            opcoes = thread.call_args.kwargs['kwargs']['sslopt']
            self.assertEqual(opcoes['cert_reqs'], ssl.CERT_REQUIRED)
            self.assertTrue(opcoes['check_hostname'])
            self.assertTrue(Path(opcoes['ca_certs']).is_absolute())
            self.assertTrue(Path(opcoes['ca_certs']).is_file())


if __name__ == '__main__': unittest.main()
