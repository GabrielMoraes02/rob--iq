import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile
import caminhos

class CaminhosMacTests(unittest.TestCase):
    def test_motor_nativo(self):
        with patch.object(caminhos.sys, 'frozen', True, create=True), patch.object(caminhos.sys, 'platform', 'darwin'):
            self.assertEqual(Path(caminhos.comando_motor()[0]).name, 'MotorMarcos')
    def test_windows_preservado(self):
        with patch.object(caminhos.sys, 'frozen', True, create=True), patch.object(caminhos.sys, 'platform', 'win32'):
            self.assertEqual(Path(caminhos.comando_motor()[0]).name, 'MotorMarcos.exe')
    def test_dados_fora_do_app(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp, patch.object(caminhos.sys, 'frozen', True, create=True), patch.object(caminhos.sys, 'platform', 'darwin'), patch.object(Path, 'home', return_value=Path(tmp)):
            self.assertEqual(caminhos.pasta_dados(), Path(tmp)/'Library'/'Application Support'/'BotMarcos')
            self.assertTrue(caminhos.pasta_dados().is_dir())
