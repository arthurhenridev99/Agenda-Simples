"""Cadastro e recuperação usando SQLite temporário e SMTP simulado."""
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.parse import urlsplit

import database
from app import app
from recuperacao import gerar_token, enviar_recuperacao, configuracao_email
from werkzeug.security import generate_password_hash, check_password_hash


class ContasTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE
        database.DATABASE = Path(self.temp.name) / 'contas.db'
        database.inicializar_banco()
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.env = patch.dict(os.environ, {
            'FLASK_SECRET_KEY':'segredo-apenas-de-teste', 'SMTP_HOST':'smtp.example.test',
            'SMTP_PORT':'587','SMTP_USER':'usuario','SMTP_PASSWORD':'senha-teste',
            'SMTP_FROM':'agenda@example.test','APP_BASE_URL':'https://agenda.example.test',
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        database.DATABASE = self.original
        self.temp.cleanup()

    def csrf(self, url, key):
        self.client.get(url)
        with self.client.session_transaction() as session:
            return session[key]

    def cadastro(self, email='ana@example.test', **alteracoes):
        dados = dict(nome='Ana Teste', email=email, whatsapp='(11) 99999-9999',
                     senha='SenhaAntiga123', confirmar_senha='SenhaAntiga123',
                     csrf_token=self.csrf('/cadastro','csrf_cadastro'))
        dados.update(alteracoes)
        return self.client.post('/cadastro',data=dados)

    def solicitar(self, email='ana@example.test'):
        return self.client.post('/esqueci-minha-senha',data={
            'email':email,'csrf_token':self.csrf('/esqueci-minha-senha','csrf_recuperacao')})

    def test_cadastro_multiplo_e_duplicidade(self):
        for email in ('ANA@example.test','bia@example.test'):
            self.assertIn('Conta criada com sucesso',self.cadastro(email).get_data(as_text=True))
        self.assertIn('Não foi possível', self.cadastro().get_data(as_text=True))
        with database.conectar() as c:
            rows = c.execute('SELECT login, whatsapp, senha_hash FROM profissional ORDER BY id_profissional').fetchall()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0][:2],('ana@example.test','11999999999'))
        self.assertTrue(check_password_hash(rows[0][2],'SenhaAntiga123'))
        self.assertEqual(self.client.post('/login',data={'login':'ANA@example.test','senha':'SenhaAntiga123'}).status_code,302)

    def test_validacoes_cadastro(self):
        for dados in ({'csrf_token':'errado'}, {'email':'invalido'}, {'whatsapp':'123'},
                      {'senha':'curta'}, {'confirmar_senha':'outra'}, {'nome':''}):
            self.cadastro(**dados)
        with database.conectar() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM profissional').fetchone()[0],0)

    def test_migracao_preserva_conta_antiga(self):
        with database.conectar() as c:
            c.execute('DROP TABLE profissional')
            c.execute('CREATE TABLE profissional(id_profissional INTEGER PRIMARY KEY, nome TEXT, login TEXT UNIQUE, senha_hash TEXT)')
            c.execute('INSERT INTO profissional VALUES(1,?,?,?)',('Antiga','antiga',generate_password_hash('SenhaAntiga123')))
        self.assertEqual(self.client.get('/cadastro').status_code,200)
        self.assertEqual(self.client.get('/cadastro').status_code,200)
        with database.conectar() as c:
            self.assertEqual(c.execute('SELECT nome,login,whatsapp FROM profissional').fetchone(),('Antiga','antiga',''))
        self.assertEqual(self.client.post('/login',data={'login':'antiga','senha':'SenhaAntiga123'}).status_code,302)

    def test_recuperacao_completa_e_uso_unico(self):
        self.cadastro()
        with patch('recuperacao.enviar_recuperacao') as envio:
            self.assertEqual(self.solicitar().status_code,200)
            envio.assert_called_once()
            caminho=envio.call_args.args[1]
        self.assertNotIn(caminho, self.client.get('/esqueci-minha-senha').get_data(as_text=True))
        self.assertIn('Nova senha',self.client.get(caminho).get_data(as_text=True))
        csrf=self.csrf(caminho,'csrf_redefinicao')
        self.assertIn('Formulário inválido',self.client.post(caminho,data={'csrf_token':'errado'}).get_data(as_text=True))
        self.assertIn('não coincidem',self.client.post(caminho,data={'csrf_token':csrf,'senha':'NovaSenha123','confirmar_senha':'diferente'}).get_data(as_text=True))
        resposta=self.client.post(caminho,data={'csrf_token':csrf,'senha':'NovaSenha123','confirmar_senha':'NovaSenha123'})
        self.assertIn('Senha alterada com sucesso',resposta.get_data(as_text=True))
        self.assertIn('já foi utilizado',self.client.get(caminho).get_data(as_text=True))
        self.assertEqual(self.client.post('/login',data={'login':'ana@example.test','senha':'SenhaAntiga123'}).status_code,200)
        self.assertEqual(self.client.post('/login',data={'login':'ana@example.test','senha':'NovaSenha123'}).status_code,302)

    def test_link_invalido_e_expirado(self):
        self.cadastro()
        with database.conectar() as c:
            profissional=c.execute('SELECT id_profissional,senha_hash FROM profissional').fetchone()
        with app.app_context(), patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=int(time.time())-1801):
            token=gerar_token(profissional)
        for valor in ('invalido',token,token+'X'):
            html=self.client.get('/redefinir-senha/'+valor).get_data(as_text=True)
            self.assertIn('Solicite um novo link',html)
            self.assertNotIn('name="senha"',html)

    def test_email_desconhecido_e_limite(self):
        with patch('recuperacao.enviar_recuperacao') as envio:
            html=self.solicitar('naoexiste@example.test').get_data(as_text=True)
            self.assertIn('Se este e-mail estiver cadastrado',html)
            envio.assert_not_called()
            self.assertEqual(self.solicitar().status_code,429)

    def test_envio_nao_configurado_e_falha(self):
        self.cadastro()
        with patch.dict(os.environ,{'SMTP_HOST':''}):
            resposta=self.solicitar()
            self.assertEqual(resposta.status_code,503)
            self.assertIn('temporariamente indisponível',resposta.get_data(as_text=True))
        with patch('recuperacao.enviar_recuperacao',side_effect=OSError('smtp indisponível')):
            self.assertEqual(self.solicitar().status_code,200)

    def test_smtp_tls_e_url_configurada(self):
        with patch('recuperacao.smtplib.SMTP') as smtp:
            config=configuracao_email()
            enviar_recuperacao('ana@example.test','/redefinir-senha/token-teste',config)
            servidor=smtp.return_value.__enter__.return_value
            servidor.starttls.assert_called_once()
            servidor.login.assert_called_once_with('usuario','senha-teste')
            mensagem=servidor.send_message.call_args.args[0]
            self.assertEqual(mensagem['To'],'ana@example.test')
            self.assertIn('https://agenda.example.test/redefinir-senha/token-teste',mensagem.get_content())
        with patch.dict(os.environ,{'APP_BASE_URL':'http://site-publico.example.test'}):
            self.assertIsNone(configuracao_email())


if __name__ == '__main__':
    unittest.main(verbosity=2)
