import json
import csv
try:
    import winsound
except ImportError:
    winsound = None
import time
from datetime import datetime, timedelta
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from configuracao import PADRAO, PARES_DISPONIVEIS, carregar_configuracao, salvar_configuracao, validar_configuracao
from historico_nuvem import Historico, Sincronizador
from caminhos import pasta_dados, comando_motor, VERSAO

BASE = pasta_dados()
EXPLICACOES = {
    'DEMO_ENVIADA': 'Ordem automática enviada na conta DEMO (saldo virtual). Veja direção e ID nos detalhes.',
    'ORDEM_RECUSADA': 'A corretora recusou a ordem. Veja os detalhes.',
    'ERRO_ORDEM': 'Falha ao enviar a ordem. Confira a plataforma antes de concluir se houve entrada.',
    'RESULTADO_WIN': 'Resultado confirmado pela corretora: ganho na demo.',
    'RESULTADO_LOSS': 'Resultado confirmado pela corretora: perda na demo.',
    'RESULTADO_EMPATE': 'Resultado confirmado pela corretora: empate.',
    'RESULTADO_NAO_CONFIRMADO': 'Resultado não confirmado. Confira a operação na plataforma.',
    'BOLINHA_CALCULADA': 'Primeiro sinal encontrado. Aguarda confirmação na próxima vela.',
    'SETA_CONFIRMADA': 'Direção confirmada. Aguarda o recuo configurado contra a abertura da nova vela.',
    'SETA_DETECTADA': 'Seta observada em tempo real. Aguarda o recuo nesta mesma vela, até o segundo 29.',
    'CORRECAO_3_PIPS': 'O último preço recebido atingiu a correção de 3 pips dentro da janela.',
    'CORRECAO_PIPS': 'O último preço recebido atingiu o recuo configurado dentro da janela.',
    'CONFIGURACAO': 'Parâmetros utilizados nesta sessão.',
    'SINAL_SIMULADO': 'Entrada simulada registrada. Nenhuma ordem foi enviada.',
    'CANCELADO_POR_CONTRARIO': 'Apareceu um sinal contrário. A oportunidade foi cancelada.',
    'DESCARTADO': 'A oportunidade não cumpriu as condições ou passou do horário.',
    'BLOQUEADO': 'Uma condição de segurança impediu a entrada.',
    'SEM_VELAS': 'A corretora não retornou preços nesta consulta.',
    'ERRO_LEITURA': 'Não foi possível ler ou processar os preços.',
    'RECONEXAO_NECESSARIA': 'A conexão falhou. O bot tentará conectar novamente.',
    'TENTATIVA_RECONEXAO': 'Tentando restabelecer a conexão.',
    'RECONECTADO': 'Conexão restabelecida. Os sinais antigos foram descartados.',
    'ENCERRADO_SEGURO': 'O bot parou porque não conseguiu restabelecer a conexão.',
    'ERRO_DISPONIBILIDADE': 'Não foi possível confirmar quais ativos estão abertos.',
}

def limites_periodo(inicio='', fim=''):
    def converter(texto, final=False):
        texto = texto.strip()
        if not texto:
            return None
        for formato in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
            try:
                valor = datetime.strptime(texto, formato)
                if final and formato == '%d/%m/%Y':
                    valor += timedelta(days=1, microseconds=-1)
                elif final and formato == '%d/%m/%Y %H:%M':
                    valor += timedelta(minutes=1, microseconds=-1)
                return valor
            except ValueError:
                pass
        raise ValueError('Use DD/MM/AAAA ou DD/MM/AAAA HH:MM.')
    a, b = converter(inicio), converter(fim, final=True)
    if a is not None and b is not None and a > b:
        raise ValueError('O início precisa ser anterior ao fim do período.')
    return a, b


def resumo_resultados(linhas):
    ganhos = sum(item['RESULTADO'] == 'WIN' for item in linhas)
    perdas = sum(item['RESULTADO'] == 'LOSS' for item in linhas)
    empates = sum(item['RESULTADO'] == 'EMPATE' for item in linhas)
    total = ganhos + perdas + empates
    return {'ganhos': ganhos, 'perdas': perdas, 'empates': empates,
            'total': total, 'taxa': ganhos * 100 / total if total else None,
            'valor_ganhos': sum(float(item['LUCRO_LIQUIDO']) for item in linhas if item['RESULTADO'] == 'WIN'),
            'valor_perdas': sum(float(item['LUCRO_LIQUIDO']) for item in linhas if item['RESULTADO'] == 'LOSS'),
            'liquido': sum(float(item['LUCRO_LIQUIDO']) for item in linhas)}


