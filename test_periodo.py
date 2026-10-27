import unittest
import csv
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
import painel

class Periodo(unittest.TestCase):
    def test_dia_final_inclusivo(self):
        a,b=painel.limites_periodo('23/10/2026','23/10/2026')
        self.assertEqual(a,datetime(2026,10,23))
        self.assertEqual((b.hour,b.minute,b.second),(23,59,59))
    def test_horario_final_inclui_minuto(self):
        a,b=painel.limites_periodo('23/10/2026 20:00','23/10/2026 21:00')
        self.assertEqual((b.hour,b.minute,b.second),(21,0,59))
    def test_invalidos(self):
        for a,b in [('31/02/2026',''),('24/10/2026','23/10/2026'),('20:00','')]:
            with self.subTest(a=a),self.assertRaises(ValueError): painel.limites_periodo(a,b)
    def test_filtro_datas_tipo_e_ordenacao(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.bot-temp') as pasta:
            root=Path(pasta)
            with (root/'V19_GENERAL_3PIPS_OTC_5_RESULTADOS.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f,delimiter=';')
                w.writerow(['DATA_HORA','ATIVO','DIRECAO','ID_ORDEM','RESULTADO','LUCRO_LIQUIDO'])
                for hora,oid,resultado,valor in [('22/10/2026 20:00:00','1','WIN','17.40'),('23/10/2026 23:59:59','2','LOSS','-20'),('23/10/2026 20:51:00','3','WIN','17.40'),('24/10/2026 00:00:00','4','WIN','17.40')]:
                    w.writerow([hora,'EURUSD-OTC','CALL',oid,resultado,valor])
            obj=painel.Painel.__new__(painel.Painel)
            obj.conta_historico = painel.Historico(root, '123')
            with (root/'V19_GENERAL_3PIPS_OTC_5_RESULTADOS.csv').open(encoding='utf-8-sig', newline='') as stream:
                for linha in csv.DictReader(stream, delimiter=';'):
                    obj.conta_historico.registrar('resultado', linha)
            with patch.object(painel,'BASE',root):
                limites=painel.limites_periodo('23/10/2026','23/10/2026')
                self.assertEqual([r['ID_ORDEM'] for r in obj.ler_resultados_salvos('Todos',*limites)],['2','3'])
                self.assertEqual([r['ID_ORDEM'] for r in obj.ler_resultados_salvos('Ganhos',*limites)],['3'])
                self.assertEqual([r['ID_ORDEM'] for r in obj.ler_resultados_salvos('Perdas',*limites)],['2'])

if __name__=='__main__': unittest.main()
