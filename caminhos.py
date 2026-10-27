"""Separa recursos do executável dos dados gravados por cada cliente."""
import os
import sys
from pathlib import Path

VERSAO = '1.0.9'


def pasta_recursos():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def pasta_dados():
    if getattr(sys, 'frozen', False):
        pasta = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'BotMarcos'
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta
    return Path(__file__).resolve().parent


def comando_motor():
    if getattr(sys, 'frozen', False):
        return [str(pasta_recursos() / 'MotorMarcos.exe')]
    return [sys.executable, '-u', str(pasta_recursos() / 'motor_visual.py')]
