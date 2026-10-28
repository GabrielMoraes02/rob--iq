"""Respostas ficticias: nao conecta nem envia ordens."""
import unittest
from unittest.mock import Mock, patch
from test_entrada import bot


class Disponibilidade(unittest.TestCase):
    def test_aviso_blitz_exige_confirmacao_e_nao_libera_ordem(self):
        item = {'name': 'front.EURUSD', 'enabled': True, 'is_suspended': True}
        for aberto in (True, False, None):
            blitz = dict(item, is_suspended=not aberto) if aberto is not None else {'name': 'front.EURUSD'}
            resultado = bot.interpretar_disponibilidade({'turbo': {'actives': {'1': item}},
                'blitz': {'actives': {'1': blitz}}}, ['EURUSD'])
            self.assertIs(resultado['EURUSD'], False)
            self.assertEqual('Blitz está aberto' in resultado.motivos['EURUSD'], aberto is True)
            self.assertNotIn('EURUSD', resultado.instrumentos)

    def test_binaria_aberta_nao_bloqueia_por_existir_blitz(self):
        item = {'name': 'front.EURUSD', 'enabled': True, 'is_suspended': False}
        resultado = bot.interpretar_disponibilidade({'turbo': {'actives': {'1': item}},
            'blitz': {'actives': {'1': item}}}, ['EURUSD'])
        self.assertIs(resultado['EURUSD'], True)
        self.assertNotIn('Sem novas entradas', resultado.motivos['EURUSD'])

    def test_lista_ausente_nao_afirma_suspensao_ou_blitz(self):
        resultado = bot.interpretar_disponibilidade({}, ['EURUSD'])
        self.assertIsNone(resultado['EURUSD'])
        self.assertNotIn('suspensas', resultado.motivos['EURUSD'])
        self.assertNotIn('Blitz está aberto', resultado.motivos['EURUSD'])

    def ler(self, ativos):
        return bot.interpretar_disponibilidade(
            {'turbo': {'actives': ativos}}, ['EURUSD'])

    def test_booleanos_e_inteiros_confirmam_mesmo_codigo(self):
        for enabled, suspended in ((True, False), (1, 0)):
            with self.subTest(enabled=enabled):
                self.assertIs(self.ler({'1': {'name': 'front.EURUSD',
                    'enabled': enabled, 'is_suspended': suspended}})['EURUSD'], True)

    def test_incompleto_ou_invalido_nao_significa_fechado(self):
        for item in ({}, {'enabled': True}, {'is_suspended': False},
                     {'enabled': 'true', 'is_suspended': 'false'},
                     {'enabled': 2, 'is_suspended': 0}):
            with self.subTest(item=item):
                self.assertIsNone(self.ler({'1': {'name': 'front.EURUSD', **item}})['EURUSD'])

    def test_desabilitado_ou_suspenso_bloqueia(self):
        for item in ({'enabled': False}, {'enabled': 0},
                     {'enabled': True, 'is_suspended': True}, {'is_suspended': 1}):
            with self.subTest(item=item):
                self.assertIs(self.ler({'1': {'name': 'front.EURUSD', **item}})['EURUSD'], False)

    def test_codigo_atual_e_descoberto_pelo_nome(self):
        self.assertIs(self.ler({'99': {'name': 'front.EURUSD',
            'enabled': True, 'is_suspended': False}})['EURUSD'], True)

    def test_resposta_vazia_malformada_e_codigo_ambiguo(self):
        for ativos in ({}, [], None, {'1': None},
                       {'1': {'name': 'front.EURUSD', 'enabled': True, 'is_suspended': False}, 1: {}}):
            with self.subTest(ativos=ativos):
                self.assertIsNone(self.ler(ativos)['EURUSD'])
        with self.assertRaises(ValueError):
            bot.interpretar_disponibilidade(None, ['EURUSD'])

    def test_digital_e_blitz_nao_confirmam_binarias(self):
        dados = {categoria: {'actives': {'1': {'name': 'front.EURUSD', 'enabled': True, 'is_suspended': False}}}
                 for categoria in ('digital', 'blitz')}
        self.assertIsNone(bot.interpretar_disponibilidade(dados, ['EURUSD'])['EURUSD'])

    def test_dez_pares_identificados_por_codigo(self):
        from configuracao import PARES_DISPONIVEIS
        from iqoptionapi.constants import ACTIVES
        ativos = {str(ACTIVES[nome]): {'name': 'front.'+nome, 'enabled': 1, 'is_suspended': 0}
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
            {'turbo': {'actives': {'1': {'name': 'front.EURUSD', 'enabled': False}}}},
            {'turbo': {'actives': {'1': {'name': 'front.EURUSD', 'enabled': True, 'is_suspended': False}}}}]
        with patch.object(bot, 'ATIVOS', ['EURUSD']):
            self.assertIs(bot.consultar_abertura_binaria(iq)['EURUSD'], False)
            self.assertIs(bot.consultar_abertura_binaria(iq)['EURUSD'], True)

    def test_variante_op_aberta_substitui_codigo_legado_suspenso(self):
        resultado = self.ler({
            '1': {'name': 'front.EURUSD', 'enabled': True, 'is_suspended': True},
            '90001': {'name': 'front.EURUSD-op', 'enabled': True, 'is_suspended': False}})
        self.assertIs(resultado['EURUSD'], True)
        self.assertEqual(resultado.instrumentos['EURUSD']['codigo'], 90001)
        self.assertIn('EURUSD-op', resultado.motivos['EURUSD'])

    def test_otc_digital_e_nomes_sem_correspondencia_nao_liberam_normal(self):
        for nome in ('front.EURUSD-OTC', 'front.EURUSD-OTC-op', 'front.USDJPY', '', 'front.EURUSD-outro'):
            with self.subTest(nome=nome):
                self.assertIsNone(self.ler({'1': {'name': nome,
                    'enabled': True, 'is_suspended': False}})['EURUSD'])

    def test_duas_variantes_abertas_bloqueiam_em_vez_de_escolher_ao_acaso(self):
        resultado = self.ler({
            '1': {'name': 'front.EURUSD', 'enabled': True, 'is_suspended': False},
            '90001': {'name': 'front.EURUSD-op', 'enabled': True, 'is_suspended': False}})
        self.assertIsNone(resultado['EURUSD'])
        self.assertEqual(resultado.instrumentos, {})

    def test_troca_de_codigo_descarta_sinal_anterior(self):
        from iqoptionapi import constants
        estado = {'alerta': {'lado': 'CALL'}, 'ultima_fechada': 100,
                  'ultima_operada': 100, 'codigo_instrumento': 1}
        resultado = self.ler({'90001': {'name': 'front.EURUSD-op',
            'enabled': True, 'is_suspended': False}})
        with patch.dict(constants.ACTIVES):
            bot.aplicar_instrumento('EURUSD', resultado, estado)
            self.assertEqual(constants.ACTIVES['EURUSD'], 90001)
            self.assertIsNone(estado['alerta'])
            self.assertIsNone(estado['ultima_fechada'])
            self.assertIsNone(estado['ultima_operada'])
            estado['alerta'] = {'lado': 'PUT'}
            bot.aplicar_instrumento('EURUSD', resultado, estado)
            self.assertEqual(estado['alerta'], {'lado': 'PUT'})
            bot.aplicar_instrumento('EURUSD', {'EURUSD': None}, estado)
            self.assertIsNone(estado['alerta'])

    def test_sdk_velas_e_ordens_30s_e_1min_usam_codigo_descoberto(self):
        from iqoptionapi import constants
        from iqoptionapi.stable_api import IQ_Option
        from expiracao_ordem import comprar_com_expiracao, comprar_por_vencimento_api
        from types import SimpleNamespace
        api = Mock()
        api.candles = SimpleNamespace(candles_data=None)
        api.buy_multi_option = {}
        iq = SimpleNamespace(api=api, check_connect=lambda: True,
                             get_balance_mode=lambda: 'PRACTICE',
                             get_server_timestamp=lambda: 1800000005)
        def velas(*args):
            api.candles.candles_data = [{'from': 1800000000}]
        api.getcandles.side_effect = velas
        def ordem(*args):
            api.buy_multi_option[args[-1]] = {'message': 'Recusa ficticia de teste'}
        api.buyv3.side_effect = ordem
        def ordem_30(*args, request_id):
            api.buy_multi_option[request_id] = {'message': 'Recusa ficticia de teste'}
        api.buyv3_by_raw_expired.side_effect = ordem_30
        iq.buy = lambda *args: IQ_Option.buy(iq, *args)
        iq.buy_by_raw_expirations = lambda *args: comprar_por_vencimento_api(iq, *args)
        resultado = self.ler({'90001': {'name': 'front.EURUSD-op',
            'enabled': True, 'is_suspended': False}})
        with patch.dict(constants.ACTIVES), patch('expiracao_ordem.time.time', return_value=1800000005):
            bot.aplicar_instrumento('EURUSD', resultado, {})
            IQ_Option.get_candles(iq, 'EURUSD', 60, 35, 1800000005)
            self.assertEqual(api.getcandles.call_args.args[0], 90001)
            for minutos in (1, 0.5):
                self.assertFalse(comprar_com_expiracao(iq, 20, 'EURUSD', 'call', minutos)[0])
            self.assertEqual(api.buyv3.call_args.args[1], 90001)
            self.assertEqual(api.buyv3_by_raw_expired.call_args.args[1], 90001)
