import tempfile
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import database
from agendamentos import registrar_agendamento, reagendar_agendamento
from app import app


def testar_notificacoes():
    banco_original = database.DATABASE
    configuracao_teste = app.config["TESTING"]

    with tempfile.TemporaryDirectory() as pasta:
        database.DATABASE = Path(pasta) / "teste_notificacoes.db"

        try:
            database.inicializar_banco()

            data_original = date.today() + timedelta(days=7)
            data_nova = date.today() + timedelta(days=8)

            with closing(database.conectar()) as conexao:
                id_profissional = conexao.execute("""
                    INSERT INTO profissional
                        (nome, login, senha_hash)
                    VALUES ('Profissional Teste', 'teste', 'hash_teste')
                    """).lastrowid

                id_servico = conexao.execute(
                    """
                    INSERT INTO servico
                        (id_profissional, nome, preco, duracao, ativo)
                    VALUES (?, 'Manicure', 40, 100, 1)
                    """,
                    (id_profissional,),
                ).lastrowid

                for dia in (data_original, data_nova):
                    conexao.execute(
                        """
                        INSERT INTO horario_atendimento
                            (id_profissional, dia_semana,
                             hora_inicio, hora_fim)
                        VALUES (?, ?, '08:00', '18:00')
                        """,
                        (id_profissional, dia.weekday()),
                    )

                conexao.commit()

            # Teste 1: novo agendamento
            codigo = registrar_agendamento(
                id_servico,
                data_original.isoformat(),
                "09:00",
                "Cliente Teste",
                "62900000000",
            )

            with closing(database.conectar()) as conexao:
                id_agendamento = conexao.execute(
                    """
                    SELECT id_agendamento
                    FROM agendamento
                    WHERE codigo_atendimento = ?
                    """,
                    (codigo,),
                ).fetchone()[0]

            # Teste 2: reagendamento
            reagendar_agendamento(
                id_agendamento,
                data_nova.isoformat(),
                "10:00",
            )

            # Teste 3: cancelamento pela cliente
            app.config["TESTING"] = True

            with app.test_client() as navegador:
                with navegador.session_transaction() as sessao:
                    sessao["csrf_consulta"] = "token-teste"

                resposta = navegador.post(
                    "/agendamentos/cancelar",
                    data={
                        "csrf_token": "token-teste",
                        "codigo": codigo,
                        "telefone": "62900000000",
                    },
                )

                assert resposta.status_code == 302

            with closing(database.conectar()) as conexao:
                notificacoes = [linha[0] for linha in conexao.execute("""
                        SELECT tipo
                        FROM notificacao
                        ORDER BY id_notificacao
                        """).fetchall()]

                reserva = conexao.execute(
                    """
                    SELECT data, hora, status
                    FROM agendamento
                    WHERE id_agendamento = ?
                    """,
                    (id_agendamento,),
                ).fetchone()

                quantidade = conexao.execute(
                    "SELECT COUNT(*) FROM agendamento"
                ).fetchone()[0]

            assert notificacoes == [
                "novo_agendamento",
                "reagendamento",
                "cancelamento",
            ], notificacoes

            assert reserva == (
                data_nova.isoformat(),
                "10:00",
                "cancelado",
            ), reserva

            assert quantidade == 1, quantidade

            print("TESTES DE NOTIFICACOES APROVADOS!")
            print("Novo agendamento: OK")
            print("Reagendamento: OK")
            print("Cancelamento: OK")
            print("Codigo e registro preservados: OK")
            print("Banco principal preservado: OK")

        finally:
            database.DATABASE = banco_original
            app.config["TESTING"] = configuracao_teste


if __name__ == "__main__":
    testar_notificacoes()
