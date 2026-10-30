"""Separa recursos do executável dos dados gravados por cada cliente."""
import os
import sys
from pathlib import Path

VERSAO = '1.0.23'


def pasta_recursos():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def pasta_dados():
    if getattr(sys, 'frozen', False):
        if sys.platform == 'darwin':
            pasta = Path.home() / 'Library' / 'Application Support' / 'BotMarcos'
        else:
            pasta = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'BotMarcos'
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta
    return Path(__file__).resolve().parent


def comando_motor():
    if getattr(sys, 'frozen', False):
        nome = 'MotorMarcos.exe' if sys.platform == 'win32' else 'MotorMarcos'
        return [str(pasta_recursos() / nome)]
    return [sys.executable, '-u', str(pasta_recursos() / 'motor_visual.py')]
