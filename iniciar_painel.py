"""Entrada do aplicativo Windows e verificação offline do pacote."""
import json
import subprocess
import sys
import os
from pathlib import Path


def autoteste(destino):
    import tkinter as tk
    from caminhos import comando_motor, pasta_dados, pasta_recursos
    import painel
    import ssl
    import certifi
    contexto = ssl.create_default_context(cafile=certifi.where())
    root = tk.Tk()
    root.withdraw()
    timers = []
    try:
        app = painel.Painel(root)
        root.update_idletasks()
        assert app.conta_historico is None
        assert app.ler_resultados_salvos() == []
        assert app.modo.get() == 'simulacao'
        selecionados = ['EURUSD', 'GBPJPY-OTC']
        for par, variavel in app.pares_config.items():
            variavel.set(par in selecionados)
        assert set(app.parametros_digitados()['pares']) == set(selecionados)
        app.config_expiracao.set('30 segundos')
        assert app.parametros_digitados()['expiracao'] == 0.5
        app.som_ativo.set(False)
        app.fila.put('[12:00:00] EURUSD-OTC | DEMO_ENVIADA | CALL valor=20.00 expiracao=0.5 id=autoteste')
        app.poll()
        assert 'EURUSD-OTC' in app.entrada_par.get()
        assert 'CALL' in app.entrada_par.get()
        assert '30 segundos' in app.entrada_info.get()
        app.fila.put('[12:01:00] EURUSD-OTC | RESULTADO_WIN | id=autoteste lucro_liquido=17.40')
        app.poll()
        assert 'CONCLUÍDA' in app.entrada_estado.get()
        retorno = subprocess.run(comando_motor() + ['--autoteste'], capture_output=True,
            text=True, encoding='utf-8', timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
        if retorno.returncode:
            raise RuntimeError('Motor interno falhou: ' + retorno.stderr[-2000:])
        motor = json.loads(retorno.stdout.strip())
        assert motor['ok']
        relatorio = {'ok': True, 'executavel_independente': bool(getattr(sys, 'frozen', False)),
            'tkinter': str(tk.TkVersion), 'motor': motor,
            'tls_inicializado': contexto.verify_mode == ssl.CERT_REQUIRED,
            'titulo': root.title(), 'destaque_de_entrada_testado': True,
            'pares_disponiveis': len(app.pares_config), 'selecao_de_pares_testada': True,
            'expiracao_30s_testada': True,
            'dados_fora_do_executavel': pasta_dados() != pasta_recursos(),
            'painel_sem_login': True, 'nenhuma_ordem_enviada': True}
        Path(destino).write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        for timer in root.tk.call('after', 'info'):
            root.after_cancel(timer)
        root.destroy()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--diagnostico-conexao':
        from caminhos import comando_motor, pasta_dados
        retorno = subprocess.run(comando_motor() + ['--diagnostico-conexao'], capture_output=True,
            text=True, encoding='utf-8', timeout=40, cwd=pasta_dados(),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYINSTALLER_RESET_ENVIRONMENT': '1'})
        Path(sys.argv[2]).write_text(retorno.stdout or json.dumps({'ok': False, 'codigo': retorno.returncode}), encoding='utf-8')
    elif len(sys.argv) == 3 and sys.argv[1] == '--autoteste':
        try:
            autoteste(sys.argv[2])
        except Exception as erro:
            Path(sys.argv[2]).write_text(json.dumps({'ok': False, 'erro': repr(erro)}), encoding='utf-8')
            raise
    else:
        import tkinter as tk
        from painel import Painel
        Painel(tk.Tk()).root.mainloop()
