"""Gera o motor, o aplicativo e o ZIP para clientes. Rodar no Windows."""
import os
import ssl
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from caminhos import VERSAO


def gerar():
    if sys.platform != 'win32':
        raise SystemExit('A versao Windows precisa ser gerada no Windows.')
    base = Path(__file__).resolve().parent
    os.chdir(base)
    extras = []
    certificados_runtime = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
    if certificados_runtime.exists():
        extras = ['--add-data', f'{certificados_runtime}:.']
    comum = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--noupx', '--specpath', 'build-spec']
    subprocess.run(comum + ['--console', '--name', 'MotorMarcos', '--distpath', 'dist-motor',
        '--workpath', 'build-motor', '--collect-all', 'iqoptionapi', '--add-data',
        f'{base / "MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py"}:.'] + extras + ['motor_visual.py'], check=True)
    subprocess.run(comum + ['--windowed', '--name', 'BotMarcos', '--distpath', 'dist-windows',
        '--workpath', 'build-painel', '--add-binary', f'{base / "dist-motor" / "MotorMarcos.exe"}:.']
        + extras + ['iniciar_painel.py'], check=True)
    destino = base / 'dist-windows' / f'BOT_MARCOS_WINDOWS_{VERSAO}.zip'
    with ZipFile(destino, 'w', compression=ZIP_DEFLATED) as pacote:
        pacote.write(base / 'dist-windows' / 'BotMarcos.exe', 'BotMarcos.exe')
        pacote.write(base / 'LEIA_ME_WINDOWS_EXE.txt', 'LEIA-ME.txt')
    print(f'Executavel: {base / "dist-windows" / "BotMarcos.exe"}')
    print(f'Pacote do cliente: {destino}')


if __name__ == '__main__':
    gerar()
