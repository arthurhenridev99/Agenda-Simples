import tempfile
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import database
from app import app
from notificacoes import registrar_notificacao


def testar_visualizacao():
    banco_original = database.DATABASE
    testing_original = app.config["TESTING"]

    with tempfile.TemporaryDirectory() as pasta:
        database.DATABASE = Path(pasta) / "notificacoes_teste.db"

        try:
            database.inicializar_banco()

            with closing(database.conectar()) as conexao:
                profissional = conexao.execute("""
                    INSERT INTO profissional
                        (nome, login, senha_hash)
                    VALUES ('Teste', 'prof_teste', 'hash_teste')
                    """).lastrowid

                cliente = conexao.execute("""
                    INSERT INTO cliente (nome, telefone)
                    VALUES ('Cliente Teste', '62900000000')
                    """).lastrowid

                servico = conexao.execute(
                    """
                    INSERT INTO servico
                        (id_profissional, nome, preco, duracao, ativo)
                    VALUES (?, 'Manicure', 40, 100, 1)
                    """,
                    (profissional,),
                ).lastrowid

                dia = (date.today() + timedelta(days=7)).isoformat()

                agendamento = conexao.execute(
                    """
                    INSERT INTO agendamento (
                        id_cliente, id_servico, data, hora,
                        codigo_atendimento, status,
                        duracao_minutos, preco_praticado
                    )
                    VALUES (?, ?, ?, '09:00',
                            'CODIGOTESTE12345', 'agendado', 100, 40)
                    """,
                    (cliente, servico, dia),
                ).lastrowid

                registrar_notificacao(conexao, agendamento, "novo_agendamento")
                registrar_notificacao(conexao, agendamento, "reagendamento")

                conexao.commit()

                primeira = conexao.execute("""
                    SELECT id_notificacao FROM notificacao
                    ORDER BY id_notificacao LIMIT 1
                    """).fetchone()[0]

            app.config["TESTING"] = True

            with app.test_client() as navegador:
                with navegador.session_transaction() as sessao:
                    sessao["id_profissional"] = profissional
                    sessao["csrf_notificacoes"] = "token-teste"

                resposta = navegador.get("/notificacoes")

                assert resposta.status_code == 200
                assert b"Novo agendamento" in resposta.data
                assert b"Reagendamento" in resposta.data
                assert b"Marcar como lida" in resposta.data

                resposta = navegador.post(
                    f"/notificacoes/{primeira}/marcar-lida",
                    data={"csrf_token": "token-teste"},
                )

                assert resposta.status_code == 302

                # Token incorreto deve ser rejeitado.
                resposta = navegador.post(
                    f"/notificacoes/{primeira}/marcar-lida",
                    data={"csrf_token": "incorreto"},
                )

                assert resposta.status_code == 400

            with closing(database.conectar()) as conexao:
                estados = [linha[0] for linha in conexao.execute("""
                        SELECT visualizada FROM notificacao
                        ORDER BY id_notificacao
                        """)]

            assert estados == [1, 0], estados

            print("TESTES DE VISUALIZACAO APROVADOS!")
            print("Listagem: OK")
            print("Marcar como lida: OK")
            print("Notificacao restante preservada: OK")
            print("Protecao CSRF: OK")
            print("Banco principal preservado: OK")

        finally:
            database.DATABASE = banco_original
            app.config["TESTING"] = testing_original


if __name__ == "__main__":
    testar_visualizacao()
