import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from configuracao import validar_configuracao, carregar_configuracao, salvar_configuracao, aplicar_no_motor, PADRAO, PARES_OTC


class Configuracao(unittest.TestCase):
    def test_validacao_e_padrao(self):
        self.assertEqual(validar_configuracao({}), PADRAO)
        self.assertEqual(validar_configuracao({'pips': '4,5', 'valor': '12,75', 'expiracao': '5'}), {'pips': 4.5, 'valor': 12.75, 'expiracao': 5, 'pares': PARES_OTC})

    def test_invalidos_nao_sao_aceitos(self):
        for dados in [[], {'pips': 0}, {'pips': '-3'}, {'pips': 'NaN'}, {'valor': 'Infinity'}, {'valor': 0}, {'valor': '10.001'}, {'expiracao': '1.5'}, {'expiracao': 0}, {'expiracao': 6}]:
            with self.subTest(dados=dados), self.assertRaises(ValueError):
                validar_configuracao(dados)

    def test_salvar_reabrir_sem_credenciais(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.bot-temp') as pasta:
            self.assertEqual(carregar_configuracao(pasta), PADRAO)
            salvo = salvar_configuracao(pasta, {'pips': '4', 'valor': '35,50', 'expiracao': 2, 'senha': 'nao-persistir'})
            self.assertEqual(carregar_configuracao(pasta), salvo)
            self.assertNotIn('senha', (Path(pasta)/'configuracao.json').read_text())
            (Path(pasta)/'configuracao.json').write_text(json.dumps({'expiracao': 99}))
            with self.assertRaises(ValueError): carregar_configuracao(pasta)

    def test_motor_recebe_valores_validados(self):
        motor = SimpleNamespace()
        aplicar_no_motor(motor, {'pips': 4, 'valor': 50, 'expiracao': 3})
        self.assertEqual((motor.CORRECAO_PIPS, motor.VALOR, motor.EXPIRACAO), (4, 50, 3))

    def test_pares_selecionados_persistem_e_chegam_ao_motor(self):
        motor=SimpleNamespace()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.bot-temp') as pasta:
            salvar_configuracao(pasta, {'pares':['EURUSD','GBPJPY-OTC','EURUSD']})
            config=carregar_configuracao(pasta)
            aplicar_no_motor(motor,config)
            self.assertEqual(motor.ATIVOS,['EURUSD','GBPJPY-OTC'])
        for pares in ([], 'EURUSD', ['INVALIDO'], [None]):
            with self.subTest(pares=pares),self.assertRaises(ValueError):validar_configuracao({'pares':pares})

    def test_painel_salva_selecao_e_bloqueia_troca_durante_sessao(self):
        import tkinter as tk
        import painel
        from unittest.mock import patch
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.bot-temp') as pasta, patch.object(painel, 'BASE', Path(pasta)):
                app = painel.Painel(root)
                for par, variavel in app.pares_config.items():
                    variavel.set(par in ('EURUSD', 'GBPJPY-OTC'))
                self.assertTrue(app.salvar_parametros())
                self.assertEqual(set(carregar_configuracao(pasta)['pares']), {'EURUSD', 'GBPJPY-OTC'})
                self.assertEqual(app.ativos.item('EURUSD-OTC', 'values')[1], 'Não selecionado')
                app.bloquear_parametros(True)
                self.assertEqual(str(app.escolher_pares.cget('state')), 'disabled')
                app.bloquear_parametros(False)
                self.assertEqual(str(app.escolher_pares.cget('state')), 'normal')
        finally:
            for timer in root.tk.call('after', 'info'):
                root.after_cancel(timer)
            root.destroy()
