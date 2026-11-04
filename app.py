import os
import secrets
import sqlite3
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database import conectar

app = Flask(__name__)

# Chave necessária para proteger as sessões de login.
# Em produção, deve ser definida na variável FLASK_SECRET_KEY.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)


def login_obrigatorio(funcao):
    @wraps(funcao)
    def verificar_login(*args, **kwargs):
        if "id_profissional" not in session:
            return redirect(url_for("login"))
        return funcao(*args, **kwargs)

    return verificar_login


@app.route("/")
def inicio():
    return render_template("index.html")


# UC09 - Realizar Cadastro
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    erro = None
    sucesso = None

    conexao = conectar()

    try:
        profissional = conexao.execute(
            "SELECT id_profissional FROM profissional LIMIT 1"
        ).fetchone()

        if profissional:
            return render_template("cadastro.html", cadastro_existente=True)

        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            login_informado = request.form.get("login", "").strip()
            senha = request.form.get("senha", "")
            confirmar_senha = request.form.get("confirmar_senha", "")

            if not nome or not login_informado or not senha:
                erro = "Preencha todos os campos obrigatórios."

            elif len(senha) < 8:
                erro = "A senha deve possuir pelo menos 8 caracteres."

            elif senha != confirmar_senha:
                erro = "As senhas informadas não coincidem."

            else:
                senha_hash = generate_password_hash(senha)

                try:
                    conexao.execute(
                        """
                        INSERT INTO profissional (nome, login, senha_hash)
                        VALUES (?, ?, ?)
                        """,
                        (nome, login_informado, senha_hash),
                    )
                    conexao.commit()
                    sucesso = "Cadastro realizado com sucesso!"

                except sqlite3.IntegrityError:
                    conexao.rollback()
                    erro = "Não foi possível realizar o cadastro. Verifique o login."

    finally:
        conexao.close()

    return render_template("cadastro.html", erro=erro, sucesso=sucesso)


# UC10 - Realizar Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if "id_profissional" in session:
        return redirect(url_for("painel"))

    erro = None

    if request.method == "POST":
        login_informado = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")

        conexao = conectar()

        try:
            profissional = conexao.execute(
                """
                SELECT id_profissional, nome, senha_hash
                FROM profissional
                WHERE login = ?
                """,
                (login_informado,),
            ).fetchone()
        finally:
            conexao.close()

        if profissional and check_password_hash(profissional[2], senha):
            session.clear()
            session["id_profissional"] = profissional[0]
            session["nome_profissional"] = profissional[1]

            return redirect(url_for("painel"))

        erro = "Login ou senha inválidos."

    return render_template("login.html", erro=erro)


# Painel administrativo protegido
@app.route("/painel")
@login_obrigatorio
def painel():
    return render_template("painel.html", nome=session["nome_profissional"])


# Encerrar sessão
@app.route("/sair", methods=["POST"])
@login_obrigatorio
def sair():
    session.clear()
    return redirect(url_for("login"))


# UC11 - Listar e cadastrar serviços
@app.route("/servicos", methods=["GET", "POST"])
@login_obrigatorio
def listar_servicos():
    erro = None
    token = session.get("csrf_servicos")

    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_servicos"] = token

    if request.method == "POST":
        from decimal import Decimal, InvalidOperation

        nome = request.form.get("nome", "").strip()
        preco_texto = request.form.get("preco", "").strip().replace(",", ".")
        duracao_texto = request.form.get("duracao", "").strip()

        token_recebido = request.form.get("csrf_token", "")

        if not secrets.compare_digest(token, token_recebido):
            erro = "Formulário inválido. Atualize a página e tente novamente."

        elif not nome or len(nome) > 100:
            erro = "Informe um nome válido com até 100 caracteres."

        else:
            try:
                preco = Decimal(preco_texto)
                duracao = int(duracao_texto)

                if (
                    not preco.is_finite()
                    or preco < 0
                    or preco.as_tuple().exponent < -2
                    or duracao <= 0
                ):
                    raise ValueError

                conexao = conectar()
                try:
                    conexao.execute(
                        """
                        INSERT INTO servico
                        (id_profissional, nome, preco, duracao, ativo)
                        VALUES (?, ?, ?, ?, 1)
                        """,
                        (session["id_profissional"], nome, float(preco), duracao),
                    )
                    conexao.commit()
                finally:
                    conexao.close()

                return redirect(url_for("listar_servicos"))

            except (ValueError, InvalidOperation):
                erro = "Informe um preço e uma duração válidos."

    conexao = conectar()
    try:
        servicos = conexao.execute(
            """
            SELECT id_servico, nome, preco, duracao, ativo
            FROM servico
            WHERE id_profissional = ?
            ORDER BY nome
            """,
            (session["id_profissional"],),
        ).fetchall()
    finally:
        conexao.close()

    return render_template(
        "servicos.html", servicos=servicos, erro=erro, csrf_token=token
    )


