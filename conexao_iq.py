"""Compatibilidade e diagnóstico de transporte sem expor credenciais."""
import json


def motivo_seguro(motivo):
    texto = str(motivo)
    if '11001' in texto or 'getaddrinfo' in texto:
        return 'Falha de DNS: nao foi possivel localizar o servidor da IQ Option.'
    if '10060' in texto or 'timed out' in texto.lower():
        return 'A conexao com a IQ Option excedeu o tempo limite.'
    if '10061' in texto or 'refused' in texto.lower():
        return 'A conexao com a IQ Option foi recusada.'
    if '403' in texto or 'Forbidden' in texto:
        return 'O servidor da IQ Option recusou a conexao (HTTP 403).'
    if 'certificate' in texto.lower() or 'SSL' in texto:
        return 'Falha na verificacao do certificado da conexao com a IQ Option.'
    if 'Websocket connection closed' in texto:
        return 'A IQ Option encerrou a conexao antes de confirmar o login.'
    return 'A IQ Option retornou uma resposta de conexao inesperada. Tente novamente em instantes.'


def instalar_compatibilidade(stable_api):
    import certifi
    import ssl
    import threading
    import time
    from iqoptionapi.api import WebsocketClient
    from iqoptionapi import global_value
    original = stable_api.IQOptionAPI

    class APICompativel(original):
        def start_websocket(self):
            global_value.check_websocket_if_connect = None
            global_value.check_websocket_if_error = False
            global_value.websocket_error_reason = None
            self.websocket_client = WebsocketClient(self)
            from catalogo import instalar_consulta
            instalar_consulta(self)
            # A biblioteca usa 'cacert.pem' relativo; no EXE os certificados
            # ficam dentro do pacote. Usar caminho absoluto e verificar TLS.
            self.websocket_thread = threading.Thread(target=self.websocket.run_forever,
                kwargs={'sslopt': {'check_hostname': True, 'cert_reqs': ssl.CERT_REQUIRED,
                                  'ca_certs': certifi.where()}}, daemon=True)
            self.websocket_thread.start()
            limite = time.monotonic() + 20
            while time.monotonic() < limite:
                if global_value.check_websocket_if_error:
                    return False, global_value.websocket_error_reason
                if global_value.check_websocket_if_connect == 0:
                    return False, 'Websocket connection closed.'
                if global_value.check_websocket_if_connect == 1:
                    return True, None
                time.sleep(0.05)
            self.close()
            return False, 'Connection timed out'

        def connect(self):
            ok, motivo = super().connect()
            if not ok:
                try:
                    valido = json.loads(motivo)
                    if not isinstance(valido, dict):
                        raise ValueError()
                except (ValueError, TypeError):
                    motivo = json.dumps({'code': 'connection_error', 'message': motivo_seguro(motivo)})
            return ok, motivo

    stable_api.IQOptionAPI = APICompativel


def diagnosticar_transporte():
    import threading
    import traceback
    from iqoptionapi.api import WebsocketClient
    from iqoptionapi import stable_api
    instalar_compatibilidade(stable_api)
    api = stable_api.IQOptionAPI('iqoption.com', '', '')
    saida = {}
    on_error_original = WebsocketClient.on_error
    def capturar_erro(*args):
        erro = args[-1]
        saida['pilha'] = [{'arquivo': Path(f.filename).name, 'linha': f.lineno, 'funcao': f.name}
                          for f in traceback.extract_tb(getattr(erro, '__traceback__', None))]
        return on_error_original(*args)
    from pathlib import Path
    WebsocketClient.on_error = staticmethod(capturar_erro)
    def verificar():
        try:
            ok, motivo = api.start_websocket()
            saida.update(ok=bool(ok), motivo=None if ok else motivo_seguro(motivo),
                         erro_tipo=None if ok else type(motivo).__name__,
                         detalhe=None if ok else str(motivo).splitlines()[0][:160])
        except Exception as erro:
            saida.update(ok=False, motivo=motivo_seguro(erro), erro_tipo=type(erro).__name__)
    thread = threading.Thread(target=verificar, daemon=True)
    thread.start()
    thread.join(20)
    try:
        api.close()
    except Exception:
        pass
    if thread.is_alive():
        saida.update(ok=False, motivo='Tempo limite ao abrir o canal da IQ Option.')
    saida['sem_login_e_sem_ordens'] = True
    return saida
