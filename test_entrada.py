"""Testes locais da entrada; nao conectam nem enviam ordens a corretora."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ARQUIVO = Path(__file__).with_name('MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py')
spec = importlib.util.spec_from_file_location('motor_teste', ARQUIVO)
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)

class CorretoraFalsa:
    def __init__(self):
        self.chamadas = []
    def check_connect(self):
        return True
    def get_balance_mode(self):
        return 'PRACTICE'
    def buy(self, *args):
        self.chamadas.append(args)
        # Recusa ficticia: nao cria thread de resultado.
        return False, None

class Entrada(unittest.TestCase):
    def executar(self, lado, preco, segundo=10, extrema=True, abertura=1.1):
        t = 1800000000
        velas = [{'t': t-60*i, 'o': 1.1, 'h': 1.101, 'l': 1.099, 'c': 1.1}
                 for i in range(15, 0, -1)]
        velas.append({'t': t, 'o': abertura, 'h': 1.101 if extrema else 1.1,
                      'l': 1.099 if extrema else 1.1, 'c': preco})
        estado = {'ultima_fechada': t-60, 'ultima_operada': None,
                  'alerta': {'lado': lado, 't': t-60, 'seta': True,
                             't_seta': t, 'preco_seta': 1.1}}
        iq = CorretoraFalsa()
        with patch.object(bot.time, 'time', return_value=t+segundo), patch.object(bot, 'escrever'):
            bot.processar('EURUSD-OTC', velas, estado, t+segundo, True, iq, True)
        return iq.chamadas, estado

    def test_bolinha_junto_da_seta_descarta_sem_rearmar(self):
        for lado in ('CALL', 'PUT'):
            with self.subTest(lado=lado), patch.object(bot, 'SEM_RECUO', True):
                t,v,estado,iq=self.cenario_intrabar(lado)
                with patch.object(bot, 'bolinha', side_effect=lambda vela,*args: lado if vela['t'] in (t-60,t) else None), patch.object(bot, 'seta', side_effect=lambda vela,*args: lado if vela['t']==t else None):
                    self.ciclo(t,v,estado,iq,5)
                self.assertIsNone(estado['alerta'])
                self.ciclo(t,v,estado,iq,6)
                self.assertEqual(iq.chamadas,[])

    def test_bolinha_apos_seta_detectada_cancela_espera_recuo(self):
        for lado in ('CALL', 'PUT'):
            with self.subTest(lado=lado):
                t,v,estado,iq=self.cenario_intrabar(lado)
                self.ciclo(t,v,estado,iq,5)
                self.assertTrue(estado['alerta']['seta'])
                with patch.object(bot, 'bolinha', return_value=lado), patch.object(bot, 'seta', return_value=None):
                    self.ciclo(t,v,estado,iq,6)
                self.assertIsNone(estado['alerta'])
                self.assertEqual(iq.chamadas,[])

    def test_bolinha_e_seta_fechadas_nao_armam_proxima(self):
        t,v,estado,iq=self.cenario_intrabar('CALL')
        with patch.object(bot, 'verificar_sinal_historico', return_value={'bolinha':'CALL','seta':'CALL'}):
            self.ciclo(t,v,estado,iq,5)
        self.assertIsNone(estado['alerta'])
        self.assertEqual(iq.chamadas,[])

    def test_call_toque_antigo_nao_envia(self):
        chamadas, estado = self.executar('CALL', 1.1002)
        self.assertEqual(chamadas, [])
        self.assertIsNotNone(estado['alerta'])
        self.assertIsNone(estado['ultima_operada'])

    def test_put_toque_antigo_nao_envia(self):
        self.assertEqual(self.executar('PUT', 1.0998)[0], [])

    def test_call_no_alvo_envia_configuracao_original(self):
        alvo = 1.1 - bot.CORRECAO_PIPS*bot.pip('EURUSD-OTC')
        self.assertEqual(self.executar('CALL', alvo)[0], [(20, 'EURUSD-OTC', 'call', 1)])

    def test_put_no_alvo_envia(self):
        alvo = 1.1 + bot.CORRECAO_PIPS*bot.pip('EURUSD-OTC')
        self.assertEqual(self.executar('PUT', alvo)[0], [(20, 'EURUSD-OTC', 'put', 1)])

    def test_sem_correcao_nao_envia(self):
        self.assertEqual(self.executar('CALL', 1.1, extrema=False)[0], [])

    def test_depois_do_limite_nao_envia(self):
        self.assertEqual(self.executar('CALL', 1.0996, segundo=29.1)[0], [])
        self.assertEqual(self.executar('PUT', 1.1004, segundo=30)[0], [])

    def test_call_mede_abertura_e_nao_fechamento_da_seta(self):
        # Abertura acima do fechamento: alvo deve acompanhar a abertura.
        abertura = 1.1005
        alvo = abertura - 3*bot.pip('EURUSD-OTC')
        self.assertEqual(len(self.executar('CALL', alvo, abertura=abertura)[0]), 1)
        # Alvo antigo foi atingido, mas nao houve recuo de 3 pips da abertura.
        self.assertEqual(self.executar('CALL', 1.0996, abertura=1.0995)[0], [])

    def test_put_mede_abertura_e_nao_fechamento_da_seta(self):
        abertura = 1.0995
        alvo = abertura + 3*bot.pip('EURUSD-OTC')
        self.assertEqual(len(self.executar('PUT', alvo, abertura=abertura)[0]), 1)
        self.assertEqual(self.executar('PUT', 1.1004, abertura=1.1005)[0], [])

    def test_apenas_ficar_vermelha_nao_basta(self):
        self.assertEqual(self.executar('CALL', 1.0999)[0], [])

    def test_segundo_29_ainda_permitido(self):
        self.assertEqual(len(self.executar('CALL', 1.0996, segundo=29)[0]), 1)

    def test_configuracao_personalizada_chega_a_ordem(self):
        with patch.object(bot, 'CORRECAO_PIPS', 4.5), patch.object(bot, 'VALOR', 12.75), patch.object(bot, 'EXPIRACAO', 5):
            self.assertEqual(self.executar('CALL', 1.1-3*bot.pip('EURUSD-OTC'))[0], [])
            self.assertEqual(self.executar('CALL', 1.1-4.5*bot.pip('EURUSD-OTC'))[0], [(12.75, 'EURUSD-OTC', 'call', 5)])
            self.assertEqual(self.executar('PUT', 1.1+4.5*bot.pip('EURUSD-OTC'))[0], [(12.75, 'EURUSD-OTC', 'put', 5)])

    def test_30_segundos_chega_ao_adaptador_sem_truncamento(self):
        from unittest.mock import Mock
        envio = Mock(return_value=(False, None))
        with patch.object(bot, 'EXPIRACAO', 0.5), patch.object(bot, 'comprar_com_expiracao', envio):
            self.executar('CALL', 1.0996)
        self.assertEqual(envio.call_args.args[1:], (20, 'EURUSD-OTC', 'call', 0.5))

    def cenario_intrabar(self, lado):
        t=1800000000
        velas=[{'t': t-i*60, 'o': 1.1, 'c': 1.1, 'h': 1.101, 'l': 1.099} for i in range(18,3,-1)]
        velas += [{'t': t-180, 'o': 1.1003, 'c': 1.1004, 'h': 1.1005, 'l': 1.1002},
                  {'t': t-120, 'o': 1.1008, 'c': 1.1002, 'h': 1.1009, 'l': 1.1001},
                  {'t': t-60, 'o': 1.1, 'c': 1.101, 'h': 1.1012, 'l': 1.0999},
                  {'t': t, 'o': 1.101, 'c': 1.1012, 'h': 1.1013, 'l': 1.101}]
        if lado=='PUT':
            velas=[{'t':v['t'],'o':2.2-v['o'],'c':2.2-v['c'],'h':2.2-v['l'],'l':2.2-v['h']} for v in velas]
        return t,velas,{'ultima_fechada':t-120,'ultima_operada':None,'alerta':None},CorretoraFalsa()

    def ciclo(self, t, velas, estado, iq, segundo, enviar=True, aberto=True):
        with patch.object(bot.time,'time',return_value=t+segundo),patch.object(bot,'escrever') as log:
            bot.processar('EURUSD-OTC',velas,estado,t+segundo,enviar,iq,aberto)
        return log

    def test_bolinha_seta_e_recuo_na_mesma_vela_call_e_put(self):
        for lado in ('CALL','PUT'):
            with self.subTest(lado=lado):
                t,v,estado,iq=self.cenario_intrabar(lado)
                log=self.ciclo(t,v,estado,iq,5)
                self.assertEqual(estado['alerta']['t_seta'],t)
                self.assertTrue(any(c.args[1]=='SETA_DETECTADA' for c in log.call_args_list))
                self.assertEqual(iq.chamadas,[])
                # O recuo pode tornar a seta neutra antes do fechamento.
                v[-1]['c']=v[-1]['o']+(-1 if lado=='CALL' else 1)*4*bot.pip('EURUSD-OTC')
                log=self.ciclo(t,v,estado,iq,12)
                self.assertEqual(iq.chamadas,[(20,'EURUSD-OTC',lado.lower(),1)])
                ordem=next(c for c in log.call_args_list if c.args[1]=='ORDEM_RECUSADA')
                self.assertIn(f'seta_t={t} entrada_t={t}',ordem.args[2])
                self.ciclo(t,v,estado,iq,13)
                self.assertEqual(len(iq.chamadas),1)

    def test_sem_recuo_envia_na_deteccao_call_e_put_uma_vez(self):
        for lado in ('CALL', 'PUT'):
            with self.subTest(lado=lado), patch.object(bot, 'SEM_RECUO', True):
                t, v, estado, iq = self.cenario_intrabar(lado)
                log = self.ciclo(t, v, estado, iq, 5)
                self.assertEqual(iq.chamadas, [(20, 'EURUSD-OTC', lado.lower(), 1)])
                self.assertTrue(any(c.args[1] == 'ENTRADA_SEM_RECUO' for c in log.call_args_list))
                self.assertFalse(any(c.args[1] == 'CORRECAO_PIPS' for c in log.call_args_list))
                self.ciclo(t, v, estado, iq, 6)
                self.assertEqual(len(iq.chamadas), 1)

    def test_sem_recuo_preserva_demais_condicoes(self):
        for caso in ('sem_bolinha', 'sem_seta', 'contrario', 'prazo', 'fechado', 'real', 'observacao'):
            with self.subTest(caso=caso), patch.object(bot, 'SEM_RECUO', True):
                t, v, estado, iq = self.cenario_intrabar('CALL')
                if caso == 'sem_bolinha': estado['ultima_fechada'] = t-60
                if caso == 'real': iq.get_balance_mode = lambda: 'REAL'
                direcao = None if caso == 'sem_seta' else 'PUT' if caso == 'contrario' else 'CALL'
                with patch.object(bot, 'seta', return_value=direcao):
                    self.ciclo(t, v, estado, iq, 30 if caso == 'prazo' else 5,
                               enviar=caso != 'observacao', aberto=caso != 'fechado')
                self.assertEqual(iq.chamadas, [])

    def test_nao_carrega_seta_para_proxima_vela(self):
        t,v,estado,iq=self.cenario_intrabar('CALL')
        self.ciclo(t,v,estado,iq,5)
        v.append({'t':t+60,'o':1.101,'c':1.1005,'h':1.101,'l':1.1005})
        self.ciclo(t,v,estado,iq,70)
        self.assertEqual(iq.chamadas,[])

    def test_recuo_sem_seta_observada_nao_envia(self):
        t,v,estado,iq=self.cenario_intrabar('CALL')
        v[-1]['c']=1.1005
        self.ciclo(t,v,estado,iq,10)
        self.assertEqual(iq.chamadas,[])
        self.assertFalse(estado['alerta']['seta'])

    def test_sinal_contrario_intrabar_cancela(self):
        t,v,estado,iq=self.cenario_intrabar('CALL')
        self.ciclo(t,v,estado,iq,5)
        with patch.object(bot,'seta',return_value='PUT'):
            self.ciclo(t,v,estado,iq,10)
        self.assertIsNone(estado['alerta'])
        self.assertEqual(iq.chamadas,[])

    def test_demo_e_observacao_preservam_bloqueios(self):
        for modo in ('simulacao','fechado','real'):
            with self.subTest(modo=modo):
                t,v,estado,iq=self.cenario_intrabar('CALL')
                self.ciclo(t,v,estado,iq,5)
                v[-1]['c']=1.1005
                if modo=='real':iq.get_balance_mode=lambda:'REAL'
                self.ciclo(t,v,estado,iq,12,enviar=modo!='simulacao',aberto=modo!='fechado')
                self.assertEqual(iq.chamadas,[])

    def test_seta_do_indicador_usa_close_atual_e_comparacoes_estritas(self):
        for lado in ('CALL', 'PUT'):
            with self.subTest(lado=lado):
                _, velas, _, _ = self.cenario_intrabar(lado)
                atual, anterior, ant2, ant3 = [v.copy() for v in velas[-4:][::-1]]
                self.assertEqual(bot.seta(atual, anterior, ant2, ant3), lado)
                atual['c'] = anterior['c']
                self.assertIsNone(bot.seta(atual, anterior, ant2, ant3))
                atual = velas[-1].copy()
                ant3['c'] = ant2['c']
                self.assertIsNone(bot.seta(atual, anterior, ant2, ant3))

    def test_main_consulta_somente_os_pares_selecionados(self):
        from unittest.mock import Mock, call
        selecionados = ['EURUSD', 'GBPJPY-OTC']
        iq = Mock()
        iq.check_connect.return_value = True
        iq.get_balance_mode.return_value = 'PRACTICE'
        iq.get_candles.return_value = []
        with patch.object(bot, 'ATIVOS', selecionados), \
             patch.object(bot, 'input', side_effect=['1', 'cliente@exemplo.test'], create=True), \
             patch.object(bot, 'getpass', return_value='senha-ficticia'), \
             patch('iqoptionapi.stable_api.IQ_Option', return_value=iq), \
             patch.object(bot, 'consultar_abertura_binaria', return_value={p: True for p in selecionados}), \
             patch.object(bot, 'escrever'), patch('builtins.print'), \
             patch.object(bot.time, 'sleep', side_effect=KeyboardInterrupt):
            bot.main()
        self.assertEqual([c.args[0] for c in iq.get_candles.call_args_list], selecionados)
        iq.buy.assert_not_called()

if __name__ == '__main__':
    unittest.main(verbosity=2)