# UC11 - Editar servico
@app.route("/servicos/<int:id_servico>/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar_servico(id_servico):
    from decimal import Decimal, InvalidOperation

    erro = None

    token = session.get("csrf_servicos")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_servicos"] = token

    conexao = conectar()

    try:
        servico = conexao.execute(
            """
            SELECT id_servico, nome, preco, duracao
            FROM servico
            WHERE id_servico = ? AND id_profissional = ?
            """,
            (id_servico, session["id_profissional"]),
        ).fetchone()

        if servico is None:
            return "Serviço não encontrado.", 404

        if request.method == "POST":
            token_recebido = request.form.get("csrf_token", "")

            nome = request.form.get("nome", "").strip()
            preco_texto = request.form.get("preco", "").strip().replace(",", ".")
            duracao_texto = request.form.get("duracao", "").strip()

            if not secrets.compare_digest(token, token_recebido):
                erro = "Formulário inválido. Atualize a página."

            elif not nome or len(nome) > 100:
                erro = "Informe um nome válido com até 100 caracteres."

            else:
                try:
                    preco = Decimal(preco_texto)
                    duracao = int(duracao_texto)

                    if (
                        not preco.is_finite()
                        or preco < 0
                        or preco.as_tuple().exponent < -2
                        or duracao <= 0
                    ):
                        raise ValueError

                    conexao.execute(
                        """
                        UPDATE servico
                        SET nome = ?, preco = ?, duracao = ?
                        WHERE id_servico = ? AND id_profissional = ?
                        """,
                        (
                            nome,
                            float(preco),
                            duracao,
                            id_servico,
                            session["id_profissional"],
                        ),
                    )

                    conexao.commit()
                    return redirect(url_for("listar_servicos"))

                except (ValueError, InvalidOperation):
                    erro = "Informe um preço e uma duração válidos."

        return render_template(
            "editar_servico.html", servico=servico, erro=erro, csrf_token=token
        )

    finally:
        conexao.close()


# UC11 - Desativar ou reativar servico
@app.route("/servicos/<int:id_servico>/alternar-status", methods=["POST"])
@login_obrigatorio
def alternar_status_servico(id_servico):
    token_esperado = session.get("csrf_servicos", "")
    token_recebido = request.form.get("csrf_token", "")

    # Verificar a autenticidade do formulario
    if not token_esperado or not secrets.compare_digest(token_esperado, token_recebido):
        return "Formulario invalido.", 400

    conexao = conectar()

    try:
        # Localizar somente servicos da profissional autenticada
        servico = conexao.execute(
            """
            SELECT ativo
            FROM servico
            WHERE id_servico = ? AND id_profissional = ?
            """,
            (id_servico, session["id_profissional"]),
        ).fetchone()

        if servico is None:
            return "Servico nao encontrado.", 404

        # Alternar entre ativo (1) e inativo (0)
        novo_status = 0 if servico[0] == 1 else 1

        conexao.execute(
            """
            UPDATE servico
            SET ativo = ?
            WHERE id_servico = ? AND id_profissional = ?
            """,
            (novo_status, id_servico, session["id_profissional"]),
        )

        conexao.commit()

    finally:
        conexao.close()

    return redirect(url_for("listar_servicos"))


# UC12 - Listar e cadastrar horarios de atendimento
@app.route("/horarios", methods=["GET", "POST"])
@login_obrigatorio
def listar_horarios():
    import re

    dias_semana = [
        "Segunda-feira",
        "Terça-feira",
        "Quarta-feira",
        "Quinta-feira",
        "Sexta-feira",
        "Sábado",
        "Domingo",
    ]

    erro = None

    token = session.get("csrf_horarios")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_horarios"] = token

    if request.method == "POST":
        token_recebido = request.form.get("csrf_token", "")

        dia_texto = request.form.get("dia_semana", "")
        hora_inicio = request.form.get("hora_inicio", "")
        hora_fim = request.form.get("hora_fim", "")

        formato_hora = r"(?:[01]\d|2[0-3]):[0-5]\d"

        if not secrets.compare_digest(token, token_recebido):
            erro = "Formulário inválido. Atualize a página."

        elif not dia_texto.isdigit() or int(dia_texto) not in range(7):
            erro = "Selecione um dia da semana válido."

        elif not (
            re.fullmatch(formato_hora, hora_inicio)
            and re.fullmatch(formato_hora, hora_fim)
        ):
            erro = "Informe horários válidos."

        elif hora_inicio >= hora_fim:
            erro = "O horário inicial deve ser anterior ao final."

        else:
            dia_semana = int(dia_texto)
            conexao = conectar()

            try:
                conflito = conexao.execute(
                    """
                    SELECT id_horario
                    FROM horario_atendimento
                    WHERE id_profissional = ?
                      AND dia_semana = ?
                      AND hora_inicio < ?
                      AND hora_fim > ?
                    LIMIT 1
                    """,
                    (
                        session["id_profissional"],
                        dia_semana,
                        hora_fim,
                        hora_inicio,
                    ),
                ).fetchone()

                if conflito:
                    erro = "Este período apresenta conflito com outro horário."
                else:
                    conexao.execute(
                        """
                        INSERT INTO horario_atendimento
                        (id_profissional, dia_semana, hora_inicio, hora_fim)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            session["id_profissional"],
                            dia_semana,
                            hora_inicio,
                            hora_fim,
                        ),
                    )

                    conexao.commit()

            finally:
                conexao.close()

            if erro is None:
                return redirect(url_for("listar_horarios"))

    conexao = conectar()

    try:
        horarios = conexao.execute(
            """
            SELECT id_horario, dia_semana, hora_inicio, hora_fim
            FROM horario_atendimento
            WHERE id_profissional = ?
            ORDER BY dia_semana, hora_inicio
            """,
            (session["id_profissional"],),
        ).fetchall()

    finally:
        conexao.close()

    return render_template(
        "horarios.html",
        horarios=horarios,
        dias_semana=dias_semana,
        erro=erro,
        csrf_token=token,
    )


# UC12 - Remover um periodo de atendimento
@app.route("/horarios/<int:id_horario>/remover", methods=["POST"])
@login_obrigatorio
def remover_horario(id_horario):
    token_esperado = session.get("csrf_horarios", "")
    token_recebido = request.form.get("csrf_token", "")

    if not token_esperado or not secrets.compare_digest(token_esperado, token_recebido):
        return "Formulário inválido.", 400

    conexao = conectar()

    try:
        conexao.execute(
            """
            DELETE FROM horario_atendimento
            WHERE id_horario = ?
              AND id_profissional = ?
            """,
            (id_horario, session["id_profissional"]),
        )
        conexao.commit()
    finally:
        conexao.close()

    return redirect(url_for("listar_horarios"))


# UC12 - Editar horario de atendimento
@app.route("/horarios/<int:id_horario>/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar_horario(id_horario):
    import re

    dias_semana = [
        "Segunda-feira",
        "Terça-feira",
        "Quarta-feira",
        "Quinta-feira",
        "Sexta-feira",
        "Sábado",
        "Domingo",
    ]

    erro = None

    token = session.get("csrf_horarios")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_horarios"] = token

    conexao = conectar()

    try:
        horario = conexao.execute(
            """
            SELECT id_horario, dia_semana, hora_inicio, hora_fim
            FROM horario_atendimento
            WHERE id_horario = ? AND id_profissional = ?
            """,
            (id_horario, session["id_profissional"]),
        ).fetchone()

        if horario is None:
            return "Horário não encontrado.", 404

        if request.method == "POST":
            token_recebido = request.form.get("csrf_token", "")
            dia_texto = request.form.get("dia_semana", "")
            hora_inicio = request.form.get("hora_inicio", "")
            hora_fim = request.form.get("hora_fim", "")

            formato_hora = r"(?:[01]\d|2[0-3]):[0-5]\d"

            if not secrets.compare_digest(token, token_recebido):
                erro = "Formulário inválido. Atualize a página."

            elif not dia_texto.isdigit() or int(dia_texto) not in range(7):
                erro = "Selecione um dia válido."

            elif not (
                re.fullmatch(formato_hora, hora_inicio)
                and re.fullmatch(formato_hora, hora_fim)
            ):
                erro = "Informe horários válidos."

            elif hora_inicio >= hora_fim:
                erro = "O horário inicial deve ser anterior ao final."

            else:
                dia_semana = int(dia_texto)

                conflito = conexao.execute(
                    """
                    SELECT id_horario
                    FROM horario_atendimento
                    WHERE id_profissional = ?
                      AND dia_semana = ?
                      AND id_horario != ?
                      AND hora_inicio < ?
                      AND hora_fim > ?
                    LIMIT 1
                    """,
                    (
                        session["id_profissional"],
                        dia_semana,
                        id_horario,
                        hora_fim,
                        hora_inicio,
                    ),
                ).fetchone()

                if conflito:
                    erro = "Este período apresenta conflito com outro horário."
                else:
                    conexao.execute(
                        """
                        UPDATE horario_atendimento
                        SET dia_semana = ?, hora_inicio = ?, hora_fim = ?
                        WHERE id_horario = ? AND id_profissional = ?
                        """,
                        (
                            dia_semana,
                            hora_inicio,
                            hora_fim,
                            id_horario,
                            session["id_profissional"],
                        ),
                    )

                    conexao.commit()
                    return redirect(url_for("listar_horarios"))

        return render_template(
            "editar_horario.html",
            horario=horario,
            dias_semana=dias_semana,
            erro=erro,
            csrf_token=token,
        )

    finally:
        conexao.close()


# UC13 - Cadastrar e listar bloqueios de horarios
@app.route("/bloqueios", methods=["GET", "POST"])
@login_obrigatorio
def listar_bloqueios():
    import re
    from datetime import date

    erro = None
    formulario = request.form

    token = session.get("csrf_bloqueios")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_bloqueios"] = token

    conexao = conectar()

    try:
        if request.method == "POST":
            token_recebido = formulario.get("csrf_token", "")
            data_texto = formulario.get("data", "")
            hora_inicio = formulario.get("hora_inicio", "")
            hora_fim = formulario.get("hora_fim", "")

            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_texto):
                    raise ValueError
                data_bloqueio = date.fromisoformat(data_texto)
            except ValueError:
                data_bloqueio = None

            formato_hora = r"(?:[01]\d|2[0-3]):[0-5]\d"

            if not secrets.compare_digest(token, token_recebido):
                erro = "Formulário inválido. Atualize a página."

            elif data_bloqueio is None:
                erro = "Informe uma data válida."

            elif data_bloqueio < date.today():
                erro = "Não é permitido cadastrar bloqueios em datas passadas."

            elif not (
                re.fullmatch(formato_hora, hora_inicio)
                and re.fullmatch(formato_hora, hora_fim)
            ):
                erro = "Informe horários válidos."

            elif hora_inicio >= hora_fim:
                erro = "O horário inicial deve ser anterior ao final."

            else:
                conflito = conexao.execute(
                    """
                    SELECT id_bloqueio
                    FROM bloqueio
                    WHERE id_profissional = ?
                      AND data = ?
                      AND hora_inicio < ?
                      AND hora_fim > ?
                    LIMIT 1
                    """,
                    (
                        session["id_profissional"],
                        data_texto,
                        hora_fim,
                        hora_inicio,
                    ),
                ).fetchone()

                if conflito:
                    erro = "Este período já possui um bloqueio."
                else:
                    conexao.execute(
                        """
                        INSERT INTO bloqueio
                            (id_profissional, data, hora_inicio, hora_fim)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            session["id_profissional"],
                            data_texto,
                            hora_inicio,
                            hora_fim,
                        ),
                    )

                    conexao.commit()
                    return redirect(url_for("listar_bloqueios"))

        bloqueios = conexao.execute(
            """
            SELECT id_bloqueio, data, hora_inicio, hora_fim
            FROM bloqueio
            WHERE id_profissional = ?
            ORDER BY data, hora_inicio
            """,
            (session["id_profissional"],),
        ).fetchall()

        return render_template(
            "bloqueios.html",
            bloqueios=bloqueios,
            erro=erro,
            csrf_token=token,
            data_minima=date.today().isoformat(),
            formulario=formulario,
        )

    finally:
        conexao.close()


