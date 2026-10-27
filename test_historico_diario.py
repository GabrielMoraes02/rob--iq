import csv
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import tkinter as tk
import painel

class HistoricoDiario(unittest.TestCase):
    def test_sete_em_dez_sao_setenta_porcento(self):
        linhas = [{'RESULTADO': 'WIN' if i<7 else 'LOSS', 'LUCRO_LIQUIDO': '17.4' if i<7 else '-20'} for i in range(10)]
        self.assertEqual(painel.resumo_resultados(linhas)['taxa'],70)
        self.assertIsNone(painel.resumo_resultados([])['taxa'])

    def test_empate_incluido_sem_ser_ganho(self):
        resumo=painel.resumo_resultados([{'RESULTADO':'WIN','LUCRO_LIQUIDO':'17.4'}, {'RESULTADO':'EMPATE','LUCRO_LIQUIDO':'0'}])
        self.assertEqual(resumo['taxa'],50)

    def test_tres_reaberturas_preservam_dia_e_modal_visivel(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.bot-temp') as pasta:
            base=Path(pasta)
            data=datetime.now().strftime('%d/%m/%Y')
            with (base/'V19_GENERAL_3PIPS_OTC_5_RESULTADOS.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f,delimiter=';')
                w.writerow(['DATA_HORA','ATIVO','DIRECAO','ID_ORDEM','RESULTADO','LUCRO_LIQUIDO'])
                for i in range(10):
                    w.writerow([data+f' 00:{i:02d}:00','EURUSD-OTC','CALL',str(i),'WIN' if i<7 else 'LOSS','17.4' if i<7 else '-20'])
                # Duplicate notification/row must not double the totals.
                w.writerow([data+' 00:00:00','EURUSD-OTC','CALL','0','WIN','17.4'])
            with patch.object(painel,'BASE',base):
                for ciclo in range(3):
                    root=tk.Tk()
                    try:
                        obj=painel.Painel(root)
                        self.assertEqual(obj.ler_resultados_salvos(), [])  # CSV legado nunca entra automaticamente.
                        obj.conta_historico = painel.Historico(base, '123')
                        with (base/'V19_GENERAL_3PIPS_OTC_5_RESULTADOS.csv').open(encoding='utf-8-sig', newline='') as stream:
                            for linha in csv.DictReader(stream, delimiter=';'):
                                obj.conta_historico.registrar('resultado', linha)
                        obj.atualizar_resumo_diario()
                        root.geometry('1080x720');root.update()
                        self.assertEqual(obj.taxa_valor.get(),'70,0%')
                        self.assertEqual((obj.ganhos,obj.perdas),(7,3))
                        obj.abrir_resultados();root.update()
                        self.assertEqual(len(obj.lista_resultados.get_children()),10)
                        self.assertEqual(obj.totais_historico['valor_ganhos'].get(), '+121,80')
                        self.assertEqual(obj.totais_historico['valor_perdas'].get(), '-60,00')
                        self.assertEqual(obj.totais_historico['liquido'].get(), '+61,80')
                        tabela=obj.lista_resultados
                        x=tabela.winfo_rootx()+tabela.winfo_width()//2
                        y=tabela.winfo_rooty()+tabela.winfo_height()//2
                        # Desktop hit-testing can be unavailable in a locked Windows session.
                        alvo = root.winfo_containing(x,y)
                        if alvo is not None:
                            self.assertIs(alvo,tabela)
                        self.assertTrue(tabela.winfo_ismapped())
                        self.assertGreater(tabela.winfo_height(),40)
                        self.assertLessEqual(tabela.winfo_rooty()+tabela.winfo_height(),root.winfo_rooty()+root.winfo_height())
                        self.assertIn('70,0%',obj.resumo_lista.get())
                        tabela.yview_moveto(1);root.update()
                        self.assertGreater(tabela.yview()[0],0)
                        obj.filtro_resultados.set('Ganhos');obj.preencher_resultados()
                        self.assertEqual(len(tabela.get_children()),7)
                        self.assertIn('70,0%',obj.resumo_lista.get())
                        root.update()
                        self.assertTrue(obj.cartoes_historico['valor_ganhos'].winfo_ismapped())
                        self.assertFalse(obj.cartoes_historico['valor_perdas'].winfo_ismapped())
                        obj.filtro_resultados.set('Perdas');obj.preencher_resultados();root.update()
                        self.assertEqual(len(tabela.get_children()),3)
                        self.assertTrue(obj.cartoes_historico['valor_perdas'].winfo_ismapped())
                        self.assertFalse(obj.cartoes_historico['liquido'].winfo_ismapped())
                        obj.inicio_periodo.set(data+' 00:07')
                        obj.fim_periodo.set(data+' 00:08')
                        obj.aplicar_periodo()
                        self.assertEqual(obj.totais_historico['valor_perdas'].get(), '-40,00')
                        obj.filtro_resultados.set('Todos');obj.preencher_resultados();root.update()
                        self.assertEqual(obj.totais_historico['valor_ganhos'].get(), '0,00')
                        self.assertEqual(obj.totais_historico['liquido'].get(), '-40,00')
                        self.assertTrue(all(c.winfo_ismapped() for c in obj.cartoes_historico.values()))
                        obj.fechar_resultados()
                    finally:
                        for timer in root.tk.call('after', 'info'):
                            root.after_cancel(timer)
                        root.destroy()

if __name__=='__main__': unittest.main()
