import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from configuracao import validar_configuracao, salvar_configuracao, carregar_configuracao, formatar_expiracao
from expiracao_ordem import comprar_com_expiracao, comprar_por_vencimento_api


class Expiracao(unittest.TestCase):
    def corretora(self):
        iq = Mock()
        iq.check_connect.return_value = True
        iq.get_balance_mode.return_value = 'PRACTICE'
        iq.get_server_timestamp.return_value = 1800000009
        iq.buy_by_raw_expirations.return_value = (True, 123)
        return iq

    def test_30_segundos_e_configuracoes_antigas(self):
        for valor in ('30 segundos', '0,5', 0.5):
            self.assertEqual(validar_configuracao({'expiracao': valor})['expiracao'], 0.5)
        for minutos in range(1, 6):
            self.assertEqual(validar_configuracao({'expiracao': minutos})['expiracao'], minutos)
        self.assertEqual(formatar_expiracao(0.5), '30 segundos')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.bot-temp') as pasta:
            salvar_configuracao(pasta, {'expiracao': '30 segundos'})
            self.assertEqual(carregar_configuracao(pasta)['expiracao'], 0.5)

    def test_envia_timestamp_explicito_sem_arredondar_para_minuto(self):
        iq = self.corretora()
        registrar = Mock()
        with patch('expiracao_ordem.time.time', return_value=1800000009):
            self.assertEqual(comprar_com_expiracao(iq, 20, 'EURUSD', 'call', 0.5, registrar), (True, 123))
        iq.buy_by_raw_expirations.assert_called_once_with(20, 'EURUSD', 'call', 'turbo', 1800000039)
        registrar.assert_called_once_with(1800000039)
        iq.buy.assert_not_called()

    def test_recusa_nao_dispara_fallback(self):
        iq = self.corretora()
        iq.buy_by_raw_expirations.return_value = (False, 'expiration unavailable')
        with patch('expiracao_ordem.time.time', return_value=1800000009):
            self.assertEqual(comprar_com_expiracao(iq, 20, 'EURUSD', 'put', 0.5), (False, 'expiration unavailable'))
        iq.buy.assert_not_called()
        self.assertEqual(iq.buy_by_raw_expirations.call_count, 1)

    def test_relogio_invalido_bloqueia_sem_ordem(self):
        for valor in (None, True, float('nan'), 1800000000):
            iq = self.corretora()
            iq.get_server_timestamp.return_value = valor
            with patch('expiracao_ordem.time.time', return_value=1800000009), self.assertRaises(RuntimeError):
                comprar_com_expiracao(iq, 20, 'EURUSD', 'call', 0.5)
            iq.buy_by_raw_expirations.assert_not_called()
            iq.buy.assert_not_called()

    def test_bloqueia_conta_real_e_preserva_envio_de_minutos(self):
        iq = self.corretora()
        iq.get_balance_mode.return_value = 'REAL'
        with self.assertRaises(RuntimeError): comprar_com_expiracao(iq, 20, 'EURUSD', 'call', 0.5)
        iq.buy_by_raw_expirations.assert_not_called()
        iq.get_balance_mode.return_value = 'PRACTICE'
        comprar_com_expiracao(iq, 20, 'EURUSD', 'call', 3)
        iq.buy.assert_called_once_with(20, 'EURUSD', 'call', 3)

    def test_interface_mostra_30_segundos_no_destaque(self):
        from painel import Painel
        root = tk.Tk()
        root.withdraw()
        try:
            app = Painel(root)
            app.config_expiracao.set('30 segundos')
            self.assertEqual(app.parametros_digitados()['expiracao'], 0.5)
            app.destacar_entrada('12:00:00', 'EURUSD', 'CALL valor=20.00 expiracao=0.5 id=teste')
            self.assertIn('Expiração 30 segundos', app.entrada_info.get())
            self.assertNotIn('0.5 min', app.entrada_info.get())
        finally:
            for timer in root.tk.call('after', 'info'): root.after_cancel(timer)
            root.destroy()

    def test_resposta_correlacionada_por_requisicao_unica(self):
        from types import SimpleNamespace
        iq = self.corretora()
        iq.api = SimpleNamespace(buy_multi_option={'antigo': {'id': 999}})
        enviados = []
        def enviar(*args, request_id):
            enviados.append(request_id)
            iq.api.buy_multi_option[request_id] = {'id': 123}
        iq.api.buyv3_by_raw_expired = enviar
        for _ in range(2):
            self.assertEqual(comprar_por_vencimento_api(iq, 20, 'EURUSD', 'call', 'turbo', 1800000039), (True, 123))
        self.assertEqual(len(set(enviados)), 2)
        self.assertEqual(iq.api.buy_multi_option, {'antigo': {'id': 999}})

    def test_timeout_nao_reenvia_nem_declara_recusa(self):
        from types import SimpleNamespace
        iq = self.corretora()
        iq.api = SimpleNamespace(buy_multi_option={}, buyv3_by_raw_expired=Mock())
        with self.assertRaises(TimeoutError):
            comprar_por_vencimento_api(iq, 20, 'EURUSD', 'put', 'turbo', 1800000039, timeout=0)
        self.assertEqual(iq.api.buyv3_by_raw_expired.call_count, 1)
        self.assertEqual(iq.api.buy_multi_option, {})


if __name__ == '__main__': unittest.main()