# UC13 - Remover bloqueio de horario
@app.route("/bloqueios/<int:id_bloqueio>/remover", methods=["POST"])
@login_obrigatorio
def remover_bloqueio(id_bloqueio):
    token_esperado = session.get("csrf_bloqueios", "")
    token_recebido = request.form.get("csrf_token", "")

    if not token_esperado or not secrets.compare_digest(token_esperado, token_recebido):
        return "Formulário inválido.", 400

    conexao = conectar()

    try:
        conexao.execute(
            """
            DELETE FROM bloqueio
            WHERE id_bloqueio = ?
              AND id_profissional = ?
            """,
            (id_bloqueio, session["id_profissional"]),
        )
        conexao.commit()
    finally:
        conexao.close()

    return redirect(url_for("listar_bloqueios"))


# UC14 - Consultar disponibilidade de horarios
@app.route("/disponibilidade")
def consultar_disponibilidade():
    from datetime import date

    servico_texto = request.args.get("servico", "")
    data_texto = request.args.get("data", "")

    horarios = []
    erro = None
    consulta_realizada = False

    conexao = conectar()

    try:
        servicos = conexao.execute("""
            SELECT id_servico, nome, preco, duracao
            FROM servico
            WHERE ativo = 1
            ORDER BY nome
            """).fetchall()
    finally:
        conexao.close()

    if request.args:
        if not servico_texto.isdigit():
            erro = "Selecione um serviço válido."

        elif not any(servico[0] == int(servico_texto) for servico in servicos):
            erro = "O serviço selecionado não está disponível."

        else:
            try:
                data_escolhida = date.fromisoformat(data_texto)

                if data_escolhida.isoformat() != data_texto:
                    raise ValueError

                if data_escolhida < date.today():
                    erro = "Selecione uma data atual ou futura."

            except ValueError:
                erro = "Selecione uma data válida."

            if erro is None:
                from disponibilidade import calcular_horarios_disponiveis

                horarios = calcular_horarios_disponiveis(
                    int(servico_texto),
                    data_texto,
                )
                consulta_realizada = True

    return render_template(
        "disponibilidade.html",
        servicos=servicos,
        servico_selecionado=servico_texto,
        data_selecionada=data_texto,
        data_minima=date.today().isoformat(),
        horarios=horarios,
        erro=erro,
        consulta_realizada=consulta_realizada,
    )


