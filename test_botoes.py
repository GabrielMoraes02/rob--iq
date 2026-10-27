import io
import json
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import painel


class Botoes(unittest.TestCase):
    def setUp(self):
        import gc
        gc.collect()  # Objetos Tk de testes anteriores sao liberados na thread principal.
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.bot-temp')
        self.base = patch.object(painel, 'BASE', Path(self.temp.name))
        self.base.start()
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0.0)
        self.erros = []
        self.root.report_callback_exception = lambda tipo, valor, tb: self.erros.append((tipo.__name__, str(valor)))
        self.app = painel.Painel(self.root)
        self.app.som_ativo.set(False)
        self.root.update()

    def tearDown(self):
        for timer in self.root.tk.call('after', 'info'): self.root.after_cancel(timer)
        self.root.destroy()
        self.base.stop()
        self.temp.cleanup()
        self.assertEqual(self.erros, [])
        self.app = self.root = None
        import gc
        gc.collect()

    def filhos(self, pai):
        for filho in pai.winfo_children():
            yield filho
            yield from self.filhos(filho)

    def botao(self, pai, texto):
        return next(w for w in self.filhos(pai) if w.winfo_class() in ('TButton', 'Button') and str(w.cget('text')).startswith(texto))

    def test_disponibilidade_exibe_estado_e_motivo_da_corretora(self):
        par = 'EURUSD-OTC'
        for estado, rotulo in [('NAO_CONFIRMADA', 'Não confirmada'), ('FECHADO', 'Fechado'), ('ABERTO', 'Aberto')]:
            motivo = 'Motivo de teste em Binarias/Turbo.'
            self.app.fila.put(f'[12:00:00] {par} | DISPONIBILIDADE | {estado}; {motivo}')
            self.app.poll()
            valores = self.app.ativos.item(par, 'values')
            self.assertEqual(valores[1], rotulo)
            self.assertIn(motivo, valores[2])

    def test_sem_recuo_selecao_salvar_reabrir_e_bloquear(self):
        from configuracao import carregar_configuracao
        self.app.config_pips.set('2')
        self.app.sem_recuo_opcao.invoke()
        self.assertTrue(self.app.config_sem_recuo.get())
        self.assertEqual(str(self.app.campos_config[0].cget('state')), 'disabled')
        self.assertTrue(self.app.salvar_parametros())
        salvo = carregar_configuracao(Path(self.temp.name))
        self.assertTrue(salvo['sem_recuo'])
        self.assertEqual(salvo['pips'], 2)
        self.app.bloquear_parametros(True)
        self.app.sem_recuo_opcao.invoke()
        self.assertTrue(self.app.config_sem_recuo.get())
        self.app.bloquear_parametros(False)
        self.assertEqual(str(self.app.campos_config[0].cget('state')), 'disabled')
        self.app.sem_recuo_opcao.invoke()
        self.assertFalse(self.app.config_sem_recuo.get())
        self.assertEqual(str(self.app.campos_config[0].cget('state')), 'normal')
        self.assertEqual(self.app.config_pips.get(), '2')

    def test_catalogo_filtra_favorita_e_nao_altera_operacao(self):
        from catalogo import normalizar_catalogo
        from test_catalogo import resposta_opcoes
        antes = self.app.parametros_digitados()
        self.app.catalogo_dados = normalizar_catalogo('Opções', resposta_opcoes())
        self.app.catalogo_consultado_em = time.time()
        self.app.ver_catalogo.invoke()
        janela = self.app.catalogo_janela
        self.assertEqual(len(janela.tabela.get_children()), 3)
        janela.modalidade.set('Blitz')
        janela.busca.set('EUR/USD')
        self.assertEqual(janela.tabela.get_children(), ('Blitz:76',))
        janela.tabela.selection_set('Blitz:76')
        janela.alternar_favorito()
        self.assertIn('Blitz:76', janela.favoritos)
        janela.fechar()
        self.assertIsNone(self.root.grab_current())
        self.app.ver_catalogo.invoke()
        janela = self.app.catalogo_janela
        janela.somente_favoritos.set(True)
        janela.atualizar()
        self.assertEqual(janela.tabela.get_children(), ('Blitz:76',))
        self.assertEqual(self.app.parametros_digitados(), antes)
        self.assertIsNone(self.app.processo)
        janela.fechar()

    def test_abas_e_historico_abrem_e_fecham(self):
        for botao, _, _, chave in self.app.nav_items:
            botao.invoke()
            self.assertEqual(self.app.current_page, chave)
        self.app.navigate('inicio')
        self.botao(self.app.inicio_conteudo, 'Histórico de transações').invoke()
        self.root.update()
        self.assertIsNotNone(self.app.janela_resultados)
        self.botao(self.app.janela_resultados, '×').invoke()
        self.assertIsNone(self.app.janela_resultados)
        self.assertIsNone(self.root.grab_current())
        self.botao(self.app.inicio_conteudo, 'Abrir atividade ao vivo').invoke()
        self.assertEqual(self.app.current_page, 'atividade')

    def test_pares_aplicar_fechar_e_salvar_parametros(self):
        self.app.escolher_pares.invoke()
        self.root.update()
        modal = self.root.grab_current()
        self.assertIsNotNone(modal)
        self.botao(modal, 'Aplicar e salvar pares').invoke()
        self.assertIsNone(self.root.grab_current())
        self.app.escolher_pares.invoke()
        self.botao(self.root.grab_current(), '×').invoke()
        self.assertIsNone(self.root.grab_current())
        self.app.config_expiracao.set('30 segundos')
        self.app.salvar_config.invoke()
        self.assertEqual(json.loads((Path(self.temp.name)/'configuracao.json').read_text())['expiracao'], 0.5)

    def test_conectar_valida_e_executa_com_motor_falso(self):
        with patch.object(painel.messagebox, 'showinfo') as aviso:
            self.app.iniciar.invoke()
            aviso.assert_called_once()
        self.app.opcoes_modo[1].invoke()
        self.assertEqual(self.app.modo.get(), 'demo')
        self.app.opcoes_modo[0].invoke()
        self.app.email.insert(0, 'teste@exemplo.test')
        self.app.senha.insert(0, 'senha-ficticia')
        processo = Mock(stdin=io.StringIO(), stdout=iter([]))
        processo.poll.return_value = None
        processo.wait.return_value = 0
        with patch.object(painel.subprocess, 'Popen', return_value=processo) as abrir:
            self.app.iniciar.invoke()
            abrir.assert_called_once()
            limite = time.monotonic()+2
            while self.app.processo is not None and time.monotonic() < limite:
                self.app.poll()
                self.root.update()
                time.sleep(0.01)
        self.assertIsNone(self.app.processo)
        self.assertEqual(str(self.app.iniciar.cget('state')), 'normal')

    def test_ambos_botoes_parar_liberam_os_controles(self):
        for botao in (self.app.parar_inicio, self.app.parar):
            processo = Mock()
            processo.poll.return_value = None
            self.app.processo = processo
            self.app.bloquear_parametros(True)
            self.app.iniciar.configure(state='disabled')
            botao.configure(state='normal')
            with patch.object(painel, 'encerrar_motor') as encerrar:
                botao.invoke()
                limite=time.monotonic()+2
                while self.app.processo is not None and time.monotonic()<limite:
                    self.app.poll(); self.root.update(); time.sleep(0.01)
                encerrar.assert_called_once_with(processo)
            self.assertIsNone(self.app.processo)
            self.assertFalse(self.app.parando)
            self.assertEqual(str(self.app.iniciar.cget('state')), 'normal')
            self.assertEqual(str(self.app.escolher_pares.cget('state')), 'normal')
            self.assertEqual(str(self.app.parar.cget('state')), 'disabled')

    def test_parar_sem_sessao_nao_fica_parando(self):
        self.app.stop()
        self.assertFalse(self.app.parando)
        self.assertNotIn('Parando', self.app.status.get())

    def test_fechar_painel_espera_confirmacao_do_encerramento(self):
        processo = Mock()
        processo.poll.return_value = None
        self.app.processo = processo
        with patch.object(painel, 'encerrar_motor') as encerrar, patch.object(self.app, 'destruir_painel') as destruir:
            self.app.close()
            self.assertTrue(self.app.fechar_apos_parada)
            destruir.assert_not_called()
            limite = time.monotonic()+2
            while self.app.processo is not None and time.monotonic()<limite:
                self.app.poll(); self.root.update(); time.sleep(0.01)
            encerrar.assert_called_once_with(processo)
            destruir.assert_called_once()


if __name__ == '__main__': unittest.main()