class Painel:
    def __init__(self, root):
        self.root = root
        self.processo = None
        self.fila = queue.Queue()
        self.conta_historico = None
        self.sincronizador_nuvem = None
        self.erro_sessao = ''
        self.nuvem_status = tk.StringVar(value='Histórico na nuvem · aguardando login da conta.')
        self.total = self.ordens = self.ganhos = self.perdas = self.empates = 0
        self.liquido = 0.0
        self.ids_resultados = set()
        self.registros = {}
        self.modo_sessao = 'simulacao'
        self.modo = tk.StringVar(value='simulacao')
        try:
            configuracao = carregar_configuracao(BASE)
            self.erro_configuracao = ''
        except (OSError, ValueError, TypeError):
            configuracao = dict(PADRAO)
            self.erro_configuracao = 'Configuração salva inválida. Revise e salve os parâmetros antes de iniciar.'
        self.config_pips = tk.StringVar(value=str(configuracao['pips']).replace('.', ','))
        self.config_valor = tk.StringVar(value=str(configuracao['valor']).replace('.', ','))
        self.config_expiracao = tk.StringVar(value=str(configuracao['expiracao']))
        self.pares_config = {par: tk.BooleanVar(value=par in configuracao['pares']) for par in PARES_DISPONIVEIS}
        self.pares_texto = tk.StringVar(value=f"Escolher pares · {len(configuracao['pares'])} selecionados")
        self.config_status = tk.StringVar(value=self.erro_configuracao or 'Parâmetros aplicados ao iniciar a próxima sessão.')
        self.som_ativo = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Sessão parada · Conecte sua conta para começar.')
        self.saldo_texto = tk.StringVar(value='O saldo aparece após a conexão com a conta demo.')
        self.resultado_texto = tk.StringVar(value='Nenhum resultado confirmado nesta sessão')
        self.contagem = tk.StringVar(value='Nenhuma entrada registrada')
        self.entradas_ativas = {}
        self.ultima_entrada = None
        self.entrada_estado = tk.StringVar(value='')
        self.entrada_par = tk.StringVar(value='')
        self.entrada_info = tk.StringVar(value='')
        self.entrada_abertas = tk.StringVar(value='')
        self.ultimo_saldo_recebido = None
        self.saldo_valor = tk.StringVar(value='—')
        self.liquido_valor = tk.StringVar(value='0,00')
        self.ganhos_valor = tk.StringVar(value='0')
        self.perdas_valor = tk.StringVar(value='0')
        self.taxa_valor = tk.StringVar(value='—')
        self.resumo_dia_texto = tk.StringVar(value='Carregando resultados do dia…')
        self.bg, self.surface, self.muted = '#17191f', '#24262e', '#9398a5'
        root.title('Painel IQ Option | Conta demo' + (f' | Windows {VERSAO}' if getattr(sys, 'frozen', False) else ''))
        root.geometry('1280x820')
        root.minsize(1080, 720)
        root.configure(bg=self.bg)
        st = ttk.Style()
        st.theme_use('clam')
        st.configure('.', font=('Segoe UI Variable Text', 10))
        st.configure('TFrame', background=self.bg)
        st.configure('TLabel', background=self.bg, foreground='#e4e6eb')
        st.configure('Sub.TLabel', foreground=self.muted, font=('Segoe UI Variable Text', 10))
        st.configure('TButton', background='#30333c', foreground='#e4e6eb', padding=(18, 12), borderwidth=0)
        st.map('TButton', background=[('active', '#41454f')], foreground=[('disabled', '#65718a')])
        st.configure('Start.TButton', background='#f58220', foreground='#f4f5f7', font=('Segoe UI Variable Text', 11, 'bold'))
        st.map('Start.TButton', background=[('disabled', '#4a3527'), ('active', '#ff963d')])
        st.configure('Stop.TButton', foreground='#f27d88')
        st.configure('TEntry', fieldbackground='#2d3039', foreground='#e9eaef', insertcolor='#f4f5f7', padding=11, borderwidth=0)
        st.configure('TRadiobutton', background=self.bg, foreground='#d8dbe4', padding=10)
        st.map('TRadiobutton', background=[('active', '#292c34')])
        st.configure('Treeview', background=self.surface, fieldbackground=self.surface, foreground='#c8cbd4', rowheight=42, borderwidth=0, font=('Segoe UI Variable Text', 10))
        st.configure('Vertical.TScrollbar', background='#40444f', troughcolor=self.bg, borderwidth=0, arrowsize=12)
        st.configure('Treeview.Heading', background='#2b2e37', foreground='#9fa4b2', padding=(10, 12), relief='flat', font=('Segoe UI Variable Text', 9))
        st.map('Treeview', background=[('selected', '#493326')], foreground=[('selected', '#ffc493')])
        # Fixed content gutter; navigation expands over it without resizing the data.
        content = tk.Frame(root, bg=self.bg)
        self.content = content
        content.pack(fill='both', expand=True, padx=(240, 24), pady=20)
        top = tk.Frame(content, bg=self.bg)
        top.pack(fill='x', pady=(0, 22))
        st.configure('TCheckbutton', background=self.bg, foreground=self.muted, padding=6)
        st.map('TCheckbutton', background=[('active', self.bg)])
        self.page_title = tk.StringVar(value='Início')
        tk.Label(top, text='Painel IQ Option', bg=self.bg, fg='#969ba8', font=('Segoe UI Variable Text', 9, 'bold')).pack(anchor='w')
        tk.Label(top, textvariable=self.page_title, bg=self.bg, fg='#f4f5f7', font=('Segoe UI Variable Display', 25)).pack(side='left', pady=(4, 0))
        tk.Label(top, text='●  Ambiente demo', bg='#233b31', fg='#65c78b', padx=16, pady=8, font=('Segoe UI Variable Text', 10)).pack(side='right')
        ttk.Checkbutton(top, text='Som nas entradas', variable=self.som_ativo).pack(side='right', padx=(0, 18))
        statusbar = tk.Frame(content, bg='#252830', padx=16, pady=12)
        statusbar.pack(fill='x', pady=(0, 22))
        self.parar_inicio = ttk.Button(statusbar, text='■  Parar bot', command=self.stop, style='Stop.TButton', state='disabled')
        self.parar_inicio.pack(side='right', padx=(10, 0))
        ttk.Button(statusbar, text='Início  →', command=lambda: self.navigate('inicio')).pack(side='right', padx=(10, 0))
        status_textos = tk.Frame(statusbar, bg='#252830')
        status_textos.pack(side='left', fill='x', expand=True)
        tk.Label(status_textos, textvariable=self.status, bg='#252830', fg='#b9bfcc', anchor='w', wraplength=650, font=('Segoe UI Variable Text', 10)).pack(fill='x')
        self.destaque_entrada = tk.Frame(status_textos, bg='#252830')
        tk.Label(self.destaque_entrada, textvariable=self.entrada_estado, bg='#252830', fg='#ffb56b', anchor='w', font=('Segoe UI Variable Text', 9, 'bold')).pack(fill='x', pady=(8, 0))
        self.label_par_entrada = tk.Label(self.destaque_entrada, textvariable=self.entrada_par, bg='#252830', fg='#65c78b', anchor='w', font=('Segoe UI Variable Display', 24, 'bold'))
        self.label_par_entrada.pack(fill='x')
        tk.Label(self.destaque_entrada, textvariable=self.entrada_info, bg='#252830', fg='#e7e9ef', anchor='w', wraplength=650, font=('Segoe UI Variable Text', 10)).pack(fill='x', pady=(2, 0))
        tk.Label(self.destaque_entrada, textvariable=self.entrada_abertas, bg='#252830', fg='#b9bfcc', anchor='w', wraplength=650, font=('Segoe UI Variable Text', 9)).pack(fill='x', pady=(4, 0))
        host = tk.Frame(content, bg=self.bg)
        host.pack(fill='both', expand=True)
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        self.pages = {}
        for key in ('inicio', 'atividade', 'ajuda'):
            page = tk.Frame(host, bg=self.bg)
            page.grid(row=0, column=0, sticky='nsew')
            self.pages[key] = page
        # Início reúne login, saldo, resultados e parâmetros em uma página rolável.
        self.inicio_canvas = tk.Canvas(self.pages['inicio'], bg=self.bg, highlightthickness=0)
        inicio_scroll = ttk.Scrollbar(self.pages['inicio'], orient='vertical', command=self.inicio_canvas.yview)
        inicio_scroll.pack(side='right', fill='y')
        self.inicio_canvas.pack(side='left', fill='both', expand=True)
        self.inicio_canvas.configure(yscrollcommand=inicio_scroll.set)
        main = tk.Frame(self.inicio_canvas, bg=self.bg)
        self.inicio_conteudo = main
        inicio_janela = self.inicio_canvas.create_window((0, 0), window=main, anchor='nw')
        main.bind('<Configure>', lambda e: self.inicio_canvas.configure(scrollregion=self.inicio_canvas.bbox('all')))
        self.inicio_canvas.bind('<Configure>', lambda e: self.inicio_canvas.itemconfigure(inicio_janela, width=e.width))
        inicio_colunas = tk.Frame(main, bg=self.bg)
        inicio_colunas.pack(fill='x')
        inicio_colunas.columnconfigure(0, weight=1, uniform='inicio')
        inicio_colunas.columnconfigure(1, weight=1, uniform='inicio')
        login_parent = tk.Frame(inicio_colunas, bg=self.bg)
        login_parent.grid(row=0, column=0, sticky='nsew', padx=(0, 20))
        resumo_parent = tk.Frame(inicio_colunas, bg=self.bg)
        resumo_parent.grid(row=0, column=1, sticky='nsew')
        cards = tk.Frame(resumo_parent, bg=self.bg)
        cards.pack(fill='x')
        for i, (titulo, var, nota, cor) in enumerate([
            ('Saldo disponível demo', self.saldo_valor, 'Informado pela corretora', '#e9eaef'),
            ('Líquido do dia', self.liquido_valor, 'Todas as sessões', '#65c78b'),
            ('Ganhos do dia', self.ganhos_valor, 'Confirmados', '#65c78b'),
            ('Perdas do dia', self.perdas_valor, 'Confirmados', '#ef7c86'),
            ('Taxa de acerto', self.taxa_valor, 'Ganhos / concluídas', '#e9eaef')]):
            cards.columnconfigure(0, weight=1, uniform='cards')
            cards.columnconfigure(1, weight=1, uniform='cards')
            card = tk.Frame(cards, bg=self.surface, padx=14, pady=14, highlightbackground='#343741', highlightthickness=1)
            card.grid(row=0 if i == 0 else 1+(i-1)//2, column=0 if i == 0 else (i-1)%2, columnspan=2 if i == 0 else 1, sticky='nsew', padx=(0 if i == 0 or i%2 else 8, 0), pady=(0, 8))
            self.label(card, titulo, color='#a1a6b4', size=9)
            value = self.label(card, variable=var, color=cor, size=22, display=True)
            if i == 1:
                self.liquido_label = value
            self.label(card, 'Ver histórico  ↗' if i > 0 else nota, color='#a1a6b4', size=9)
            if i > 0:
                filtro = {1: 'Todos', 2: 'Ganhos', 3: 'Perdas', 4: 'Todos'}[i]
                for widget in [card, *card.winfo_children()]:
                    widget.configure(cursor='hand2')
                    widget.bind('<Button-1>', lambda event, f=filtro: self.abrir_resultados(f))
        ttk.Label(resumo_parent, textvariable=self.saldo_texto, style='Sub.TLabel', wraplength=360).pack(anchor='w', pady=(12, 22))
        ttk.Label(resumo_parent, textvariable=self.resumo_dia_texto, style='Sub.TLabel', wraplength=360).pack(anchor='w', pady=(0, 14))
        ttk.Label(resumo_parent, textvariable=self.nuvem_status, style='Sub.TLabel', wraplength=360).pack(anchor='w', pady=(0, 10))
        ttk.Button(resumo_parent, text='Histórico de transações do dia  ↗', command=self.abrir_resultados).pack(anchor='w', pady=(0, 14))
        ttk.Button(resumo_parent, text='Abrir atividade ao vivo  →', command=lambda: self.navigate('atividade')).pack(anchor='w', pady=(0, 18))
        connection = tk.Frame(login_parent, bg=self.bg)
        connection.pack(fill='x', pady=(0, 12))
        activity = self.pages['atividade']
        ttk.Label(activity, text='Sinais, entradas e resultados desta sessão aparecem aqui.', style='Sub.TLabel').pack(anchor='w', pady=(0, 12))
        heading = tk.Frame(activity, bg=self.bg)
        heading.pack(fill='x', pady=(0, 12))
        tk.Label(heading, text='Mercados acompanhados', bg=self.bg, fg='#e7e9ef', font=('Segoe UI Variable Text', 14, 'bold')).pack(side='left')
        self.mercados_texto = tk.StringVar()
        tk.Label(heading, textvariable=self.mercados_texto, bg=self.bg, fg=self.muted, font=('Segoe UI Variable Text', 10)).pack(side='right')
        mercados_area = ttk.Frame(activity)
        mercados_area.pack(fill='x', pady=(0, 16))
        self.ativos = ttk.Treeview(mercados_area, columns=('ativo', 'mercado', 'etapa'), show='headings', height=3)
        for col, title, width in [('ativo', 'Ativo', 145), ('mercado', 'Disponibilidade', 150), ('etapa', 'Etapa atual', 600)]:
            self.ativos.heading(col, text=title)
            self.ativos.column(col, width=width, minwidth=85, stretch=col == 'etapa')
        for ativo in PARES_DISPONIVEIS:
            self.ativos.insert('', 'end', iid=ativo, values=(ativo, 'Aguardando', 'Inicie a sessão para acompanhar'))
        self.ativos.pack(side='left', fill='x', expand=True)
        mercados_scroll = ttk.Scrollbar(mercados_area, command=self.ativos.yview)
        mercados_scroll.pack(side='right', fill='y')
        self.ativos.configure(yscrollcommand=mercados_scroll.set)
        ttk.Label(activity, textvariable=self.contagem, font=('Segoe UI Variable Text', 13, 'bold')).pack(anchor='w', pady=(0, 8))
        ttk.Label(activity, textvariable=self.resultado_texto, style='Sub.TLabel').pack(anchor='w', pady=(0, 18))
        area = ttk.Frame(activity)
        area.pack(fill='both', expand=True)
        self.historico = ttk.Treeview(area, columns=('hora', 'ativo', 'mensagem'), show='headings', height=5)
        for col, title, width in [('hora', 'Horário', 80), ('ativo', 'Ativo', 130), ('mensagem', 'O que aconteceu', 650)]:
            self.historico.heading(col, text=title)
            self.historico.column(col, width=width, stretch=col == 'mensagem')
        for tag, cor in [('ganho', '#65c78b'), ('perda', '#ef7c86'), ('aviso', '#e7b778'), ('sinal', '#f1b17d')]:
            self.historico.tag_configure(tag, foreground=cor)
        self.historico.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(area, command=self.historico.yview)
        scroll.pack(side='right', fill='y')
        self.historico.configure(yscrollcommand=scroll.set)
        ttk.Label(activity, text='Detalhes do evento ao vivo · selecione uma linha acima', style='Sub.TLabel').pack(anchor='w', pady=(18, 8))
        self.detalhe = tk.Text(activity, height=3, bg=self.surface, fg='#b4bac9', font=('Cascadia Code', 10), relief='flat', padx=14, pady=12, wrap='word', state='disabled')
        self.detalhe.pack(fill='x')
        self.historico.bind('<<TreeviewSelect>>', self.selecionar)
        # Login e estratégia ficam no Início, abaixo dos dados da conta.
        form = ttk.Frame(connection, padding=(0, 0, 24, 0))
        form.pack(side='left', fill='both', expand=True)
        form.configure(width=350)
        ttk.Label(form, text='Conectar conta DEMO', font=('Segoe UI Variable Display', 20)).pack(anchor='w', pady=(0, 8))
        ttk.Label(form, text='Escolha o modo antes de iniciar a sessão.', style='Sub.TLabel').pack(anchor='w', pady=(0, 20))
        self.opcoes_modo = []
        for texto, val in [('Só observar · sem enviar ordens', 'simulacao'), ('DEMO automática · saldo virtual', 'demo')]:
            radio = ttk.Radiobutton(form, text=texto, variable=self.modo, value=val)
            radio.pack(anchor='w', pady=3)
            self.opcoes_modo.append(radio)
        ttk.Label(form, text='E-mail da IQ Option', style='Sub.TLabel').pack(anchor='w', pady=(14, 6))
        self.email = ttk.Entry(form)
        self.email.pack(fill='x')
        ttk.Label(form, text='Senha', style='Sub.TLabel').pack(anchor='w', pady=(12, 6))
        self.senha = ttk.Entry(form, show='•')
        self.senha.pack(fill='x')
        self.iniciar = ttk.Button(form, text='Conectar e iniciar sessão  →', command=self.start, style='Start.TButton')
        self.iniciar.pack(fill='x', pady=(16, 8))
        self.parar = ttk.Button(form, text='Encerrar sessão', command=self.stop, style='Stop.TButton', state='disabled')
        self.parar.pack(fill='x')
        ttk.Label(form, text='A senha não é salva pelo painel.', style='Sub.TLabel').pack(anchor='w', pady=15)
        config = tk.Frame(main, bg=self.surface, padx=20, pady=20)
        config.pack(fill='x', pady=(16, 12))
        self.label(config, 'Estratégia configurada', size=15, display=True)
        self.campos_config = []
        parametros_linha = tk.Frame(config, bg=self.surface)
        parametros_linha.pack(fill='x')
        for indice, (title, variavel) in enumerate([('Recuo desde a abertura (pips)', self.config_pips), ('Valor por entrada (moeda da conta)', self.config_valor), ('Expiração (minutos)', self.config_expiracao)]):
            parametros_linha.columnconfigure(indice, weight=1, uniform='parametros')
            campo_base = tk.Frame(parametros_linha, bg=self.surface)
            campo_base.grid(row=0, column=indice, sticky='ew', padx=(0 if indice == 0 else 16, 0))
            self.label(campo_base, title, size=9, color='#9098ab', pady=(12, 3))
            campo = ttk.Combobox(campo_base, textvariable=variavel, values=('1', '2', '3', '4', '5'), state='readonly', width=20) if variavel is self.config_expiracao else ttk.Entry(campo_base, textvariable=variavel, width=22)
            campo.pack(fill='x')
            self.campos_config.append(campo)
        self.salvar_config = ttk.Button(config, text='Salvar parâmetros', command=self.salvar_parametros)
        self.salvar_config.pack(fill='x', pady=(14, 6))
        self.escolher_pares = ttk.Button(config, textvariable=self.pares_texto, command=self.abrir_pares)
        self.escolher_pares.pack(fill='x', pady=(0, 6))
        self.label(config, variable=self.config_status, size=9).configure(wraplength=340)
        self.label(config, variable=self.nuvem_status, size=9).configure(wraplength=340)
        for title, value in [('Janela e sinais', 'Velas M1 · entrada até o segundo 29'), ('Conta permitida', 'Somente demonstração / PRACTICE')]:
            self.label(config, title, size=9, color='#9098ab', pady=(18, 2))
            self.label(config, value, size=11)
        help_page = self.pages['ajuda']
        ttk.Label(help_page, text='Entenda o que o robô faz', font=('Segoe UI Variable Display', 22)).pack(anchor='w', pady=(0, 20))
        for title, text in [('Só observar', 'Acompanha os preços e registra sinais. Não envia ordens e não calcula resultados hipotéticos.'), ('DEMO automática', 'Abre operações sozinho usando saldo virtual. CALL é previsão de alta; PUT é previsão de queda.'), ('A regra da entrada', 'Após a bolinha fechada, observa a seta em tempo real e espera o recuo escolhido no Início, desde a abertura dessa mesma vela da seta. A seta pode desaparecer enquanto a vela está aberta; sua detecção fica registrada, mas um sinal contrário cancela a oportunidade. Na compra, abaixo; na venda, acima. Sinais continuam em velas de 1 minuto; a expiração pode ser de 1 a 5 minutos. Só envia até o segundo 29.'), ('Saldo e resultados', 'Saldo consultado a cada 3 segundos, mais o tempo de resposta da API, e após resultados. Ganhos e perdas somam todas as sessões do dia local. A taxa é ganhos divididos pelas operações concluídas, incluindo empates; pendentes ficam fora. Não há garantia de assertividade.'), ('Ao encerrar', 'Novas entradas param. Ordens já abertas continuam na corretora e devem ser conferidas na IQ Option.')]:
            ttk.Label(help_page, text=title, font=('Segoe UI Variable Text', 12, 'bold')).pack(anchor='w', pady=(12, 5))
            ttk.Label(help_page, text=text, style='Sub.TLabel', wraplength=850).pack(anchor='w')
        # Navegação fixa deixa as abas nomeadas sempre visíveis.
        self.sidebar = tk.Frame(root, bg='#202229', width=216)
        self.sidebar.place(x=0, y=0, width=216, relheight=1)
        self.nav_items = []
        self.logo = tk.Label(self.sidebar, text='IQ  Painel', bg='#202229', fg='#f58220', font=('Segoe UI Variable Display', 18, 'bold'), anchor='w')
        self.logo.place(x=22, y=24, width=190, height=48)
        for index, (icon, title, key) in enumerate([('⌂', 'Início', 'inicio'), ('≡', 'Atividade ao vivo', 'atividade'), ('?', 'Como funciona', 'ajuda')]):
            button = tk.Button(self.sidebar, text=f'{icon}   {title}', anchor='w', padx=14, bg='#202229', fg='#989dab', activebackground='#383b44', activeforeground='#f58220', bd=0, relief='flat', font=('Segoe UI Variable Text', 11), cursor='hand2', command=lambda k=key: self.navigate(k))
            button.place(x=10, y=110+index*64, width=196, height=48)
            self.nav_items.append((button, icon, title, key))
        self.nav_footer = tk.Label(self.sidebar, text='●  Ambiente demo', anchor='w', bg='#202229', fg='#767d8d', font=('Segoe UI Variable Text', 10))
        self.nav_footer.place(x=24, rely=1, y=-55, width=180, height=30)
        self.current_page = None
        self.atualizar_pares_selecionados()
        self.navigate('inicio')
        self.sidebar.lift()
        self.sincronizar_resumo_diario()
        root.after(150, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def label(self, parent, text='', variable=None, color='#e7e9ef', size=10, display=False, pady=(2, 4)):
        widget = tk.Label(parent, text=text, textvariable=variable, bg=self.surface, fg=color, font=('Segoe UI Variable Display' if display else 'Segoe UI Variable Text', size), anchor='w', justify='left')
        widget.pack(anchor='w', pady=pady)
        return widget

    def navigate(self, key):
        key = {'resumo': 'inicio', 'conexao': 'inicio'}.get(key, key)
        self.pages[key].tkraise()
        self.current_page = key
        self.page_title.set({'inicio': 'Início', 'atividade': 'Atividade ao vivo', 'ajuda': 'Como funciona'}[key])
        for button, icon, title, item_key in self.nav_items:
            button.configure(bg='#3d2e23' if key == item_key else '#202229', fg='#ffab66' if key == item_key else '#989dab')

    def parametros_digitados(self):
        return validar_configuracao({'pips': self.config_pips.get(), 'valor': self.config_valor.get(), 'expiracao': self.config_expiracao.get(),
                                    'pares': [par for par, variavel in self.pares_config.items() if variavel.get()]})

    def atualizar_pares_selecionados(self):
        selecionados = [par for par, variavel in self.pares_config.items() if variavel.get()]
        self.pares_texto.set(f'Escolher pares · {len(selecionados)} selecionados')
        self.mercados_texto.set(f'{len(selecionados)} pares selecionados / velas de 1 minuto')
        for par in self.ativos.get_children():
            self.ativos.item(par, values=(par, 'Aguardando' if par in selecionados else 'Não selecionado',
                                         'Conecte a sessão para acompanhar' if par in selecionados else 'Fora desta sessão · não envia ordens'))

    def abrir_pares(self):
        if self.processo and self.processo.poll() is None:
            messagebox.showinfo('Sessão em andamento', 'Encerre a sessão antes de trocar os pares.')
            return
        janela = tk.Frame(self.root, bg='#101217')
        janela.place(x=0, y=0, relwidth=1, relheight=1)
        janela.lift()
        caixa = ttk.Frame(janela, padding=28)
        caixa.place(relx=0.5, rely=0.5, anchor='center', width=640)
        cabecalho = ttk.Frame(caixa)
        cabecalho.pack(fill='x')
        ttk.Label(cabecalho, text='Pares da sessão', font=('Segoe UI', 20)).pack(side='left')
        escolhas = {par: tk.BooleanVar(value=var.get()) for par, var in self.pares_config.items()}
        def fechar():
            janela.grab_release()
            janela.destroy()
        ttk.Button(cabecalho, text='×', width=3, command=fechar).pack(side='right')
        ttk.Label(caixa, text='Selecione os pares que o bot poderá acompanhar e operar.\nCada um ainda precisa estar confirmado aberto na corretora.', style='Sub.TLabel').pack(anchor='w', pady=(10, 16))
        opcoes = ttk.Frame(caixa)
        opcoes.pack(fill='x')
        for i, (par, variavel) in enumerate(escolhas.items()):
            ttk.Checkbutton(opcoes, text=par, variable=variavel).grid(row=i%5, column=i//5, sticky='w', padx=(0, 80), pady=4)
        erro = tk.StringVar()
        ttk.Label(caixa, textvariable=erro, foreground='#ef7c86').pack(anchor='w', pady=(10, 4))
        def aplicar():
            if not any(v.get() for v in escolhas.values()):
                erro.set('Selecione pelo menos um par.')
                return
            anterior = {par: var.get() for par, var in self.pares_config.items()}
            for par, var in escolhas.items():
                self.pares_config[par].set(var.get())
            if self.salvar_parametros():
                fechar()
            else:
                for par, valor in anterior.items():
                    self.pares_config[par].set(valor)
                erro.set(self.config_status.get())
        ttk.Button(caixa, text='Aplicar e salvar pares', command=aplicar, style='Start.TButton').pack(fill='x', pady=(10, 0))
        janela.bind('<Escape>', lambda event: fechar())
        janela.grab_set()
        janela.focus_set()

    def salvar_parametros(self):
        if self.processo and self.processo.poll() is None:
            messagebox.showinfo('Sessão em andamento', 'Encerre a sessão antes de alterar os parâmetros.')
            return False
        try:
            salvar_configuracao(BASE, self.parametros_digitados())
        except (OSError, ValueError) as exc:
            self.config_status.set(str(exc))
            return False
        self.erro_configuracao = ''
        self.atualizar_pares_selecionados()
        self.config_status.set('Salvo · será aplicado ao iniciar a próxima sessão.')
        return True

    def bloquear_parametros(self, bloqueado):
        for campo in self.campos_config:
            campo.configure(state='disabled' if bloqueado else 'readonly' if isinstance(campo, ttk.Combobox) else 'normal')
        self.salvar_config.configure(state='disabled' if bloqueado else 'normal')
        self.escolher_pares.configure(state='disabled' if bloqueado else 'normal')

    def start(self):
        if not self.email.get().strip() or not self.senha.get():
            messagebox.showinfo('Login', 'Preencha o e-mail e a senha da IQ Option.')
            return
        if self.processo and self.processo.poll() is None:
            return
        if self.erro_configuracao:
            messagebox.showerror('Revise os parâmetros', self.erro_configuracao)
            return
        try:
            parametros = self.parametros_digitados()
        except ValueError as exc:
            messagebox.showerror('Parâmetros inválidos', str(exc))
            return
        modo = self.modo.get()
        if modo == 'demo' and not messagebox.askyesno('Confirmar operações DEMO', f"O bot abrirá operações de valor {parametros['valor']:.2f} na moeda da conta, com expiração de {parametros['expiracao']} minuto(s) e recuo de {parametros['pips']:g} pips.\n\nSomente PRACTICE (saldo virtual). Deseja iniciar na DEMO?"):
            return
        if not self.salvar_parametros():
            return
        if self.sincronizador_nuvem is not None:
            self.sincronizador_nuvem.parar.set()
        self.sincronizador_nuvem = None
        self.conta_historico = None
        self.erro_sessao = ''
        self.ids_resultados.clear()
        self.entradas_ativas.clear()
        self.ultima_entrada = None
        self.destaque_entrada.pack_forget()
        self.historico.delete(*self.historico.get_children())
        self.registros.clear()
        self.nuvem_status.set('Histórico na nuvem · confirmando a conta na corretora…')
        self.atualizar_resumo_diario()
        self.ultimo_saldo_recebido = None
        self.saldo_texto.set('Saldo demo: consultando…')
        self.saldo_valor.set('—')
        self.modo_sessao = modo
        self.ordens = 0
        try:
            self.processo = subprocess.Popen(comando_motor(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', cwd=BASE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0, env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8', 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
            self.processo.stdin.write(json.dumps({'email': self.email.get().strip(), 'senha': self.senha.get(), 'modo': self.modo_sessao, 'configuracao': parametros}) + '\n')
            self.processo.stdin.flush()
            self.processo.stdin.close()
            self.senha.delete(0, 'end')
            self.iniciar.configure(state='disabled')
            self.bloquear_parametros(True)
            self.parar.configure(state='normal')
            self.parar_inicio.configure(state='normal')
            for opcao in self.opcoes_modo:
                opcao.configure(state='disabled')
            self.total = 0
            self.contagem.set('Histórico desta sessão • 0 sinais simulados')
            self.evento(datetime.now().strftime('%H:%M:%S'), 'SESSÃO', 'Nova sessão DEMO automática' if modo == 'demo' else 'Nova sessão de observação sem ordens', 'Nova sessao; o resumo diario preserva os resultados de todas as sessoes do dia.')
            for ativo in parametros['pares']:
                self.ativos.item(ativo, values=(ativo, 'Aguardando', 'Conectando à corretora'))
            self.status.set('Conectando • Aguarde a confirmação da conta demo.')
            self.navigate('inicio')
            threading.Thread(target=self.reader, args=(self.processo,), daemon=True).start()
        except Exception as exc:
            self.stop()
            messagebox.showerror('Não foi possível iniciar', str(exc))

    def reader(self, processo):
        for linha in processo.stdout:
            self.fila.put(('saida', processo, linha.strip()))
        processo.wait()
        self.fila.put(('fim', processo))

    def ler_resultados_salvos(self, filtro='Todos', inicio=None, fim=None):
        if self.conta_historico is None:
            return []
        resultados = {}
        for linha in self.conta_historico.ler('resultado'):
                horario = datetime.strptime(linha['DATA_HORA'], '%d/%m/%Y %H:%M:%S')
                if (inicio is not None and horario < inicio) or (fim is not None and horario > fim):
                    continue
                if filtro == 'Ganhos' and linha.get('RESULTADO') != 'WIN':
                    continue
                if filtro == 'Perdas' and linha.get('RESULTADO') != 'LOSS':
                    continue
                resultados[linha['ID_ORDEM']] = linha
        return sorted(resultados.values(), key=lambda item: datetime.strptime(item['DATA_HORA'], '%d/%m/%Y %H:%M:%S'), reverse=True)

    def abrir_resultados(self, filtro='Todos'):
        janela = getattr(self, 'janela_resultados', None)
        if janela is not None and janela.winfo_exists():
            self.filtro_resultados.set(filtro)
            janela.lift()
            self.preencher_resultados()
            return
        self.foco_antes_modal = self.root.focus_get()
        janela = tk.Frame(self.root, bg='#101217')
        self.janela_resultados = janela
        janela.place(x=0, y=0, relwidth=1, relheight=1)
        janela.lift()
        moldura = tk.Frame(janela, bg=self.surface, highlightbackground='#414550', highlightthickness=1)
        moldura.place(relx=0.5, rely=0.5, anchor='center', relwidth=0.94, relheight=0.9)
        area = ttk.Frame(moldura, padding=22)
        area.pack(fill='both', expand=True, padx=1, pady=1)
        cabecalho = ttk.Frame(area)
        cabecalho.pack(fill='x')
        ttk.Button(cabecalho, text='×', width=3, command=self.fechar_resultados).pack(side='right')
        ttk.Label(cabecalho, text='Histórico de resultados', font=('Segoe UI Variable Display', 22)).pack(side='left')
        ttk.Label(area, text='Resultados confirmados · horário local · filtros por período', style='Sub.TLabel', wraplength=750).pack(anchor='w', pady=(4, 16))
        janela.bind('<Button-1>', lambda event: self.fechar_resultados() if event.widget is janela else None)
        self.escape_resultados = self.root.bind('<Escape>', lambda event: self.fechar_resultados(), add='+')
        janela.grab_set()
        janela.focus_set()
        self.filtro_resultados = tk.StringVar(value=filtro)
        barra = ttk.Frame(area)
        barra.pack(fill='x', pady=(0, 12))
        for nome in ('Todos', 'Ganhos', 'Perdas'):
            ttk.Radiobutton(barra, text=nome, variable=self.filtro_resultados, value=nome, command=self.preencher_resultados).pack(side='left')
        hoje = datetime.now().strftime('%d/%m/%Y')
        self.periodo_aplicado = limites_periodo(hoje, hoje)
        self.inicio_periodo = tk.StringVar(value=hoje)
        self.fim_periodo = tk.StringVar(value=hoje)
        self.erro_periodo = tk.StringVar()
        datas = ttk.Frame(area)
        datas.pack(fill='x', pady=(0, 8))
        for col, titulo, variavel in [(0, 'De', self.inicio_periodo), (1, 'Até', self.fim_periodo)]:
            ttk.Label(datas, text=titulo, style='Sub.TLabel').grid(row=0, column=col, sticky='w', pady=(0, 5))
            entry = ttk.Entry(datas, textvariable=variavel, width=23)
            entry.grid(row=1, column=col, sticky='ew', padx=(0, 10))
            entry.bind('<Return>', lambda event: self.aplicar_periodo())
        ttk.Button(datas, text='Aplicar período', command=self.aplicar_periodo).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(datas, text='Hoje', command=lambda: self.atalho_periodo(True)).grid(row=1, column=3, padx=(0, 8))
        ttk.Button(datas, text='Todo o histórico', command=lambda: self.atalho_periodo(False)).grid(row=1, column=4)
        ttk.Label(area, text='DD/MM/AAAA · horário opcional HH:MM · sem horário, inclui o dia inteiro.', style='Sub.TLabel').pack(anchor='w')
        ttk.Label(area, textvariable=self.erro_periodo, foreground='#ef7c86').pack(anchor='w', pady=(2, 8))
        self.periodo_texto = tk.StringVar(value=f'Período: {hoje} · todas as sessões deste dia')
        ttk.Label(area, textvariable=self.periodo_texto, style='Sub.TLabel').pack(anchor='w', pady=(0, 10))
        totais = tk.Frame(area, bg=self.bg)
        totais.pack(fill='x', pady=(0, 12))
        self.totais_historico = {}
        self.cartoes_historico = {}
        for chave, titulo, cor in [('valor_ganhos', 'Total de ganhos', '#65c78b'),
                                   ('valor_perdas', 'Total de perdas', '#ef7c86'),
                                   ('liquido', 'Líquido do período', '#e9eaef')]:
            cartao = tk.Frame(totais, bg='#292c35', padx=16, pady=10)
            tk.Label(cartao, text=titulo, bg='#292c35', fg=self.muted,
                     font=('Segoe UI', 10)).pack(anchor='w')
            valor = tk.StringVar(value='0,00')
            tk.Label(cartao, textvariable=valor, bg='#292c35', fg=cor,
                     font=('Segoe UI', 22)).pack(anchor='w', pady=(3, 0))
            self.totais_historico[chave] = valor
            self.cartoes_historico[chave] = cartao
        tabela = ttk.Frame(area)
        tabela.pack(fill='both', expand=True)
        self.lista_resultados = ttk.Treeview(tabela, columns=('hora', 'ativo', 'direcao', 'resultado', 'lucro'), show='headings', height=4)
        for col, titulo, largura in [('hora', 'Data e horário', 180), ('ativo', 'Ativo', 145), ('direcao', 'Direção', 85), ('resultado', 'Resultado', 100), ('lucro', 'Valor líquido', 110)]:
            self.lista_resultados.heading(col, text=titulo)
            self.lista_resultados.column(col, width=largura, minwidth=75)
        self.lista_resultados.tag_configure('WIN', foreground='#65c78b')
        self.lista_resultados.tag_configure('LOSS', foreground='#ef7c86')
        self.lista_resultados.pack( side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(tabela, command=self.lista_resultados.yview)
        scroll.pack(side='right', fill='y')
        self.lista_resultados.configure(yscrollcommand=scroll.set)
        self.resumo_lista = tk.StringVar()
        ttk.Label(area, textvariable=self.resumo_lista, style='Sub.TLabel', wraplength=880).pack(anchor='w', pady=(12, 0))
        self.assinatura_lista = None
        self.preencher_resultados()
        self.atualizar_lista_resultados()

    def aplicar_periodo(self):
        try:
            limites = limites_periodo(self.inicio_periodo.get(), self.fim_periodo.get())
        except ValueError as exc:
            self.erro_periodo.set(str(exc) + ' A lista mantém o último período aplicado.')
            return
        self.erro_periodo.set('')
        self.periodo_aplicado = limites
        a, b = limites
        self.periodo_texto.set('Período aplicado: ' + (a.strftime('%d/%m/%Y %H:%M:%S') if a else 'desde o primeiro registro') + ' até ' + (b.strftime('%d/%m/%Y %H:%M:%S') if b else 'o último registro'))
        self.preencher_resultados()

    def atalho_periodo(self, hoje):
        data = datetime.now().strftime('%d/%m/%Y') if hoje else ''
        self.inicio_periodo.set(data)
        self.fim_periodo.set(data)
        self.aplicar_periodo()

    def preencher_resultados(self):
        try:
            linhas = self.ler_resultados_salvos(self.filtro_resultados.get(), *self.periodo_aplicado)
            assinatura = repr(linhas)
            if assinatura != self.assinatura_lista:
                self.assinatura_lista = assinatura
                self.lista_resultados.delete(*self.lista_resultados.get_children())
                for item in linhas:
                    valor = float(item['LUCRO_LIQUIDO'])
                    self.lista_resultados.insert('', 'end', values=(item['DATA_HORA'], item['ATIVO'], item['DIRECAO'], {'WIN': 'Ganho', 'LOSS': 'Perda', 'EMPATE': 'Empate'}.get(item['RESULTADO'], item['RESULTADO']), f'{valor:+.2f}'.replace('.', ',')), tags=(item['RESULTADO'],))
            total = sum(float(item['LUCRO_LIQUIDO']) for item in linhas)
            ganhos = sum(item['RESULTADO'] == 'WIN' for item in linhas)
            perdas = sum(item['RESULTADO'] == 'LOSS' for item in linhas)
            empates = sum(item['RESULTADO'] == 'EMPATE' for item in linhas)
            periodo = resumo_resultados(self.ler_resultados_salvos('Todos', *self.periodo_aplicado))
            filtro = self.filtro_resultados.get()
            for chave, cartao in self.cartoes_historico.items():
                valor = periodo[chave]
                texto = f'{valor:+,.2f}' if valor else '0.00'
                self.totais_historico[chave].set(texto.translate(str.maketrans({',': '.', '.': ','})))
                cartao.pack_forget()
            visiveis = ('valor_ganhos',) if filtro == 'Ganhos' else ('valor_perdas',) if filtro == 'Perdas' else ('valor_ganhos', 'valor_perdas', 'liquido')
            for chave in visiveis:
                self.cartoes_historico[chave].pack(side='left', fill='x', expand=True, padx=4)
            taxa = f"{periodo['taxa']:.1f}%".replace('.', ',') if periodo['taxa'] is not None else '—'
            self.resumo_lista.set(f"Período completo: {periodo['total']} concluídas · {periodo['ganhos']} ganhos · {periodo['perdas']} perdas · {periodo['empates']} empates · Acerto: {taxa} · Líquido: {periodo['liquido']:+.2f}".replace('.', ',') + f"\nLista filtrada: {len(linhas)} operações · Total: {total:+.2f}".replace('.', ','))
        except (OSError, csv.Error, KeyError, ValueError):
            for valor in self.totais_historico.values():
                valor.set('—')
            self.resumo_lista.set('Não foi possível ler os resultados salvos. Tente novamente.')

    def atualizar_lista_resultados(self):
        janela = getattr(self, 'janela_resultados', None)
        if janela is not None and janela.winfo_exists():
            self.preencher_resultados()
            self.timer_resultados = self.root.after(3000, self.atualizar_lista_resultados)

    def fechar_resultados(self):
        timer = getattr(self, 'timer_resultados', None)
        if timer is not None:
            self.root.after_cancel(timer)
            self.timer_resultados = None
        escape = getattr(self, 'escape_resultados', None)
        if escape is not None:
            self.root.unbind('<Escape>', escape)
            self.escape_resultados = None
        janela = getattr(self, 'janela_resultados', None)
        if janela is not None and janela.winfo_exists():
            janela.grab_release()
            janela.destroy()
        self.janela_resultados = None
        foco = getattr(self, 'foco_antes_modal', None)
        if foco is not None and foco.winfo_exists():
            foco.focus_set()

    def evento(self, hora, ativo, texto, original):
        tag = 'ganho' if 'RESULTADO_WIN' in original else 'perda' if 'RESULTADO_LOSS' in original else 'aviso' if any(x in original for x in ['ERRO', 'BLOQUEADO', 'NAO_CONFIRMADO', 'RECUSADA']) else 'sinal' if any(x in original for x in ['DEMO_ENVIADA', 'SINAL_SIMULADO', 'SETA_CONFIRMADA', 'SETA_DETECTADA']) else ''
        item = self.historico.insert('', 'end', values=(hora, ativo, texto), tags=(tag,))
        self.registros[item] = original
        self.historico.see(item)
        if len(self.registros) > 500:
            antigo = self.historico.get_children()[0]
            self.historico.delete(antigo)
            self.registros.pop(antigo, None)

    def poll(self):
        try:
            while True:
                linha = self.fila.get_nowait()
                if isinstance(linha, tuple) and linha[0] == 'saida':
                    if linha[1] is not self.processo:
                        continue
                    linha = linha[2]
                if isinstance(linha, tuple) and linha[0] == 'nuvem':
                    if linha[1] is self.sincronizador_nuvem:
                        self.nuvem_status.set(linha[2])
                        self.atualizar_resumo_diario()
                        janela = getattr(self, 'janela_resultados', None)
                        if janela is not None and janela.winfo_exists():
                            self.preencher_resultados()
                    continue
                if isinstance(linha, str) and linha.startswith('__PAINEL__'):
                    self.atualizar_financeiro(json.loads(linha[len('__PAINEL__'):]))
                    continue
                if isinstance(linha, tuple):
                    if linha[1] is self.processo:
                        self.bloquear_parametros(False)
                        self.iniciar.configure(state='normal')
                        self.parar.configure(state='disabled')
                        self.parar_inicio.configure(state='disabled')
                        for opcao in self.opcoes_modo:
                            opcao.configure(state='normal')
                        for ativo in self.ativos.get_children():
                            valores = self.ativos.item(ativo, 'values')
                            self.ativos.item(ativo, values=(ativo, valores[1], 'Bot parado — não acompanha novos sinais'))
                        self.status.set(self.erro_sessao or 'Parado • A sessão terminou. Veja o histórico para identificar o motivo.')
                        if self.conta_historico is None:
                            self.nuvem_status.set('Histórico na nuvem · aguardando conexão com a corretora.')
                        self.processo = None
                        self.ultimo_saldo_recebido = None
                        self.saldo_valor.set('—')
                        self.saldo_texto.set('Sessão encerrada · conecte para consultar o saldo atual.')
                    continue
                if 'Conta confirmada: PRACTICE' in linha:
                    self.navigate('atividade')
                    self.status.set('Conectado • DEMO AUTOMÁTICA ATIVA: operações com saldo virtual.' if self.modo_sessao == 'demo' else 'Conectado à conta demo • Simulação ativa, sem envio de ordens.')
                    self.evento('', 'SISTEMA', 'Conexão confirmada na conta de demonstração.', linha)
                elif linha.startswith('[') and ' | ' in linha:
                    partes = linha.split(' | ', 2)
                    cabecalho = partes[0].split('] ', 1)
                    if len(cabecalho) != 2:
                        continue
                    hora, ativo = cabecalho[0][1:], cabecalho[1]
                    evento, detalhe = partes[1], partes[2] if len(partes) > 2 else ''
                    texto = EXPLICACOES.get(evento, evento.replace('_', ' ').capitalize())
                    if evento == 'DISPONIBILIDADE':
                        texto = {'ABERTO': 'Ativo aberto. Aguardando novos sinais.', 'FECHADO': 'Ativo fechado. Não será acompanhado.', 'NAO_CONFIRMADA': 'Abertura não confirmada. Ativo bloqueado.'}.get(detalhe, detalhe)
                        if self.ativos.exists(ativo):
                            mercado = {'ABERTO': 'Aberto', 'FECHADO': 'Fechado', 'NAO_CONFIRMADA': 'Não confirmada'}.get(detalhe, detalhe)
                            anterior = self.ativos.item(ativo, 'values')
                            etapa = anterior[2] if detalhe == 'ABERTO' and anterior[1] == 'Aberto' else texto
                            self.ativos.item(ativo, values=(ativo, mercado, etapa))
                    elif self.ativos.exists(ativo):
                        valores = self.ativos.item(ativo, 'values')
                        self.ativos.item(ativo, values=(ativo, valores[1], texto))
                    if evento == 'DEMO_ENVIADA':
                        self.destacar_entrada(hora, ativo, detalhe)
                        self.notificar_entrada()
                        self.ordens += 1
                        self.contagem.set(f'Histórico desta sessão • {self.ordens} ordens DEMO enviadas')
                    if evento.startswith('RESULTADO_') or evento == 'DEMO_ENVIADA':
                        texto += ' | ' + detalhe
                    if evento.startswith('RESULTADO_'):
                        self.resultado_entrada(evento, detalhe)
                    if evento == 'SINAL_SIMULADO':
                        self.total += 1
                        self.contagem.set(f'Histórico desta sessão • {self.total} sinais simulados')
                    if evento in ('RECONEXAO_NECESSARIA', 'TENTATIVA_RECONEXAO', 'RECONECTADO', 'ENCERRADO_SEGURO'):
                        self.status.set(texto)
                    self.evento(hora, ativo, texto, linha)
                elif 'Falha na conexao' in linha or 'Traceback' in linha or 'Error' in linha or 'indisponivel' in linha:
                    if 'Falha na conexao inicial' in linha:
                        self.erro_sessao = 'Não foi possível conectar à IQ Option · confira o motivo em Atividade.'
                    self.evento('', 'SISTEMA', linha, linha)
        except queue.Empty:
            pass
        self.root.after(150, self.poll)

    def notificar_entrada(self):
        if self.som_ativo.get():
            try:
                if winsound is not None:
                    winsound.PlaySound('SystemAsterisk', winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                elif sys.platform == 'darwin' and Path('/System/Library/Sounds/Glass.aiff').exists():
                    subprocess.Popen(['/usr/bin/afplay', '/System/Library/Sounds/Glass.aiff'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self.root.bell()
            except (RuntimeError, OSError, tk.TclError):
                pass

    def destacar_entrada(self, hora, ativo, detalhe):
        partes = detalhe.split()
        campos = dict(p.split('=', 1) for p in partes if '=' in p)
        direcao = partes[0] if partes else ''
        if direcao not in ('CALL', 'PUT') or not campos.get('id'):
            return
        entrada = {'hora': hora, 'ativo': ativo, 'direcao': direcao,
                   'valor': campos.get('valor', '—').replace('.', ','),
                   'expiracao': campos.get('expiracao', '—'), 'id': campos['id'],
                   'estado': 'ENTRADA DEMO ENVIADA · acompanhe este par na IQ Option'}
        self.entradas_ativas[entrada['id']] = entrada
        self.ultima_entrada = entrada
        self.mostrar_entrada(entrada)

    def mostrar_entrada(self, entrada):
        self.entrada_estado.set(entrada['estado'])
        lado = 'CALL ↑ · ALTA' if entrada['direcao'] == 'CALL' else 'PUT ↓ · BAIXA'
        self.entrada_par.set(f"{entrada['ativo']}   {lado}")
        self.label_par_entrada.configure(fg='#65c78b' if entrada['direcao'] == 'CALL' else '#ff929c')
        self.entrada_info.set(f"Entrada às {entrada['hora']} · Valor {entrada['valor']} · Expiração {entrada['expiracao']} min · ID {entrada['id']}")
        abertas = ' · '.join(f"{e['ativo']} ({e['direcao']})" for e in self.entradas_ativas.values())
        self.entrada_abertas.set('Aguardando resultado: ' + abertas if abertas else 'Veja o mesmo par na IQ Option · gráfico M1 · conta DEMO')
        self.destaque_entrada.pack(fill='x')

    def resultado_entrada(self, evento, detalhe):
        campos = dict(p.split('=', 1) for p in detalhe.split() if '=' in p)
        identificador = campos.get('id')
        entrada = self.entradas_ativas.get(identificador)
        if entrada is None:
            return
        if evento == 'RESULTADO_NAO_CONFIRMADO':
            entrada['estado'] = 'RESULTADO NÃO CONFIRMADO · confira a operação na IQ Option'
        elif evento in ('RESULTADO_WIN', 'RESULTADO_LOSS', 'RESULTADO_EMPATE'):
            resultado = evento.removeprefix('RESULTADO_')
            entrada['estado'] = f"ÚLTIMA ENTRADA CONCLUÍDA · {resultado} · líquido {campos.get('lucro_liquido', '—').replace('.', ',')}"
            self.entradas_ativas.pop(identificador)
        if self.entradas_ativas:
            self.mostrar_entrada(list(self.entradas_ativas.values())[-1])
        elif self.ultima_entrada is not None:
            self.mostrar_entrada(self.ultima_entrada)

    def atualizar_financeiro(self, dados):
        tipo = dados.get('tipo')
        if tipo == 'conta_historico':
            conta = str(dados['conta'])
            # Uma reconexão renova a sessão temporária da nuvem.
            if self.sincronizador_nuvem is not None:
                self.sincronizador_nuvem.parar.set()
            self.conta_historico = Historico(BASE, conta)
            sincronizador = Sincronizador(self.conta_historico, dados['ssid'],
                lambda texto: self.fila.put(('nuvem', sincronizador, texto)))
            self.sincronizador_nuvem = sincronizador
            self.nuvem_status.set('Buscando histórico desta conta no Supabase…')
            self.atualizar_resumo_diario()
            threading.Thread(target=sincronizador.executar, daemon=True).start()
        elif tipo == 'historico_erro':
            self.nuvem_status.set('Histórico bloqueado: a identidade da conta não foi confirmada.')
        elif tipo == 'saldo':
            valor = f"{dados['valor']:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')
            consultado = float(dados.get('consultado_em', time.time()))
            if time.time() - consultado > 10:
                self.saldo_valor.set('—')
                self.saldo_texto.set('Resposta de saldo atrasada · aguardando consulta atual.')
                return
            self.ultimo_saldo_recebido = time.monotonic()
            self.saldo_valor.set(valor)
            hora = datetime.fromtimestamp(consultado).strftime('%H:%M:%S')
            self.saldo_texto.set(f"DEMO · {dados.get('moeda', 'moeda não informada')} · conta {dados.get('conta', 'não informada')} · consultado às {hora} · atualização a cada 3s + API")
        elif tipo == 'saldo_erro':
            self.saldo_valor.set('—')
            self.ultimo_saldo_recebido = None
            self.saldo_texto.set('Consulta de saldo falhou (' + dados.get('motivo', 'sem resposta') + ') · confira a conta demo no site.')
        elif tipo == 'resultado' and dados['id'] not in self.ids_resultados:
            self.ids_resultados.add(dados['id'])
            self.atualizar_resumo_diario()

    def atualizar_resumo_diario(self):
        hoje = datetime.now().strftime('%d/%m/%Y')
        try:
            resumo = resumo_resultados(self.ler_resultados_salvos('Todos', *limites_periodo(hoje, hoje)))
            self.ganhos, self.perdas, self.empates = resumo['ganhos'], resumo['perdas'], resumo['empates']
            self.liquido = resumo['liquido']
            self.ganhos_valor.set(str(self.ganhos))
            self.perdas_valor.set(str(self.perdas))
            self.liquido_valor.set(f'{self.liquido:+.2f}'.replace('.', ','))
            self.taxa_valor.set(f"{resumo['taxa']:.1f}%".replace('.', ',') if resumo['taxa'] is not None else '—')
            self.liquido_label.configure(fg='#65c78b' if self.liquido > 0 else '#ef7c86' if self.liquido < 0 else '#e9eaef')
            texto = f"{hoje} · {resumo['total']} operações concluídas · {self.empates} empates · todas as sessões do dia"
            self.resumo_dia_texto.set(texto)
            self.resultado_texto.set(texto)
        except (OSError, csv.Error, KeyError, ValueError):
            self.resumo_dia_texto.set('Não foi possível atualizar o resumo diário. Confira o histórico salvo.')

    def sincronizar_resumo_diario(self):
        self.atualizar_resumo_diario()
        if self.ultimo_saldo_recebido is not None and time.monotonic() - self.ultimo_saldo_recebido > 10:
            self.saldo_valor.set('—')
            self.saldo_texto.set('Saldo sem atualização há mais de 10s · aguardando resposta da corretora.')
        self.root.after(3000, self.sincronizar_resumo_diario)

    def selecionar(self, event=None):
        selecao = self.historico.selection()
        if selecao:
            self.detalhe.configure(state='normal')
            self.detalhe.delete('1.0', 'end')
            self.detalhe.insert('1.0', self.registros.get(selecao[0], ''))
            self.detalhe.configure(state='disabled')

    def stop(self):
        if self.processo and self.processo.poll() is None:
            self.processo.terminate()
        self.status.set('Parando o bot… Ordens DEMO já abertas continuam na corretora.')

    def close(self):
        self.stop()
        if self.sincronizador_nuvem is not None:
            self.sincronizador_nuvem.parar.set()
        self.root.destroy()

if __name__ == '__main__':
    Painel(tk.Tk()).root.mainloop()