# Realizar agendamento da cliente
@app.route("/agendar", methods=["GET", "POST"])
def agendar():
    from datetime import date

    from agendamentos import registrar_agendamento
    from disponibilidade import calcular_horarios_disponiveis

    origem = request.form if request.method == "POST" else request.args

    servico_texto = origem.get("servico", "")
    data_texto = origem.get("data", "")
    hora = origem.get("hora", "")

    if not servico_texto.isdigit():
        return redirect(url_for("consultar_disponibilidade"))

    id_servico = int(servico_texto)

    try:
        data_escolhida = date.fromisoformat(data_texto)
        if data_escolhida.isoformat() != data_texto:
            raise ValueError
    except ValueError:
        return redirect(url_for("consultar_disponibilidade"))

    conexao = conectar()
    try:
        servico = conexao.execute(
            """
            SELECT id_servico, nome, duracao, preco
            FROM servico
            WHERE id_servico = ? AND ativo = 1
            """,
            (id_servico,),
        ).fetchone()
    finally:
        conexao.close()

    if servico is None:
        return redirect(url_for("consultar_disponibilidade"))

    disponiveis = calcular_horarios_disponiveis(id_servico, data_texto)

    if hora not in disponiveis:
        return redirect(
            url_for(
                "consultar_disponibilidade",
                servico=id_servico,
                data=data_texto,
            )
        )

    token = session.get("csrf_agendamento")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_agendamento"] = token

    erro = None

    if request.method == "POST":
        token_recebido = request.form.get("csrf_token", "")

        if not secrets.compare_digest(token, token_recebido):
            return "Formulário inválido.", 400

        try:
            codigo = registrar_agendamento(
                id_servico,
                data_texto,
                hora,
                request.form.get("nome", ""),
                request.form.get("telefone", ""),
            )
            return redirect(url_for("agendamento_confirmado", codigo=codigo))

        except ValueError as excecao:
            erro = str(excecao)

    return render_template(
        "agendar.html",
        servico=servico,
        data=data_texto,
        hora=hora,
        erro=erro,
        csrf_token=token,
    )


