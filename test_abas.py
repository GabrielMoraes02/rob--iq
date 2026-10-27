import tkinter as tk
import unittest
from painel import Painel


class Abas(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Painel(self.root)

    def tearDown(self):
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.root.destroy()

    def test_inicio_reune_login_e_historico(self):
        self.assertEqual(self.app.current_page, 'inicio')
        self.assertEqual(set(self.app.pages), {'inicio', 'atividade', 'ajuda'})
        self.assertIn(str(self.app.inicio_conteudo), str(self.app.email))
        self.assertIn(str(self.app.inicio_conteudo), str(self.app.iniciar))
        self.app.navigate('conexao')
        self.assertEqual(self.app.current_page, 'inicio')

    def test_confirmacao_da_conta_abre_atividade_ao_vivo(self):
        self.app.fila.put('Conta confirmada: PRACTICE. Modo: SIMULACAO')
        self.app.poll()
        self.assertEqual(self.app.current_page, 'atividade')
        self.assertIn(str(self.app.pages['atividade']), str(self.app.ativos))
        self.assertIn(str(self.app.pages['atividade']), str(self.app.historico))
        self.app.navigate('inicio')
        self.assertEqual(self.app.current_page, 'inicio')

    def test_sincronizacao_nao_apaga_eventos_ao_vivo(self):
        sync = object()
        self.app.sincronizador_nuvem = sync
        self.app.evento('12:00:00', 'EURUSD', 'Sinal desta sessão', 'evento ao vivo')
        ids = self.app.historico.get_children()
        self.app.fila.put(('nuvem', sync, 'Histórico sincronizado.'))
        self.app.poll()
        self.assertEqual(self.app.historico.get_children(), ids)
        self.assertEqual(self.app.nuvem_status.get(), 'Histórico sincronizado.')


if __name__ == '__main__': unittest.main()
