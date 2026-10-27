"""Encerra também o processo filho criado pelo executável onefile."""
import os
import signal
import subprocess
from pathlib import Path


def encerrar_motor(processo):
    if processo.poll() is not None:
        return
    if os.name == 'nt':
        sistema = Path(os.environ.get('SystemRoot', os.environ.get('SYSTEMROOT', r'C:\Windows')))
        resultado = subprocess.run([str(sistema/'System32'/'taskkill.exe'), '/PID', str(processo.pid), '/T', '/F'],
            capture_output=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if resultado.returncode != 0 and processo.poll() is None:
            raise RuntimeError('O Windows não confirmou o encerramento da árvore do motor.')
    else:
        # O motor é iniciado em uma sessão própria; não encerra o grupo do painel.
        os.killpg(processo.pid, signal.SIGTERM)
    try:
        processo.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(processo.pid, signal.SIGKILL)
            processo.wait(timeout=3)
        else:
            raise RuntimeError('O motor não confirmou o encerramento dentro do prazo.') from None


def processo_ativo(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            codigo = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(codigo)):
                raise OSError('Não foi possível consultar o estado do processo.')
            return codigo.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