# Exibir comprovante do agendamento
@app.route("/agendamento/confirmado/<codigo>")
def agendamento_confirmado(codigo):
    conexao = conectar()

    try:
        agendamento = conexao.execute(
            """
            SELECT
                s.nome, a.data, a.hora, a.codigo_atendimento
            FROM agendamento AS a
            JOIN servico AS s
              ON s.id_servico = a.id_servico
            WHERE a.codigo_atendimento = ?
            """,
            (codigo,),
        ).fetchone()
    finally:
        conexao.close()

    if agendamento is None:
        return "Agendamento não encontrado.", 404

    return render_template(
        "agendamento_confirmado.html",
        agendamento=agendamento,
    )


# Consultar agendamento pelo telefone e codigo
@app.route("/consultar-agendamento", methods=["GET", "POST"])
def consultar_agendamento():
    import re

    erro = None
    agendamento = None

    token = session.get("csrf_consulta")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_consulta"] = token

    if request.method == "POST":
        token_recebido = request.form.get("csrf_token", "")
        codigo = request.form.get("codigo", "").strip().upper()
        telefone = re.sub(r"\D", "", request.form.get("telefone", ""))

        if not secrets.compare_digest(token, token_recebido):
            return "Formulário inválido.", 400

        if not re.fullmatch(r"[A-F0-9]{16}", codigo):
            erro = "Informe um código de atendimento válido."

        elif len(telefone) not in (10, 11):
            erro = "Informe um telefone válido com DDD."

        else:
            conexao = conectar()

            try:
                agendamento = conexao.execute(
                    """
                    SELECT
                        a.id_agendamento,
                        c.nome,
                        s.nome,
                        a.data,
                        a.hora,
                        a.status,
                        a.codigo_atendimento,
                        a.duracao_minutos,
                        a.preco_praticado
                    FROM agendamento AS a
                    JOIN cliente AS c
                      ON c.id_cliente = a.id_cliente
                    JOIN servico AS s
                      ON s.id_servico = a.id_servico
                    WHERE a.codigo_atendimento = ?
                      AND c.telefone = ?
                    """,
                    (codigo, telefone),
                ).fetchone()

            finally:
                conexao.close()

            if agendamento is None:
                erro = "Agendamento não encontrado. " "Confira o telefone e o código."

    return render_template(
        "consultar_agendamento.html",
        agendamento=agendamento,
        erro=erro,
        csrf_token=token,
    )


