import unittest
from types import SimpleNamespace
from saldo_painel import consultar_saldo_demo

class Saldo(unittest.TestCase):
    def conta(self, modo='PRACTICE', resposta=True):
        api = SimpleNamespace(balances_raw=None)
        def receber():
            if resposta:
                api.balances_raw = {'msg': [{'id': 1, 'amount': 80}, {'id': 2, 'amount': 10000}]}
        api.get_balances = receber
        return SimpleNamespace(api=api, check_connect=lambda: True, get_balance_mode=lambda: modo)

    def test_le_saldo_demo_da_conta_selecionada(self):
        self.assertEqual(consultar_saldo_demo(self.conta(), 2), 10000)

    def test_bloqueia_conta_real(self):
        with self.assertRaises(RuntimeError):
            consultar_saldo_demo(self.conta(modo='REAL'), 1)

    def test_sem_resposta_nao_trava(self):
        with self.assertRaises(TimeoutError):
            consultar_saldo_demo(self.conta(resposta=False), 2, timeout=0)

    def test_nao_inventa_saldo_ausente(self):
        with self.assertRaises(ValueError):
            consultar_saldo_demo(self.conta(), 99)

if __name__ == '__main__':
    unittest.main()
