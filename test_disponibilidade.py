"""Respostas ficticias: nao conecta nem envia ordens."""
import unittest
from unittest.mock import Mock, patch
from test_entrada import bot


class Disponibilidade(unittest.TestCase):
    def ler(self, ativos, codigos=None):
        return bot.interpretar_disponibilidade(
            {'turbo': {'actives': ativos}}, codigos or {'EURUSD': 1}, ['EURUSD'])

    def test_booleanos_e_inteiros_confirmam_mesmo_codigo(self):
        for enabled, suspended in ((True, False), (1, 0)):
            with self.subTest(enabled=enabled):
                self.assertIs(self.ler({'1': {'name': 'nome.alternativo',
                    'enabled': enabled, 'is_suspended': suspended}})['EURUSD'], True)

    def test_incompleto_ou_invalido_nao_significa_fechado(self):
        for item in ({}, {'enabled': True}, {'is_suspended': False},
                     {'enabled': 'true', 'is_suspended': 'false'},
                     {'enabled': 2, 'is_suspended': 0}):
            with self.subTest(item=item):
                self.assertIsNone(self.ler({'1': item})['EURUSD'])

    def test_desabilitado_ou_suspenso_bloqueia(self):
        for item in ({'enabled': False}, {'enabled': 0},
                     {'enabled': True, 'is_suspended': True}, {'is_suspended': 1}):
            with self.subTest(item=item):
                self.assertIs(self.ler({'1': item})['EURUSD'], False)

    def test_nome_igual_com_outro_codigo_nao_libera_ordem(self):
        self.assertIsNone(self.ler({'99': {'name': 'front.EURUSD',
            'enabled': True, 'is_suspended': False}})['EURUSD'])

    def test_resposta_vazia_malformada_e_codigo_ambiguo(self):
        for ativos in ({}, [], None, {'1': None},
                       {'1': {'enabled': True, 'is_suspended': False}, 1: {}}):
            with self.subTest(ativos=ativos):
                self.assertIsNone(self.ler(ativos)['EURUSD'])
        with self.assertRaises(ValueError):
            bot.interpretar_disponibilidade(None, {'EURUSD': 1}, ['EURUSD'])

    def test_digital_e_binary_nao_confirmam_turbo(self):
        dados = {categoria: {'actives': {'1': {'enabled': True, 'is_suspended': False}}}
                 for categoria in ('digital', 'binary')}
        self.assertIsNone(bot.interpretar_disponibilidade(dados, {'EURUSD': 1}, ['EURUSD'])['EURUSD'])

    def test_dez_pares_identificados_por_codigo(self):
        from configuracao import PARES_DISPONIVEIS
        from iqoptionapi.constants import ACTIVES
        ativos = {str(ACTIVES[nome]): {'enabled': 1, 'is_suspended': 0}
                  for nome in PARES_DISPONIVEIS}
        iq = Mock()
        iq.get_all_init_v2.return_value = {'turbo': {'actives': ativos}}
        with patch.object(bot, 'ATIVOS', list(PARES_DISPONIVEIS)):
            resultado = bot.consultar_abertura_binaria(iq)
        self.assertEqual(len(resultado), 10)
        self.assertTrue(all(valor is True for valor in resultado.values()))
        self.assertEqual(len(resultado.motivos), 10)

    def test_reconsulta_pode_mudar_fechado_para_aberto(self):
        iq = Mock()
        iq.get_all_init_v2.side_effect = [
            {'turbo': {'actives': {'1': {'enabled': False}}}},
            {'turbo': {'actives': {'1': {'enabled': True, 'is_suspended': False}}}}]
        with patch.object(bot, 'ATIVOS', ['EURUSD']):
            self.assertIs(bot.consultar_abertura_binaria(iq)['EURUSD'], False)
            self.assertIs(bot.consultar_abertura_binaria(iq)['EURUSD'], True)