# Cancelar agendamento da cliente
@app.route("/agendamentos/cancelar", methods=["POST"])
def cancelar_agendamento():
    import re
    from datetime import datetime, timedelta

    from flask import flash

    token_esperado = session.get("csrf_consulta", "")
    token_recebido = request.form.get("csrf_token", "")

    if not token_esperado or not secrets.compare_digest(token_esperado, token_recebido):
        return "Formulário inválido.", 400

    codigo = request.form.get("codigo", "").strip().upper()
    telefone = re.sub(r"\D", "", request.form.get("telefone", ""))

    if not re.fullmatch(r"[A-F0-9]{16}", codigo) or len(telefone) not in (10, 11):
        flash("Dados do agendamento inválidos.", "danger")
        return redirect(url_for("consultar_agendamento"))

    conexao = conectar()

    try:
        # Bloqueia alterações concorrentes durante o cancelamento.
        conexao.execute("BEGIN IMMEDIATE")

        agendamento = conexao.execute(
            """
            SELECT a.id_agendamento, a.data, a.hora, a.status
            FROM agendamento AS a
            JOIN cliente AS c
              ON c.id_cliente = a.id_cliente
            WHERE a.codigo_atendimento = ?
              AND c.telefone = ?
            """,
            (codigo, telefone),
        ).fetchone()

        if agendamento is None:
            flash("Agendamento não encontrado.", "danger")

        elif agendamento[3] != "agendado":
            flash("Este agendamento não está ativo.", "danger")

        else:
            data_hora = datetime.strptime(
                f"{agendamento[1]} {agendamento[2]}",
                "%Y-%m-%d %H:%M",
            )

            antecedencia = data_hora - datetime.now()

            if antecedencia < timedelta(hours=4):
                flash(
                    "O cancelamento exige pelo menos 4 horas de antecedência.",
                    "danger",
                )
            else:
                cursor = conexao.execute(
                    """
                    UPDATE agendamento
                    SET status = 'cancelado'
                    WHERE id_agendamento = ?
                      AND status = 'agendado'
                    """,
                    (agendamento[0],),
                )

                if cursor.rowcount == 1:
                    conexao.commit()
                    flash(
                        "Agendamento cancelado com sucesso!",
                        "success",
                    )
                else:
                    flash("Não foi possível cancelar.", "danger")

    finally:
        conexao.close()

    return redirect(url_for("consultar_agendamento"))


