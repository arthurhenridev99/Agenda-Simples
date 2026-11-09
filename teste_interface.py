"""Regressão da interface com SQLite temporário: python teste_interface.py."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from html.parser import HTMLParser

import database
from app import app
from werkzeug.security import generate_password_hash


class Pagina(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.tokens, self.campos, self.labels = [], [], [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href', '').startswith('/'):
            self.links.append(attrs['href'])
        if tag == 'input' and attrs.get('name') == 'csrf_token':
            self.tokens.append(attrs.get('value'))
        if tag in ('input', 'select') and attrs.get('type') != 'hidden':
            self.campos.append(attrs.get('id'))
        if tag == 'label':
            self.labels.append(attrs.get('for'))


class InterfaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE
        database.DATABASE = Path(self.temp.name) / 'interface.db'
        database.inicializar_banco()
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.dia = (date.today() + timedelta(days=2)).isoformat()
        with database.conectar() as c:
            c.execute('INSERT INTO profissional(nome,login,senha_hash) VALUES(?,?,?)',
                      ('Profissional Teste', 'teste', generate_password_hash('SenhaTeste123')))
            c.execute("INSERT INTO servico(id_profissional,nome,preco,duracao) VALUES(1,'Manicure',40,60)")
            for dia in range(7):
                c.execute("INSERT INTO horario_atendimento(id_profissional,dia_semana,hora_inicio,hora_fim) VALUES(1,?,'08:00','18:00')", (dia,))

    def tearDown(self):
        database.DATABASE = self.original
        self.temp.cleanup()

    def login(self):
        resposta = self.client.post('/login', data={'login': 'teste', 'senha': 'SenhaTeste123'})
        self.assertEqual(resposta.status_code, 302)

    def pagina(self, url):
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200, url)
        html = resposta.get_data(as_text=True)
        self.assertIn('/static/css/style.css', html)
        self.assertEqual(html.count('<main '), 1)
        pagina = Pagina(html)
        for campo in pagina.campos:
            self.assertIsNotNone(campo, url)
            self.assertIn(campo, pagina.labels, (url, campo))
        for link in pagina.links:
            self.assertLess(self.client.get(link).status_code, 400, (url, link))
        return pagina, html

    def test_navegacao_e_protecao(self):
        rotas = ['/painel','/agenda','/historico','/servicos','/horarios','/bloqueios','/notificacoes','/servicos/1/editar','/horarios/1/editar']
        for url in rotas:
            self.assertEqual(self.client.get(url).status_code, 302)
        for url in ['/','/login','/cadastro','/disponibilidade','/consultar-agendamento']:
            self.pagina(url)
        self.login()
        for url in rotas:
            self.pagina(url)
        for data in ['invalida','0001-01-01','9999-12-31']:
            self.pagina('/painel?data='+data)
        self.assertEqual(self.client.post('/sair').status_code, 302)
        self.assertEqual(self.client.get('/painel').status_code, 302)

    def test_fluxo_cliente_e_dashboard(self):
        url = f'/agendar?servico=1&data={self.dia}&hora=09:00'
        pagina, _ = self.pagina(url)
        dados = {'servico':'1','data':self.dia,'hora':'09:00','nome':'Cliente de Teste','telefone':'11999999999','csrf_token':pagina.tokens[0]}
        self.assertEqual(self.client.post('/agendar', data={**dados,'csrf_token':'errado'}).status_code, 400)
        resposta = self.client.post('/agendar', data=dados)
        self.assertEqual(resposta.status_code,302)
        self.pagina(resposta.location)
        codigo = resposta.location.rsplit('/',1)[1]
        consulta, _ = self.pagina('/consultar-agendamento')
        dados_consulta = {'telefone':dados['telefone'],'codigo':codigo,'csrf_token':consulta.tokens[0]}
        resposta = self.client.post('/consultar-agendamento', data=dados_consulta)
        self.assertIn('Cliente de Teste', resposta.get_data(as_text=True))
        resposta = self.client.post('/reagendar', data={**dados_consulta,'acao':'consultar','data_nova':self.dia})
        self.assertEqual(resposta.status_code,200)
        self.assertIn('Novo horário',resposta.get_data(as_text=True))
        resposta = self.client.post('/reagendar', data={**dados_consulta,'acao':'confirmar','data_nova':self.dia,'hora_nova':'11:00'})
        self.assertEqual(resposta.status_code,302)
        self.login()
        _, html = self.pagina('/painel?data='+self.dia)
        self.assertIn('Cliente de Teste', html)
        self.assertIn('11:00', html)
        self.assertIn('1 agendado(s)', html)
        with database.conectar() as c:
            self.assertEqual(c.execute('SELECT SUM(visualizada) FROM notificacao').fetchone()[0],0)
        resposta = self.client.post('/agendamentos/cancelar', data=dados_consulta)
        self.assertEqual(resposta.status_code,400)
        # O login limpa a sessão de consulta; renovar o token público.
        consulta, _ = self.pagina('/consultar-agendamento')
        dados_consulta['csrf_token'] = consulta.tokens[0]
        self.client.post('/agendamentos/cancelar', data=dados_consulta)
        with database.conectar() as c:
            self.assertEqual(c.execute('SELECT status FROM agendamento').fetchone()[0], 'cancelado')


if __name__ == '__main__':
    unittest.main(verbosity=2)
