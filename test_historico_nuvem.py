import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from historico_nuvem import Historico, Sincronizador


class Nuvem(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.bot-temp')
        self.base = Path(self.temp.name)
        self.h = Historico(self.base, '123')

    def tearDown(self):
        self.temp.cleanup()

    def registro(self, oid='42'):
        return dict(DATA_HORA='26/10/2026 12:00:00', ATIVO='EURUSD-OTC',
                    DIRECAO='CALL', ID_ORDEM=oid, RESULTADO='WIN', LUCRO_LIQUIDO='17.40')

    def test_contas_e_legado_isolados(self):
        (self.base / 'V19_GENERAL_3PIPS_OTC_5_RESULTADOS.csv').write_text('dados antigos')
        self.h.registrar('resultado', self.registro())
        self.assertEqual(len(self.h.ler('resultado')), 1)
        self.assertEqual(Historico(self.base, '456').ler('resultado'), [])
        for conta in ('../123', '', 'abc', '0'):
            with self.assertRaises(ValueError): Historico(self.base, conta)

    def test_repetir_resultado_nao_duplica_e_fila_persiste(self):
        self.h.registrar('resultado', self.registro())
        self.h.registrar('resultado', self.registro())
        outro = Historico(self.base, '123')
        self.assertEqual(len(outro.pendentes()), 1)
        self.assertEqual(len(outro.ler('resultado')), 1)

    def test_falha_remota_nao_apaga_fila(self):
        self.h.registrar('resultado', self.registro())
        post = Mock(return_value=Mock(status_code=503))
        sync = Sincronizador(self.h, 'sessao-na-memoria', lambda _: None, post)
        with self.assertRaises(RuntimeError): sync.ciclo()
        self.assertEqual(len(self.h.pendentes()), 1)
        self.assertNotIn('sessao-na-memoria', self.h.arquivo.read_bytes().decode('latin1'))

    def test_recuperar_no_segundo_computador_e_ack(self):
        self.h.registrar('resultado', self.registro())
        lote = self.h.pendentes()
        remoto = [dict(lote[0], sequencia=1)]
        post = Mock(return_value=Mock(status_code=200, json=lambda: dict(conta='123', registros=remoto, mais=False)))
        Sincronizador(self.h, 'sessao', lambda _: None, post).ciclo()
        self.assertEqual(self.h.pendentes(), [])
        with tempfile.TemporaryDirectory(dir=self.base) as mac:
            destino = Historico(mac, '123')
            Sincronizador(destino, 'sessao', lambda _: None, post).ciclo()
            self.assertEqual(destino.ler('resultado'), self.h.ler('resultado'))
            self.assertEqual(destino.pendentes(), [])

    def test_conta_remota_diferente_bloqueia_ack(self):
        self.h.registrar('resultado', self.registro())
        post = Mock(return_value=Mock(status_code=200, json=lambda: dict(conta='456', registros=[], mais=False)))
        with self.assertRaises(RuntimeError): Sincronizador(self.h, 'sessao', lambda _: None, post).ciclo()
        self.assertEqual(len(self.h.pendentes()), 1)

    def test_paginacao_carrega_todas_e_reconsulta_desde_zero(self):
        r = dict(id='resultado:42', tipo='resultado', dados=self.registro(), ocorrido_em='2026-10-26T15:00:00Z', sequencia=12)
        post = Mock(side_effect=[Mock(status_code=200, json=lambda: dict(conta='123', registros=[r], mais=True)),
                                Mock(status_code=200, json=lambda: dict(conta='123', registros=[], mais=False)),
                                Mock(status_code=200, json=lambda: dict(conta='123', registros=[r], mais=False))])
        sync = Sincronizador(self.h, 'sessao', lambda _: None, post)
        sync.ciclo(); sync.ciclo()
        self.assertEqual([c.kwargs['json']['apos'] for c in post.call_args_list], [0, 12, 0])
        self.assertEqual(len(self.h.ler('resultado')), 1)


if __name__ == '__main__': unittest.main()