# Reagendar atendimento pela cliente
@app.route("/reagendar", methods=["POST"])
def reagendar():
    import re
    from datetime import date, datetime, timedelta

    from flask import flash
    from agendamentos import reagendar_agendamento
    from disponibilidade import calcular_horarios_disponiveis

    token_esperado = session.get("csrf_consulta", "")
    token_recebido = request.form.get("csrf_token", "")

    if not token_esperado or not secrets.compare_digest(token_esperado, token_recebido):
        return "Formulário inválido.", 400

    codigo = request.form.get("codigo", "").strip().upper()
    telefone = re.sub(r"\D", "", request.form.get("telefone", ""))

    if not re.fullmatch(r"[A-F0-9]{16}", codigo) or len(telefone) not in (10, 11):
        flash("Dados de identificação inválidos.", "danger")
        return redirect(url_for("consultar_agendamento"))

    conexao = conectar()

    try:
        agendamento = conexao.execute(
            """
            SELECT
                a.id_agendamento,
                a.id_servico,
                a.data,
                a.hora,
                a.status,
                a.duracao_minutos,
                s.nome
            FROM agendamento AS a
            JOIN cliente AS c
              ON c.id_cliente = a.id_cliente
            JOIN servico AS s
              ON s.id_servico = a.id_servico
            WHERE a.codigo_atendimento = ?
              AND c.telefone = ?
            """,
            (codigo, telefone),
        ).fetchone()

    finally:
        conexao.close()

    if agendamento is None:
        flash("Agendamento não encontrado.", "danger")
        return redirect(url_for("consultar_agendamento"))

    if agendamento[4] != "agendado":
        flash("Este agendamento não está ativo.", "danger")
        return redirect(url_for("consultar_agendamento"))

    data_hora_atual = datetime.strptime(
        f"{agendamento[2]} {agendamento[3]}",
        "%Y-%m-%d %H:%M",
    )

    if data_hora_atual < datetime.now() + timedelta(hours=4):
        flash(
            "O reagendamento exige pelo menos 4 horas de antecedência.",
            "danger",
        )
        return redirect(url_for("consultar_agendamento"))

    acao = request.form.get("acao", "abrir")
    data_nova = request.form.get("data_nova", "")
    hora_nova = request.form.get("hora_nova", "")

    erro = None
    horarios = None

    if acao not in ("abrir", "consultar", "confirmar"):
        return "Ação inválida.", 400

    if acao in ("consultar", "confirmar"):
        try:
            data_escolhida = date.fromisoformat(data_nova)

            if data_escolhida.isoformat() != data_nova or data_escolhida < date.today():
                raise ValueError

        except ValueError:
            erro = "Selecione uma data válida e futura."

        if erro is None:
            if acao == "confirmar":
                try:
                    reagendar_agendamento(
                        agendamento[0],
                        data_nova,
                        hora_nova,
                    )

                except ValueError as excecao:
                    erro = str(excecao)

                else:
                    return redirect(
                        url_for(
                            "agendamento_confirmado",
                            codigo=codigo,
                        )
                    )

            horarios = calcular_horarios_disponiveis(
                agendamento[1],
                data_nova,
                id_agendamento_ignorar=agendamento[0],
                duracao_override=agendamento[5],
            )

    return render_template(
        "reagendar.html",
        agendamento=agendamento,
        codigo=codigo,
        telefone=telefone,
        data_nova=data_nova,
        hora_nova=hora_nova,
        data_minima=date.today().isoformat(),
        horarios=horarios,
        erro=erro,
        csrf_token=token_esperado,
    )


if __name__ == "__main__":
    app.run(debug=True)
