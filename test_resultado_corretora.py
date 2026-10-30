import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from resultado_corretora import aguardar, buscar_historico, extrair

class ResultadoRecuperado(unittest.TestCase):
    def iq(self):
        api=SimpleNamespace(socket_option_closed={},get_options_v2_data=None)
        return SimpleNamespace(api=api,check_connect=lambda:True)
    def test_evento_por_id_string(self):
        iq=self.iq();iq.api.socket_option_closed['123']={'msg':{'win':'win','sum':1,'win_amount':1.85}}
        self.assertAlmostEqual(aguardar(iq,123,1)[1],0.85)
    def test_historico_recupera_id_certo(self):
        iq=self.iq()
        def responder(*args):
            iq.api.get_options_v2_data={'msg':{'closed_options':[{'id':[999],'win':'win','amount':10,'win_amount':19},{'id':[123],'win':'win','amount':1,'win_amount':1.85}]}}
        iq.api.get_options_v2=responder
        self.assertAlmostEqual(buscar_historico(iq,123)[1],0.85)
        self.assertIsNone(buscar_historico(iq,124))
    def test_prazo_expira_sem_inventar_resultado(self):
        with self.assertRaises(TimeoutError):aguardar(self.iq(),123,0)
    def test_loss_empate_e_invalido(self):
        self.assertEqual(extrair({'win':'loose','sum':2}),('loose',-2))
        self.assertEqual(extrair({'win':'equal'}),('equal',0))
        with self.assertRaises(ValueError):extrair({'win':'pending','sum':1})
