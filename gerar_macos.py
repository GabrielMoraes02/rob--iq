"""Gera e testa o aplicativo no macOS; nao acessa a corretora."""
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from caminhos import VERSAO


def gerar():
    if sys.platform != 'darwin':
        raise SystemExit('Execute este gerador em um Mac.')
    base = Path(__file__).resolve().parent
    os.chdir(base)
    comum = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--noupx', '--specpath', 'build-spec-macos']
    subprocess.run(comum + ['--onefile', '--console', '--name', 'MotorMarcos', '--distpath', 'dist-motor-macos', '--workpath', 'build-motor-macos', '--collect-all', 'iqoptionapi', '--add-data', f'{base / "MARCOS_2027_V19_5_OTC_AUDITORIA_SEGURA.py"}:.', 'motor_visual.py'], check=True)
    subprocess.run(comum + ['--onedir', '--windowed', '--name', 'BotMarcos', '--osx-bundle-identifier', 'com.botmarcos.desktop', '--distpath', 'dist-macos', '--workpath', 'build-painel-macos', '--add-binary', f'{base / "dist-motor-macos/MotorMarcos"}:.', 'iniciar_painel.py'], check=True)
    app = base / 'dist-macos/BotMarcos.app'
    report = base / 'dist-macos/autoteste.json'
    with tempfile.TemporaryDirectory(prefix='botmarcos-teste-') as home:
        subprocess.run([str(app / 'Contents/MacOS/BotMarcos'), '--autoteste', str(report)], env={**os.environ, 'HOME': home, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}, check=True, timeout=180)
    resultado = json.loads(report.read_text(encoding='utf-8'))
    if not resultado.get('ok') or not resultado.get('executavel_independente'):
        raise RuntimeError('O autoteste do aplicativo falhou; pacote nao liberado.')
    destino = base / 'dist-macos' / f'BOT_MARCOS_MACOS_{VERSAO}_{platform.machine()}.zip'
    subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(destino)], check=True)
    print(destino)


if __name__ == '__main__':
    gerar()
