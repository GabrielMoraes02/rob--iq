"""Histórico futuro por conta IQ Option. Sem senhas ou sessões em disco."""
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

URL = 'https://xpypzgflwggpcackzcwg.supabase.co/functions/v1/historico-conta'
CHAVE_PUBLICA = 'sb_publishable_h8-JLgQryAWRzr83ycrFSA_zgieq64T'


def conta_valida(conta):
    conta = str(conta)
    if not conta.isascii() or not conta.isdigit() or int(conta) <= 0:
        raise ValueError('Identidade da conta não confirmada pela corretora.')
    return conta


class Historico:
    def __init__(self, base, conta):
        self.conta = conta_valida(conta)
        self.pasta = Path(base) / 'historico_contas' / self.conta / 'PRACTICE'
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.pasta / 'historico.sqlite3'
        with self.conectar() as db:
            db.execute('''create table if not exists registros (
                id text primary key, tipo text not null, dados text not null,
                ocorrido_em text not null, enviado integer not null default 0)''')

    @contextmanager
    def conectar(self):
        db = sqlite3.connect(self.arquivo, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def registrar(self, tipo, dados):
        if tipo not in ('evento', 'resultado'):
            raise ValueError('Tipo de histórico inválido.')
        identificador = ('resultado:' + str(dados['ID_ORDEM']) if tipo == 'resultado'
                         else str(uuid.uuid4()))
        ocorrido = datetime.now(timezone.utc).isoformat()
        with self.conectar() as db:
            db.execute('insert or ignore into registros values (?, ?, ?, ?, 0)',
                       (identificador, tipo, json.dumps(dados, ensure_ascii=False), ocorrido))
        return identificador

    def ler(self, tipo):
        with self.conectar() as db:
            linhas = db.execute('select dados from registros where tipo=? order by ocorrido_em, id', (tipo,)).fetchall()
        return [json.loads(linha[0]) for linha in linhas]

    def pendentes(self):
        with self.conectar() as db:
            linhas = db.execute('select id, tipo, dados, ocorrido_em from registros where enviado=0 order by ocorrido_em, id limit 200').fetchall()
        return [dict(id=r[0], tipo=r[1], dados=json.loads(r[2]), ocorrido_em=r[3]) for r in linhas]

    def aplicar(self, enviados, recebidos):
        # ACK somente depois do sucesso remoto. Repetir o lote é seguro.
        with self.conectar() as db:
            for r in recebidos:
                db.execute('insert or ignore into registros values (?, ?, ?, ?, 1)',
                           (r['id'], r['tipo'], json.dumps(r['dados'], ensure_ascii=False), r['ocorrido_em']))
            db.executemany('update registros set enviado=1 where id=?', [(r['id'],) for r in enviados])


class Sincronizador:
    def __init__(self, historico, ssid, notificar, transporte=None):
        self.historico = historico
        self.ssid = ssid
        self.notificar = notificar
        self.parar = threading.Event()
        self.transporte = transporte

    def ciclo(self):
        import requests
        post = self.transporte or requests.post
        pagina = 0
        while not self.parar.is_set():
            lote = self.historico.pendentes()
            resposta = post(URL, json={'ssid': self.ssid, 'conta': self.historico.conta,
                'registros': lote, 'apos': pagina}, headers={'apikey': CHAVE_PUBLICA}, timeout=(5, 25))
            if resposta.status_code != 200:
                raise RuntimeError('Sessão não validada pela nuvem' if resposta.status_code == 401
                                   else 'Nuvem indisponível; os registros continuam na fila local')
            dados = resposta.json()
            if str(dados['conta']) != self.historico.conta:
                raise RuntimeError('A nuvem retornou outra conta; sincronização bloqueada')
            self.historico.aplicar(lote, dados['registros'])
            if dados['registros']:
                pagina = dados['registros'][-1]['sequencia']
            if not dados['mais'] and not self.historico.pendentes():
                break
        # Releitura a partir de zero no próximo ciclo evita perder inserções
        # concorrentes cuja transação confirme fora da ordem da sequência.

    def executar(self):
        while not self.parar.is_set():
            try:
                self.ciclo()
                self.notificar('Histórico salvo e atualizado no Supabase.')
            except Exception:
                # Não publicar exceções HTTP que possam incluir uma sessão.
                self.notificar('Histórico sem conexão com a nuvem · fila local preservada; nova tentativa automática.')
            self.parar.wait(15)

