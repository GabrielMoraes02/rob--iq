import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from conexao_iq import consultar_velas_limitado, transporte_ativo
from iqoptionapi import global_value

class Recuperacao(unittest.TestCase):
    def iq(self):
        api=SimpleNamespace(candles=SimpleNamespace(candles_data=None),getcandles=Mock())
        return SimpleNamespace(api=api,check_connect=Mock(return_value=True))
    def test_velas_recebidas_sem_relogin(self):
        iq=self.iq()
        def receber(*args):iq.api.candles.candles_data=[{'from':123}]
        iq.api.getcandles.side_effect=receber
        self.assertEqual(consultar_velas_limitado(iq,'EURUSD',60,35,123),[{'from':123}])
    def test_resposta_apos_cinco_segundos_nao_derruba_sessao(self):
        iq=self.iq()
        def responder(_):
            iq.api.candles.candles_data=[{'from':123}]
        with patch('time.monotonic',side_effect=[0,1,6]),patch('time.sleep',side_effect=responder):
            self.assertEqual(consultar_velas_limitado(iq,'EURUSD',60,35,123),[{'from':123}])
        iq.api.getcandles.assert_called_once()
    def test_prazo_continua_limitado_em_quinze_segundos(self):
        iq=self.iq()
        with patch('time.monotonic',side_effect=[0,16]),self.assertRaises(ConnectionError):
            consultar_velas_limitado(iq,'EURUSD',60,35,123)

    def test_socket_fechado_mesmo_com_flag_antiga(self):
        iq=self.iq();iq.api.websocket=SimpleNamespace(sock=SimpleNamespace(connected=False))
        with patch.object(global_value,'check_websocket_if_connect',1):
            self.assertFalse(transporte_ativo(iq))
    def test_sem_resposta_sai_para_reconexao(self):
        iq=self.iq()
        with self.assertRaises(ConnectionError):consultar_velas_limitado(iq,'EURUSD',60,35,123,timeout=0)
        iq.api.getcandles.assert_called_once()
    def test_queda_durante_espera(self):
        iq=self.iq();iq.check_connect.side_effect=[True,False]
        with self.assertRaises(ConnectionError):consultar_velas_limitado(iq,'EURUSD',60,35,123)
    def test_consulta_nao_inicia_desconectada(self):
        iq=self.iq();iq.check_connect.return_value=False
        with self.assertRaises(ConnectionError):consultar_velas_limitado(iq,'EURUSD',60,35,123)
        iq.api.getcandles.assert_not_called()
