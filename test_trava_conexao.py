import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from iqoptionapi import global_value
from conexao_iq import enviar_com_trava_segura

class TravaConexao(unittest.TestCase):
    def setUp(self):
        global_value.ssl_Mutual_exclusion=False
        global_value.ssl_Mutual_exclusion_write=False
    def tearDown(self):self.setUp()
    def test_envio_falha_e_proximo_nao_trava(self):
        api=SimpleNamespace(websocket=Mock())
        api.websocket.send.side_effect=[OSError('closed'),None]
        with self.assertRaises(OSError):enviar_com_trava_segura(api,'consulta',{})
        self.assertFalse(global_value.ssl_Mutual_exclusion_write)
        enviar_com_trava_segura(api,'consulta',{})
        self.assertEqual(api.websocket.send.call_count,2)
    def test_trava_ocupada_expira_sem_enviar(self):
        global_value.ssl_Mutual_exclusion=True
        api=SimpleNamespace(websocket=Mock())
        with patch('time.monotonic',side_effect=[0,6]),self.assertRaises(TimeoutError):
            enviar_com_trava_segura(api,'consulta',{})
        api.websocket.send.assert_not_called()

    def test_envios_concorrentes_nao_se_sobrepoem(self):
        import threading,time
        from concurrent.futures import ThreadPoolExecutor
        controle=threading.Lock()
        ativos=0
        maior=0
        total=0
        def enviar(_):
            nonlocal ativos,maior,total
            with controle:
                ativos+=1
                maior=max(maior,ativos)
            time.sleep(0.002)
            with controle:
                ativos-=1
                total+=1
        api=SimpleNamespace(websocket=SimpleNamespace(send=enviar))
        with ThreadPoolExecutor(max_workers=12) as executor:
            list(executor.map(lambda i:enviar_com_trava_segura(api,'consulta',{'i':i}),range(40)))
        self.assertEqual(maior,1)
        self.assertEqual(total,40)
