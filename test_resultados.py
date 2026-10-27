"""Valida resultados sem conexao e sem enviar ordens."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('motor_resultado', Path(__file__).with_name('MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py'))
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)

class Resultados(unittest.TestCase):
    def test_formatos_da_biblioteca(self):
        for recebido, esperado in [(('win', 17.6), (17.6, 'WIN')), (('loose', -20), (-20., 'LOSS')), (('equal', 0), (0., 'EMPATE')), (17.6, (17.6, 'WIN')), (-20, (-20., 'LOSS'))]:
            with self.subTest(recebido=recebido):
                self.assertEqual(bot.interpretar_resultado(recebido), esperado)

    def test_invalidos_nao_viram_resultados(self):
        for recebido in [None, True, ('win',), ('erro', 20), ('win', -20), ('equal', 20), ('win', float('nan')), float('inf')]:
            with self.subTest(recebido=str(recebido)):
                with self.assertRaises((ValueError, TypeError)):
                    bot.interpretar_resultado(recebido)

    def test_resultado_chega_aos_cartoes(self):
        import tkinter as tk
        from painel import Painel
        root = tk.Tk()
        root.withdraw()
        painel = Painel(root)
        try:
            salvar_mock = Mock(side_effect=lambda ativo, direcao, oid, lucro, resultado: painel.fila.put('__PAINEL__' + __import__('json').dumps({'tipo': 'resultado', 'id': str(oid), 'lucro': lucro, 'resultado': resultado})))
            with patch.object(painel, 'ler_resultados_salvos', return_value=[{'RESULTADO': 'WIN', 'LUCRO_LIQUIDO': '17.6'}, {'RESULTADO': 'LOSS', 'LUCRO_LIQUIDO': '-20'}, {'RESULTADO': 'EMPATE', 'LUCRO_LIQUIDO': '0'}]), patch.object(bot, 'salvar_resultado', salvar_mock), patch.object(bot, 'escrever') as log:
                for oid, retorno in [(1, ('win', 17.6)), (2, ('loose', -20)), (3, ('equal', 0))]:
                    iq = Mock()
                    iq.check_win_v4.return_value = retorno
                    bot.aguardar_resultado(iq, 'GBPUSD-OTC', 'PUT', oid)
                painel.poll()
                self.assertEqual(salvar_mock.call_count, 3)
                self.assertEqual((painel.ganhos, painel.perdas, painel.empates), (1, 1, 1))
                self.assertAlmostEqual(painel.liquido, -2.4)
                self.assertEqual(painel.liquido_valor.get(), '-2,40')
                self.assertFalse(any(c.args[1] == 'RESULTADO_NAO_CONFIRMADO' for c in log.call_args_list))
        finally:
            root.destroy()

    def test_falha_preserva_aviso(self):
        iq = Mock()
        iq.check_win_v4.return_value = ('desconhecido', None)
        with patch.object(bot, 'salvar_resultado') as salvar, patch.object(bot, 'escrever') as log:
            bot.aguardar_resultado(iq, 'GBPUSD-OTC', 'PUT', 9)
            salvar.assert_not_called()
            self.assertEqual(log.call_args.args[1], 'RESULTADO_NAO_CONFIRMADO')

if __name__ == '__main__':
    unittest.main(verbosity=2)
