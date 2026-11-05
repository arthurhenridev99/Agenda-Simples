import tempfile
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import database
import disponibilidade
from app import app
from agendamentos import registrar_agendamento


class RelogioSimulado(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2030, 1, 7, 10, 0)


def testar_antecedencia():
    banco_original = database.DATABASE
    data_teste = "2030-01-07"

    with tempfile.TemporaryDirectory() as pasta:
        database.DATABASE = Path(pasta) / "teste_antecedencia.db"

        try:
            database.inicializar_banco()

            with closing(database.conectar()) as conexao:
                profissional = conexao.execute("""
                    INSERT INTO profissional (nome, login, senha_hash)
                    VALUES ('Teste', 'teste', 'hash_teste')
                    """).lastrowid

                servico = conexao.execute(
                    """
                    INSERT INTO servico
                    (id_profissional, nome, preco, duracao, ativo)
                    VALUES (?, 'Manicure', 40, 60, 1)
                    """,
                    (profissional,),
                ).lastrowid

                conexao.execute(
                    """
                    INSERT INTO horario_atendimento
                    (id_profissional, dia_semana, hora_inicio, hora_fim)
                    VALUES (?, ?, '08:00', '18:00')
                    """,
                    (
                        profissional,
                        date.fromisoformat(data_teste).weekday(),
                    ),
                )

                conexao.commit()

            with patch.object(disponibilidade, "datetime", RelogioSimulado):
                horarios = disponibilidade.calcular_horarios_disponiveis(
                    servico, data_teste
                )

                assert "13:30" not in horarios
                assert "14:00" in horarios

                # Tentativa de acessar a rota diretamente
                with app.test_client() as navegador:
                    resposta = navegador.post(
                        "/agendar",
                        data={
                            "servico": str(servico),
                            "data": data_teste,
                            "hora": "13:30",
                            "nome": "Cliente Teste",
                            "telefone": "62900000000",
                        },
                    )

                    assert resposta.status_code == 302

                # Tentativa direta na funcao de registro
                try:
                    registrar_agendamento(
                        servico,
                        data_teste,
                        "13:30",
                        "Cliente Teste",
                        "62900000000",
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Reserva fora do prazo foi permitida!")

            with closing(database.conectar()) as conexao:
                quantidade = conexao.execute(
                    "SELECT COUNT(*) FROM agendamento"
                ).fetchone()[0]

            assert quantidade == 0

            print("TESTES DE ANTECEDENCIA APROVADOS!")
            print("Horario com menos de 4 horas: BLOQUEADO")
            print("Horario com 4 horas: DISPONIVEL")
            print("Acesso direto ao agendamento: BLOQUEADO")
            print("Reserva indevida no SQLite: NENHUMA")
            print("Banco principal preservado: OK")

        finally:
            database.DATABASE = banco_original


if __name__ == "__main__":
    testar_antecedencia()
