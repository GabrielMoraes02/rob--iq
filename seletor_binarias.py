import time
import tkinter as tk
from tkinter import ttk
from catalogo import pesquisar


class SeletorBinarias(tk.Frame):
    def __init__(self, app):
        super().__init__(app.root, bg='#101217')
        self.app = app
        self.marcados = {p for p, v in app.pares_config.items() if v.get()}
        self.place(x=0, y=0, relwidth=1, relheight=1)
        quadro = ttk.Frame(self, padding=24)
        quadro.pack(fill='both', expand=True, padx=15, pady=15)
        topo = ttk.Frame(quadro)
        topo.pack(fill='x')
        ttk.Label(topo, text='Binárias · pares do robô', font=('Segoe UI', 20)).pack(side='left')
        ttk.Button(topo, text='×', width=3, command=self.fechar).pack(side='right')
        ttk.Label(quadro, text='Marque e desmarque com a sessão conectada. Ordens já abertas continuam até o resultado.',
                  wraplength=850).pack(anchor='w', pady=(10, 12))
        self.busca = tk.StringVar()
        self.otc = tk.StringVar(value='Todos')
        self.disponiveis = tk.BooleanVar(value=True)
        self.somente_marcados = tk.BooleanVar(value=False)
        filtros = ttk.Frame(quadro)
        filtros.pack(fill='x')
        ttk.Label(filtros, text='Buscar ativo:').pack(side='left')
        ttk.Entry(filtros, textvariable=self.busca, width=30).pack(side='left', padx=8)
        ttk.Combobox(filtros, textvariable=self.otc, values=('Todos', 'Só OTC', 'Sem OTC'),
                     state='readonly', width=12).pack(side='left', padx=8)
        ttk.Checkbutton(filtros, text='Só disponíveis', variable=self.disponiveis, command=self.atualizar).pack(side='left', padx=8)
        ttk.Checkbutton(filtros, text='Selecionados', variable=self.somente_marcados, command=self.atualizar).pack(side='left', padx=8)
        self.observadores = [(v, v.trace_add('write', lambda *_: self.atualizar())) for v in (self.busca, self.otc)]
        area = ttk.Frame(quadro)
        area.pack(fill='both', expand=True, pady=12)
        self.tabela = ttk.Treeview(area, columns=('marcado', 'par', 'nome', 'estado'), show='headings', selectmode='browse')
        for chave, titulo, tamanho in [('marcado', '✓', 40), ('par', 'Ativo', 170), ('nome', 'Nome na corretora', 300), ('estado', 'Binárias', 160)]:
            self.tabela.heading(chave, text=titulo)
            self.tabela.column(chave, width=tamanho, stretch=chave in ('nome', 'par'))
        self.tabela.pack(side='left', fill='both', expand=True)
        barra = ttk.Scrollbar(area, orient='vertical', command=self.tabela.yview)
        barra.pack(side='right', fill='y')
        self.tabela.configure(yscrollcommand=barra.set)
        self.tabela.bind('<Double-1>', self.alternar)
        self.tabela.bind('<space>', self.alternar)
        self.tabela.bind('<ButtonRelease-1>', self.clicar)
        botoes = ttk.Frame(quadro)
        botoes.pack(fill='x')
        ttk.Button(botoes, text='Marcar disponíveis visíveis', command=self.marcar_visiveis).pack(side='left')
        ttk.Button(botoes, text='Limpar seleção', command=self.limpar).pack(side='left', padx=10)
        self.contagem = tk.StringVar()
        self.status = tk.StringVar()
        ttk.Label(quadro, textvariable=self.contagem).pack(anchor='w', pady=(10, 4))
        ttk.Label(quadro, textvariable=self.status, wraplength=950).pack(anchor='w')
        self.aplicar_botao = ttk.Button(quadro, text='Aplicar e salvar pares', command=self.aplicar, style='Start.TButton')
        self.aplicar_botao.pack(fill='x', pady=(12, 0))
        self.bind('<Escape>', lambda _: self.fechar())
        self.atualizar()
        self.grab_set()
        self.focus_set()

    def atualizar(self):
        if not hasattr(self, 'tabela'): return
        linhas = {r['par']: r.copy() for r in self.app.binarias_dados}
        for par in self.marcados:
            linhas.setdefault(par, {'par': par, 'nome': par, 'estado': 'Não confirmado', 'otc': 'OTC' in par})
        fresco = 0 <= time.time() - self.app.binarias_consultado_em <= 20
        self.linhas = linhas
        self.tabela.delete(*self.tabela.get_children())
        for par, r in sorted(linhas.items()):
            estado = r['estado'] if fresco else 'Não confirmado'
            if self.disponiveis.get() and estado != 'Aberto' and not self.somente_marcados.get(): continue
            if self.somente_marcados.get() and par not in self.marcados: continue
            if self.otc.get() != 'Todos' and (self.otc.get() == 'Só OTC') != r['otc']: continue
            if pesquisar(self.busca.get()) not in pesquisar(par + ' ' + r['nome']): continue
            self.tabela.insert('', 'end', iid=par, values=('☑' if par in self.marcados else '☐', par, r['nome'], estado))
        self.contagem.set(f'{len(self.tabela.get_children())} exibidos · {len(self.marcados)} selecionados (inclui os ocultos pelo filtro).')
        if self.app.pedido_pares is not None:
            self.status.set('Aplicando seleção no motor…')
        elif not fresco:
            self.status.set(self.app.binarias_erro or 'Aguardando consulta de Binárias. Conecte em Só observar para carregar a lista.')
        else:
            self.status.set('Binárias/Turbo · atualização a cada ~10s + resposta da API. Ativos fora de Binárias não recebem novas entradas.')
        self.aplicar_botao.configure(state='disabled' if self.app.pedido_pares is not None else 'normal')

    def clicar(self, evento):
        if self.tabela.identify_column(evento.x) == '#1': self.alternar()

    def alternar(self, _evento=None):
        selecionado = self.tabela.selection()
        if not selecionado: return
        par = selecionado[0]
        if par in self.marcados:
            self.marcados.remove(par)
        elif time.time()-self.app.binarias_consultado_em <= 20 and self.linhas[par]['estado'] == 'Aberto':
            self.marcados.add(par)
        self.atualizar()

    def marcar_visiveis(self):
        if time.time()-self.app.binarias_consultado_em <= 20:
            self.marcados.update(p for p in self.tabela.get_children() if self.linhas[p]['estado'] == 'Aberto')
        self.atualizar()

    def limpar(self):
        self.marcados.clear()
        self.atualizar()

    def aplicar(self):
        if self.app.aplicar_pares_selecionados(sorted(self.marcados)):
            if self.app.pedido_pares is None: self.fechar()
            else: self.atualizar()

    def fechar(self):
        for v, cb in self.observadores: v.trace_remove('write', cb)
        self.observadores.clear()
        self.grab_release()
        self.app.seletor_binarias = None
        self.destroy()
