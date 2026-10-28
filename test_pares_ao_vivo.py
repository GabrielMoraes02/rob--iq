import time
import unittest
from unittest.mock import Mock, patch
from pares_ao_vivo import ParesAoVivo, listar_binarias, acompanhar_binarias
from test_entrada import bot
from expiracao_ordem import comprar_binaria_categoria


def resposta(binary=None, blitz=None):
    def ativos(nomes):
        return {str(i+100): {'name': 'front.'+p, 'enabled': True, 'is_suspended': False}
                for i, p in enumerate(nomes or [])}
    return {'binary': {'actives': ativos(binary)}, 'turbo': {'actives': {}}, 'blitz': {'actives': ativos(blitz)}}


class ParesVivos(unittest.TestCase):
    def test_timeout_preserva_apenas_confirmacao_recente_sem_renovar_data(self):
        for idade, erro, preserva in [(5, TimeoutError(), True), (21, TimeoutError(), False),
                                      (5, ValueError(), False)]:
            with self.subTest(idade=idade, erro=type(erro).__name__):
                selecao = ParesAoVivo(['EURUSD'], Mock())
                selecao.atualizar_catalogo(resposta(['EURUSD']), 100-idade)
                parar = Mock()
                parar.is_set.side_effect = [False, False, True]
                iq = Mock()
                iq.api.consulta_catalogo.consultar.side_effect = erro
                with patch('pares_ao_vivo.time.time', return_value=100):
                    acompanhar_binarias(iq, parar, selecao)
                self.assertEqual(selecao.dados is not None, preserva)
                self.assertEqual(selecao.consultado_em, 100-idade if preserva else 0)
                parar.wait.assert_called_once_with(1)

    def test_recuperacao_e_suspensao_substituem_cache_imediatamente(self):
        selecao = ParesAoVivo(['EURUSD'], Mock())
        selecao.atualizar_catalogo(resposta(['EURUSD']), 99)
        fechado = resposta(['EURUSD'])
        fechado['binary']['actives']['100']['is_suspended'] = True
        iq = Mock()
        iq.api.consulta_catalogo.consultar.side_effect = [TimeoutError(), fechado, resposta(['EURUSD'])]
        parar = Mock()
        parar.is_set.side_effect = [False, False, False, False, False, False, True]
        with patch('pares_ao_vivo.time.time', return_value=100):
            acompanhar_binarias(iq, parar, selecao)
        publicados = [c.args[0] for c in selecao.publicar.call_args_list]
        self.assertEqual([p['ativos'][0]['estado'] for p in publicados], ['Aberto', 'Fechado', 'Aberto'])
        self.assertEqual([p['consultado_em'] for p in publicados], [99, 100, 100])

    def test_filtro_sem_limite_de_dez_e_sem_blitz(self):
        linhas = listar_binarias(resposta(['GBPCHF-op', 'Apple-op'] + [f'Ativo{i}' for i in range(100)], ['EURUSD-op']))
        self.assertEqual(len(linhas), 102)
        self.assertIn('GBPCHF', {r['par'] for r in linhas})
        self.assertNotIn('EURUSD', {r['par'] for r in linhas})

    def test_troca_binaria_para_blitz_e_nova_binaria_sem_reconectar(self):
        publicado = Mock()
        selecao = ParesAoVivo(['EURUSD'], publicado)
        selecao.atualizar_catalogo(resposta(['GBPCHF-op'], ['EURUSD-op']))
        selecao.receber({'tipo': 'selecionar_pares', 'pedido': 'a', 'pares': ['GBPCHF']})
        self.assertFalse(selecao.permite('EURUSD'))
        self.assertEqual(selecao.consumir(), ['GBPCHF'])
        self.assertTrue(selecao.permite('GBPCHF'))
        publicado.assert_called_with({'tipo': 'pares_aplicados', 'pedido': 'a', 'pares': ['GBPCHF']})
        selecao.receber({'tipo': 'selecionar_pares', 'pedido': 'b', 'pares': ['EURUSD']})
        self.assertIsNone(selecao.consumir())
        self.assertEqual(selecao.pares, ['GBPCHF'])
        self.assertEqual(publicado.call_args.args[0]['tipo'], 'pares_recusados')

    def test_dados_antigos_bloqueiam_adicao_mas_permite_remover_todos(self):
        selecao = ParesAoVivo(['EURUSD'], Mock())
        selecao.atualizar_catalogo(resposta(['GBPCHF-op']), time.time()-30)
        selecao.receber({'tipo': 'selecionar_pares', 'pedido': 'a', 'pares': ['GBPCHF']})
        self.assertIsNone(selecao.consumir())
        selecao.receber({'tipo': 'selecionar_pares', 'pedido': 'b', 'pares': []})
        self.assertEqual(selecao.consumir(), [])

    def test_resolucao_preserva_categoria_binary_e_nunca_blitz(self):
        resolvido = bot.interpretar_disponibilidade(resposta(['GBPCHF-op'], ['EURUSD-op']), ['GBPCHF', 'EURUSD'])
        self.assertIs(resolvido['GBPCHF'], True)
        self.assertEqual(resolvido.instrumentos['GBPCHF']['categoria'], 'binary')
        self.assertIsNone(resolvido['EURUSD'])

    def test_envio_binary_preserva_categoria_e_prazo_sem_mudar_para_blitz(self):
        iq = Mock()
        iq.check_connect.return_value = True
        iq.get_balance_mode.return_value = 'PRACTICE'
        iq.get_server_timestamp.return_value = 1800000005
        turbo = Mock()
        with patch('expiracao_ordem.time.time', return_value=1800000005), \
             patch('iqoptionapi.expiration.get_expiration_time', return_value=(1800000060, 0)), \
             patch('expiracao_ordem.comprar_por_vencimento_api', return_value=(False, 'teste')) as envio:
            self.assertEqual(comprar_binaria_categoria(iq, 20, 'GBPCHF', 'call', 1, 'binary', turbo), (False, 'teste'))
            envio.assert_called_once_with(iq, 20, 'GBPCHF', 'call', 'binary', 1800000060)
            turbo.assert_not_called()
            with self.assertRaises(ValueError): comprar_binaria_categoria(iq, 20, 'GBPCHF', 'call', 1, 'blitz', turbo)
            with self.assertRaises(ValueError): comprar_binaria_categoria(iq, 20, 'GBPCHF', 'call', 0.5, 'binary', turbo)

    def test_motor_recebe_troca_e_nao_consulta_par_removido(self):
        iq = Mock()
        iq.check_connect.return_value = True
        iq.get_balance_mode.return_value = 'PRACTICE'
        iq.get_candles.return_value = []
        with patch.object(bot, 'ATIVOS', ['EURUSD']), \
             patch.object(bot, 'input', side_effect=['1', 'cliente@exemplo.test'], create=True), \
             patch.object(bot, 'getpass', return_value='ficticia'), \
             patch('iqoptionapi.stable_api.IQ_Option', return_value=iq), \
             patch.object(bot, 'receber_pares', return_value=['GBPCHF']), \
             patch.object(bot, 'consultar_abertura_binaria', return_value={'GBPCHF': True}), \
             patch.object(bot, 'escrever'), patch('builtins.print'), \
             patch.object(bot.time, 'sleep', side_effect=KeyboardInterrupt):
            bot.main()
        self.assertEqual([c.args[0] for c in iq.get_candles.call_args_list], ['GBPCHF'])
        iq.buy.assert_not_called()
        iq.connect.assert_called_once()
