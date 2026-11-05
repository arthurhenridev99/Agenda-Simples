import tempfile
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import database
from app import app


def testar_situacoes():
    banco_original = database.DATABASE

    with tempfile.TemporaryDirectory() as pasta:
        database.DATABASE = Path(pasta) / "teste_situacoes.db"

        try:
            database.inicializar_banco()

            ontem = (date.today() - timedelta(days=1)).isoformat()
            amanha = (date.today() + timedelta(days=1)).isoformat()

            with closing(database.conectar()) as conexao:
                profissional = conexao.execute("""
                    INSERT INTO profissional (nome, login, senha_hash)
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

                ids = []

                for numero, (dia, status) in enumerate(
                    [
                        (ontem, "agendado"),
                        (ontem, "agendado"),
                        (amanha, "agendado"),
                        (ontem, "cancelado"),
                    ],
                    start=1,
                ):
                    cursor = conexao.execute(
                        """
                        INSERT INTO agendamento
                        (id_cliente, id_servico, data, hora,
                         codigo_atendimento, status,
                         duracao_minutos, preco_praticado)
                        VALUES (?, ?, ?, '09:00', ?, ?, 100, 40)
                        """,
                        (
                            cliente,
                            servico,
                            dia,
                            f"TESTE{numero:011d}",
                            status,
                        ),
                    )
                    ids.append(cursor.lastrowid)

                conexao.commit()

            app.config["TESTING"] = True

            with app.test_client() as navegador:
                with navegador.session_transaction() as sessao:
                    sessao["id_profissional"] = profissional
                    sessao["csrf_agenda"] = "token-de-teste"

                for id_agendamento, situacao in zip(
                    ids,
                    ["concluido", "falta", "concluido", "falta"],
                ):
                    resposta = navegador.post(
                        f"/agenda/{id_agendamento}/situacao",
                        data={
                            "csrf_token": "token-de-teste",
                            "situacao": situacao,
                        },
                    )
                    assert resposta.status_code == 302

            with closing(database.conectar()) as conexao:
                resultados = [
                    conexao.execute(
                        """
                        SELECT status FROM agendamento
                        WHERE id_agendamento = ?
                        """,
                        (id_agendamento,),
                    ).fetchone()[0]
                    for id_agendamento in ids
                ]

            with closing(database.conectar()) as conexao:
                notificacoes = [linha[0] for linha in conexao.execute("""
                        SELECT tipo
                        FROM notificacao
                        ORDER BY id_notificacao
                        """).fetchall()]

            esperado = [
                "concluido",
                "falta",
                "agendado",
                "cancelado",
            ]

            assert resultados == esperado, resultados

            assert notificacoes == [
                "conclusao",
                "falta",
            ], notificacoes

            print("Notificacoes de conclusao e falta: OK")

            print("TESTES APROVADOS!")
            print("Conclusao: OK")
            print("Registro de falta: OK")
            print("Reserva futura protegida: OK")
            print("Reserva cancelada protegida: OK")
            print("Banco real preservado: OK")

        finally:
            database.DATABASE = banco_original


if __name__ == "__main__":
    testar_situacoes()
