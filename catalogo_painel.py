"""Busca e filtros do catalogo; nenhuma selecao nesta tela autoriza ordens."""
import json
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from catalogo import filtrar


class CatalogoPainel(tk.Frame):
    def __init__(self, app, base):
        super().__init__(app.root, bg='#101217')
        self.app = app
        self.arquivo = base / 'favoritos_catalogo.json'
        try:
            dados = json.loads(self.arquivo.read_text(encoding='utf-8'))
            self.favoritos = set(s for s in dados if isinstance(s, str)) if isinstance(dados, list) else set()
        except (OSError, ValueError):
            self.favoritos = set()
        self.place(x=0, y=0, relwidth=1, relheight=1)
        caixa = ttk.Frame(self, padding=22)
        caixa.pack(fill='both', expand=True, padx=12, pady=12)
        topo = ttk.Frame(caixa)
        topo.pack(fill='x')
        ttk.Label(topo, text='Ativos da corretora', font=('Segoe UI', 20)).pack(side='left')
        ttk.Button(topo, text='×', width=3, command=self.fechar).pack(side='right')
        ttk.Label(caixa, text='Catálogo para consulta. Os filtros e favoritos não mudam os pares nem as operações do robô.',
                  wraplength=850).pack(anchor='w', pady=(8, 12))
        self.busca = tk.StringVar()
        self.modalidade = tk.StringVar(value='Todas')
        self.otc = tk.StringVar(value='Todos')
        self.estado = tk.StringVar(value='Todos')
        self.somente_favoritos = tk.BooleanVar(value=False)
        self.observadores = []
        filtros = ttk.Frame(caixa)
        filtros.pack(fill='x')
        for col, (titulo, var, opcoes) in enumerate([
                ('Pesquisar nome ou ticker', self.busca, None),
                ('Modalidade', self.modalidade, ['Todas', 'Opções', 'Blitz', 'Binárias', 'Turbo', 'Digital', 'Margem', 'Margem Forex', 'Margem CFD', 'Margem Cripto']),
                ('OTC', self.otc, ['Todos', 'Só OTC', 'Sem OTC']),
                ('Disponibilidade', self.estado, ['Todos', 'Aberto', 'Fechado', 'Não confirmado'])]):
            filtros.columnconfigure(col, weight=2 if col == 0 else 1)
            quadro = ttk.Frame(filtros)
            quadro.grid(row=0, column=col, sticky='ew', padx=(0, 10))
            ttk.Label(quadro, text=titulo).pack(anchor='w')
            campo = ttk.Combobox(quadro, textvariable=var, values=opcoes, state='readonly', width=18) if opcoes else ttk.Entry(quadro, textvariable=var)
            campo.pack(fill='x', pady=(4, 8))
            self.observadores.append((var, var.trace_add('write', lambda *_: self.atualizar())))
        ttk.Checkbutton(caixa, text='Watchlist · mostrar só favoritos', variable=self.somente_favoritos,
                        command=self.atualizar).pack(anchor='w', pady=(0, 8))
        grade = ttk.Frame(caixa)
        grade.pack(fill='both', expand=True)
        self.tabela = ttk.Treeview(grade, columns=('favorito', 'nome', 'simbolo', 'modalidade', 'otc', 'estado', 'retorno'), show='headings', selectmode='browse')
        for chave, titulo, largura in [('favorito', '★', 38), ('nome', 'Nome', 220), ('simbolo', 'Ticker', 130),
                ('modalidade', 'Modalidade', 120), ('otc', 'OTC', 45), ('estado', 'Disponibilidade', 140), ('retorno', 'Retorno informado', 130)]:
            self.tabela.heading(chave, text=titulo)
            self.tabela.column(chave, width=largura, minwidth=35, stretch=chave in ('nome', 'simbolo'))
        barra = ttk.Scrollbar(grade, orient='vertical', command=self.tabela.yview)
        horizontal = ttk.Scrollbar(grade, orient='horizontal', command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=barra.set, xscrollcommand=horizontal.set)
        grade.columnconfigure(0, weight=1)
        grade.rowconfigure(0, weight=1)
        self.tabela.grid(row=0, column=0, sticky='nsew')
        barra.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.contagem = tk.StringVar()
        self.situacao = tk.StringVar()
        ttk.Label(caixa, textvariable=self.contagem).pack(anchor='w', pady=(10, 3))
        ttk.Label(caixa, textvariable=self.situacao, wraplength=900).pack(anchor='w')
        ttk.Button(caixa, text='★ Adicionar / remover favorito', command=self.alternar_favorito).pack(anchor='w', pady=(10, 0))
        self.tabela.bind('<Double-1>', self.alternar_favorito)
        self.bind('<Escape>', lambda _: self.fechar())
        self.atualizar()
        self.grab_set()
        self.focus_set()

    def atualizar(self):
        if not hasattr(self, 'tabela'):
            return
        dados = self.app.catalogo_dados
        filtrados = filtrar(dados, self.busca.get(), self.modalidade.get(), self.otc.get(), self.estado.get(),
                            self.favoritos if self.somente_favoritos.get() else None)
        selecao = self.tabela.selection()
        self.tabela.delete(*self.tabela.get_children())
        for item in sorted(filtrados, key=lambda x: (x['nome'].casefold(), x['modalidade'])):
            retorno = '—' if item['retorno'] is None else f"{item['retorno']:g}%"
            self.tabela.insert('', 'end', iid=item['chave'], values=('★' if item['chave'] in self.favoritos else '☆',
                item['nome'], item['simbolo'], item['modalidade'], 'Sim' if item['otc'] else 'Não', item['estado'], retorno))
        if selecao and self.tabela.exists(selecao[0]): self.tabela.selection_set(selecao[0])
        self.contagem.set(f'{len(filtrados)} instrumentos exibidos de {len(dados)} recebidos · o mesmo ativo pode existir em várias modalidades.')
        data = self.app.catalogo_consultado_em
        if not data:
            self.situacao.set('Conecte a sessão para carregar o catálogo da sua conta. Em Só observar, nenhuma ordem é enviada.')
        else:
            texto = 'Consultado em ' + datetime.fromtimestamp(data).strftime('%d/%m %H:%M:%S')
            ativo = self.app.processo and self.app.processo.poll() is None
            texto += ' · atualização automática a cada ciclo de consulta.' if ativo else ' · sessão encerrada; dados da última consulta.'
            if self.app.catalogo_falhas:
                texto += ' Lista incompleta: ' + ', '.join(self.app.catalogo_falhas)
            texto += ' — significa retorno não informado pela API.'
            self.situacao.set(texto)

    def alternar_favorito(self, _evento=None):
        selecionados = self.tabela.selection()
        if not selecionados: return
        chave = selecionados[0]
        if chave in self.favoritos: self.favoritos.remove(chave)
        else: self.favoritos.add(chave)
        try:
            temporario = self.arquivo.with_suffix('.tmp')
            temporario.write_text(json.dumps(sorted(self.favoritos), ensure_ascii=False), encoding='utf-8')
            temporario.replace(self.arquivo)
        except OSError:
            self.situacao.set('Não foi possível salvar os favoritos neste computador.')
            return
        self.atualizar()

    def fechar(self):
        for variavel, callback in self.observadores:
            variavel.trace_remove('write', callback)
        self.observadores.clear()
        self.grab_release()
        self.app.catalogo_janela = None
        self.destroy()
