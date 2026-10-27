import tkinter as tk
import unittest
from unittest.mock import patch
from painel import Painel


class DestaqueEntrada(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.painel = Painel(self.root)
        self.painel.som_ativo.set(False)

    def tearDown(self):
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.root.destroy()

    def evento(self, ativo, evento, detalhe):
        self.painel.fila.put(f'[20:45:12] {ativo} | {evento} | {detalhe}')
        self.painel.poll()

    def test_apenas_ordem_aceita_destaca_par(self):
        for evento in ('SETA_CONFIRMADA', 'SINAL_SIMULADO', 'ORDEM_RECUSADA'):
            self.evento('EURUSD-OTC', evento, 'CALL valor=20.00 expiracao=1 id=123')
            self.assertEqual(self.painel.entrada_par.get(), '')
        self.evento('EURUSD-OTC', 'DEMO_ENVIADA', 'CALL valor=20.00 expiracao=1 id=123')
        self.assertIn('EURUSD-OTC', self.painel.entrada_par.get())
        self.assertIn('CALL', self.painel.entrada_par.get())
        self.assertIn('20:45:12', self.painel.entrada_info.get())
        self.assertIn('20,00', self.painel.entrada_info.get())
        self.assertIn('ID 123', self.painel.entrada_info.get())

    def test_ordens_simultaneas_e_resultado_da_ordem_certa(self):
        self.evento('EURUSD-OTC', 'DEMO_ENVIADA', 'CALL valor=20.00 expiracao=1 id=123')
        self.evento('GBPJPY-OTC', 'DEMO_ENVIADA', 'PUT valor=25.00 expiracao=2 id=456')
        self.assertIn('GBPJPY-OTC', self.painel.entrada_par.get())
        self.assertIn('EURUSD-OTC', self.painel.entrada_abertas.get())
        self.evento('EURUSD-OTC', 'RESULTADO_WIN', 'id=123 lucro_liquido=17.40')
        self.assertIn('GBPJPY-OTC', self.painel.entrada_par.get())
        self.assertNotIn('EURUSD-OTC', self.painel.entrada_abertas.get())
        self.evento('GBPJPY-OTC', 'RESULTADO_LOSS', 'id=456 lucro_liquido=-25.00')
        self.assertIn('CONCLUÍDA', self.painel.entrada_estado.get())
        self.assertIn('LOSS', self.painel.entrada_estado.get())
        self.assertEqual(self.painel.entradas_ativas, {})

    def test_resultado_nao_confirmado_continua_pendente(self):
        self.evento('EURUSD-OTC', 'DEMO_ENVIADA', 'PUT valor=20.00 expiracao=1 id=123')
        self.evento('EURUSD-OTC', 'RESULTADO_NAO_CONFIRMADO', 'id=123 erro=timeout')
        self.assertIn('NÃO CONFIRMADO', self.painel.entrada_estado.get())
        self.assertIn('123', self.painel.entradas_ativas)


if __name__ == '__main__': unittest.main()
