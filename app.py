import os
import secrets
import sqlite3
from functools import wraps
from notificacoes import registrar_notificacao
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import conectar, concluir_agendamentos_vencidos

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


@app.before_request
def sincronizar_conclusoes():
    # Antes das consultas e alterações, persiste os status atualizados no SQLite.
    # Ignora arquivos estáticos, sem comprometer o carregamento do visual.
    if request.endpoint != "static":
        concluir_agendamentos_vencidos()


@app.route("/")
def inicio():
    return render_template("index.html")


# UC09 - Cadastro da profissional
@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    import re
    from database import atualizar_cadastro_profissional
    from recuperacao import email_valido

    erro = sucesso = None
    token = session.setdefault("csrf_cadastro", secrets.token_urlsafe(32))
    conexao = conectar()
    try:
        atualizar_cadastro_profissional(conexao)
        # A tela permanece acessível, mas apenas a primeira conta pode ser criada.
        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            email = request.form.get("email", "").strip().lower()
            whatsapp = re.sub(r"\D", "", request.form.get("whatsapp", ""))
            senha = request.form.get("senha", "")
            confirmar_senha = request.form.get("confirmar_senha", "")
            if not secrets.compare_digest(token, request.form.get("csrf_token", "")):
                erro = "Formulário inválido. Atualize a página e tente novamente."
            elif not nome or len(nome) > 100:
                erro = "Informe seu nome completo, com até 100 caracteres."
            elif not email_valido(email):
                erro = "Informe um e-mail válido."
            elif len(whatsapp) not in (10, 11):
                erro = "Informe o WhatsApp com DDD, usando 10 ou 11 dígitos."
            elif not 8 <= len(senha) <= 128:
                erro = "A senha deve possuir entre 8 e 128 caracteres."
            elif senha != confirmar_senha:
                erro = "As senhas informadas não coincidem."
            else:
                # O campo login armazena o e-mail nas novas contas.
                # Contas antigas continuam aceitando seu login original.
                try:
                    conexao.execute("BEGIN IMMEDIATE")
                    # Verificação dentro da transação: impede duas contas criadas
                    # simultaneamente por requisições concorrentes.
                    existente = conexao.execute(
                        "SELECT 1 FROM profissional LIMIT 1"
                    ).fetchone()
                    if existente:
                        conexao.rollback()
                        erro = "Já existe um profissional cadastrado."
                    else:
                        conexao.execute(
                            "INSERT INTO profissional (nome, login, senha_hash, whatsapp) VALUES (?, ?, ?, ?)",
                            (nome, email, generate_password_hash(senha), whatsapp),
                        )
                        conexao.commit()
                        sucesso = "Conta criada com sucesso! Entre com seu e-mail e senha."
                except sqlite3.IntegrityError:
                    conexao.rollback()
                    erro = "Não foi possível criar a conta com este e-mail."
    finally:
        conexao.close()
    return render_template("cadastro.html", erro=erro, sucesso=sucesso, csrf_token=token)


# UC10 - Realizar Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if "id_profissional" in session:
        return redirect(url_for("painel"))

    erro = None

    if request.method == "POST":
        login_informado = request.form.get("login", "").strip()
        if "@" in login_informado:
            login_informado = login_informado.lower()
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


@app.route("/esqueci-minha-senha", methods=["GET", "POST"])
def esqueci_minha_senha():
    import time
    import smtplib
    from recuperacao import email_valido, configuracao_email, gerar_token, enviar_recuperacao

    token = session.setdefault("csrf_recuperacao", secrets.token_urlsafe(32))
    erro = sucesso = None
    status = 200
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        config = configuracao_email()
        if not secrets.compare_digest(token, request.form.get("csrf_token", "")):
            erro, status = "Formulário inválido. Atualize a página.", 400
        elif not email_valido(email):
            erro = "Informe um e-mail válido."
        elif config is None:
            erro, status = "A recuperação por e-mail está temporariamente indisponível. Tente novamente mais tarde.", 503
        elif time.time() - session.get("ultima_recuperacao", 0) < 60:
            erro, status = "Aguarde um minuto antes de solicitar outro link.", 429
        else:
            session["ultima_recuperacao"] = time.time()
            conexao = conectar()
            try:
                profissional = conexao.execute(
                    "SELECT id_profissional, senha_hash, login FROM profissional WHERE lower(login) = ?",
                    (email,),
                ).fetchone()
            finally:
                conexao.close()
            sucesso = "Se este e-mail estiver cadastrado, você receberá um link para redefinir sua senha. Confira também o spam."
            if profissional:
                try:
                    enviar_recuperacao(profissional[2], url_for("redefinir_senha", token=gerar_token(profissional)), config)
                except (OSError, smtplib.SMTPException):
                    # Não expõe conta, token ou credenciais na resposta/log.
                    app.logger.error("Falha no envio de recuperação por SMTP.")
    resposta = app.make_response((render_template("esqueci_senha.html", erro=erro, sucesso=sucesso, csrf_token=token), status))
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    from itsdangerous import BadSignature, SignatureExpired
    from recuperacao import serializador, assinatura_senha

    erro = None
    valido = False
    sucesso = False
    csrf = session.setdefault("csrf_redefinicao", secrets.token_urlsafe(32))
    conexao = conectar()
    try:
        try:
            dados = serializador().loads(token, max_age=1800)
            profissional = conexao.execute(
                "SELECT id_profissional, senha_hash FROM profissional WHERE id_profissional = ?",
                (dados["id"],),
            ).fetchone()
            valido = bool(profissional and secrets.compare_digest(dados["senha"], assinatura_senha(profissional[1])))
        except (BadSignature, SignatureExpired, KeyError, TypeError):
            valido = False
        if not valido:
            erro = "Este link é inválido, expirou ou já foi utilizado. Solicite um novo link."
        elif request.method == "POST":
            senha = request.form.get("senha", "")
            if not secrets.compare_digest(csrf, request.form.get("csrf_token", "")):
                erro = "Formulário inválido. Atualize a página."
            elif not 8 <= len(senha) <= 128:
                erro = "A senha deve possuir entre 8 e 128 caracteres."
            elif senha != request.form.get("confirmar_senha", ""):
                erro = "As senhas informadas não coincidem."
            else:
                resultado = conexao.execute(
                    "UPDATE profissional SET senha_hash = ? WHERE id_profissional = ? AND senha_hash = ?",
                    (generate_password_hash(senha), profissional[0], profissional[1]),
                )
                conexao.commit()
                if resultado.rowcount == 1:
                    session.clear()
                    sucesso = True
                else:
                    valido = False
                    erro = "Este link já foi utilizado. Solicite um novo link."
    finally:
        conexao.close()
    resposta = app.make_response(render_template("redefinir_senha.html", erro=erro, valido=valido, sucesso=sucesso, csrf_token=csrf))
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


# Painel administrativo protegido
@app.route("/painel")
@login_obrigatorio
def painel():
    from datetime import date, timedelta

    erro = None
    try:
        dia = date.fromisoformat(request.args.get("data", date.today().isoformat()))
    except ValueError:
        dia = date.today()
        erro = "Data inválida. Exibindo a agenda de hoje."
    conexao = conectar()
    try:
        atendimentos = conexao.execute(
            """SELECT a.hora, c.nome, s.nome, a.status, a.duracao_minutos
               FROM agendamento a JOIN cliente c ON c.id_cliente = a.id_cliente
               JOIN servico s ON s.id_servico = a.id_servico
               WHERE s.id_profissional = ? AND a.data = ? ORDER BY a.hora""",
            (session["id_profissional"], dia.isoformat()),
        ).fetchall()
        avisos = conexao.execute(
            """SELECT n.tipo, c.nome, a.data, a.hora FROM notificacao n
               JOIN agendamento a ON a.id_agendamento = n.id_agendamento
               JOIN cliente c ON c.id_cliente = a.id_cliente
               JOIN servico s ON s.id_servico = a.id_servico
               WHERE s.id_profissional = ? AND n.visualizada = 0
               ORDER BY n.id_notificacao DESC LIMIT 3""",
            (session["id_profissional"],),
        ).fetchall()
        servicos_ativos = conexao.execute(
            "SELECT COUNT(*) FROM servico WHERE id_profissional = ? AND ativo = 1",
            (session["id_profissional"],),
        ).fetchone()[0]
        periodos = conexao.execute(
            "SELECT COUNT(*) FROM horario_atendimento WHERE id_profissional = ?",
            (session["id_profissional"],),
        ).fetchone()[0]
        estabelecimento = conexao.execute(
            "SELECT nome_empresa, cidade FROM profissional WHERE id_profissional = ?",
            (session["id_profissional"],),
        ).fetchone()
    finally:
        conexao.close()
    totais = {status: sum(a[3] == status for a in atendimentos)
              for status in ("agendado", "concluido", "cancelado", "falta")}
    return render_template(
        "painel.html", nome=session["nome_profissional"], atendimentos=atendimentos,
        totais=totais, avisos=avisos, dia=dia, erro=erro,
        anterior=(dia - timedelta(days=1)).isoformat() if dia > date.min else None,
        proximo=(dia + timedelta(days=1)).isoformat() if dia < date.max else None,
        servicos_ativos=servicos_ativos, periodos=periodos,
        estabelecimento_configurado=bool(estabelecimento and estabelecimento[0].strip() and estabelecimento[1].strip()),
    )


# Configuração dos dados do estabelecimento
@app.route("/estabelecimento", methods=["GET", "POST"])
@login_obrigatorio
def configurar_estabelecimento():
    import re
    from database import atualizar_cadastro_profissional

    erro = sucesso = None
    token = session.setdefault("csrf_estabelecimento", secrets.token_urlsafe(32))
    conexao = conectar()
    try:
        atualizar_cadastro_profissional(conexao)
        campos = ("nome_empresa", "logradouro", "numero", "complemento", "bairro", "cep", "cidade")
        registro = conexao.execute(
            "SELECT " + ", ".join(campos) + " FROM profissional WHERE id_profissional = ?",
            (session["id_profissional"],),
        ).fetchone()
        if registro is None:
            return redirect(url_for("login"))
        dados = dict(zip(campos, registro))
        if request.method == "POST":
            dados = {campo: request.form.get(campo, "").strip() for campo in campos}
            dados["cep"] = re.sub(r"\\D", "", dados["cep"])
            if not secrets.compare_digest(token, request.form.get("csrf_token", "")):
                erro = "Formulário inválido. Atualize a página e tente novamente."
            elif any(not dados[campo] for campo in ("nome_empresa", "logradouro", "numero", "bairro", "cep", "cidade")):
                erro = "Preencha todos os campos obrigatórios."
            elif len(dados["cep"]) != 8:
                erro = "Informe um CEP válido com 8 dígitos."
            elif any(len(valor) > (150 if campo == "complemento" else 100) for campo, valor in dados.items()):
                erro = "Um dos campos ultrapassou o limite de caracteres."
            else:
                conexao.execute(
                    "UPDATE profissional SET " + ", ".join(campo + " = ?" for campo in campos)
                    + " WHERE id_profissional = ?",
                    (*[dados[campo] for campo in campos], session["id_profissional"]),
                )
                conexao.commit()
                sucesso = "Dados do estabelecimento salvos com sucesso."
    finally:
        conexao.close()
    return render_template("estabelecimento.html", dados=dados, erro=erro, sucesso=sucesso, csrf_token=token)


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
        estabelecimento = conexao.execute("""
            SELECT nome_empresa, cidade, whatsapp
            FROM profissional
            WHERE trim(nome_empresa) != '' AND trim(cidade) != ''
            ORDER BY id_profissional LIMIT 1
        """).fetchone()
    finally:
        conexao.close()

    if request.args:
        if not servico_texto.isdigit():
            erro = "Selecione um serviço válido."

        elif not any(servico[0] == int(servico_texto) for servico in servicos):
            erro = "O serviço selecionado não está disponível."

        elif not data_texto:
            # Serviço escolhido: exibe o calendário antes de consultar horários.
            pass

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
        estabelecimento=estabelecimento,
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
                s.nome, a.data, a.hora, a.codigo_atendimento,
                s.duracao, a.preco_praticado, c.nome, c.telefone
            FROM agendamento AS a
            JOIN servico AS s
              ON s.id_servico = a.id_servico
            JOIN cliente AS c
              ON c.id_cliente = a.id_cliente
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



# Tela demonstrativa de recuperação de código (MVP, sem integração externa).
@app.route("/esqueci-meu-codigo", methods=["GET", "POST"])
def esqueci_meu_codigo():
    import re

    token = session.setdefault("csrf_esqueci_codigo", secrets.token_urlsafe(32))
    erro = aviso = None
    status = 200
    if request.method == "POST":
        telefone = re.sub(r"\\D", "", request.form.get("telefone", ""))
        if not secrets.compare_digest(token, request.form.get("csrf_token", "")):
            erro, status = "Formulário inválido. Atualize a página.", 400
        elif len(telefone) not in (10, 11):
            erro, status = "Informe um WhatsApp válido com DDD.", 400
        else:
            aviso = "Esta é uma demonstração do MVP. O envio automático pelo WhatsApp não está habilitado."
    resposta = app.make_response((
        render_template("esqueci_codigo.html", erro=erro, aviso=aviso, csrf_token=token),
        status,
    ))
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


# Cancelar agendamento da cliente
@app.route("/agendamentos/cancelar", methods=["POST"])
def cancelar_agendamento():
    import re
    from datetime import datetime, timedelta

    from flask import flash
    from notificacoes import registrar_notificacao

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
                    registrar_notificacao(
                        conexao,
                        agendamento[0],
                        "cancelamento",
                    )

                    conexao.commit()

                    flash(
                        "Agendamento cancelado com sucesso!",
                        "success",
                    )

                else:
                    flash(
                        "Não foi possível cancelar.",
                        "danger",
                    )

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


# UC - Agenda administrativa da profissional
@app.route("/agenda")
@login_obrigatorio
def agenda_profissional():
    from datetime import date

    data_filtro = request.args.get("data", "").strip()
    status_filtro = request.args.get("status", "todos")

    status_validos = {"todos", "agendado", "cancelado", "concluido", "falta"}

    erro = None
    agendamentos = []

    if status_filtro not in status_validos:
        erro = "Situação de atendimento inválida."

    if data_filtro:
        try:
            data_validada = date.fromisoformat(data_filtro)

            if data_validada.isoformat() != data_filtro:
                raise ValueError

        except ValueError:
            erro = "Informe uma data válida."

    if erro is None:
        conexao = conectar()

        try:
            agendamentos = conexao.execute(
                """
                SELECT
                    a.id_agendamento,
                    a.data,
                    a.hora,
                    c.nome,
                    c.telefone,
                    s.nome,
                    a.duracao_minutos,
                    a.preco_praticado,
                    a.status
                FROM agendamento AS a
                JOIN cliente AS c
                    ON c.id_cliente = a.id_cliente
                JOIN servico AS s
                    ON s.id_servico = a.id_servico
                WHERE s.id_profissional = ?
                  AND (? = '' OR a.data = ?)
                  AND (? = 'todos' OR a.status = ?)
                ORDER BY a.data DESC, a.hora ASC
                """,
                (
                    session["id_profissional"],
                    data_filtro,
                    data_filtro,
                    status_filtro,
                    status_filtro,
                ),
            ).fetchall()

        finally:
            conexao.close()

    from datetime import datetime, timedelta

    token = session.get("csrf_agenda")

    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_agenda"] = token

    agora = datetime.now()

    finalizaveis = set()

    for atendimento in agendamentos:
        if atendimento[8] != "agendado":
            continue

        inicio = datetime.strptime(
            f"{atendimento[1]} {atendimento[2]}",
            "%Y-%m-%d %H:%M",
        )

        fim = inicio + timedelta(minutes=atendimento[6])

        if agora >= fim:
            finalizaveis.add(atendimento[0])

    return render_template(
        "agenda.html",
        agendamentos=agendamentos,
        data_filtro=data_filtro,
        status_filtro=status_filtro,
        erro=erro,
        csrf_token=token,
        finalizaveis=finalizaveis,
    )


# UC - Registrar conclusão ou falta no atendimento
@app.route("/agenda/<int:id_agendamento>/situacao", methods=["POST"])
@login_obrigatorio
def alterar_situacao_agendamento(id_agendamento):
    from datetime import datetime, timedelta
    from flask import flash

    token_esperado = session.get("csrf_agenda", "")
    token_recebido = request.form.get("csrf_token", "")

    if not token_esperado or not secrets.compare_digest(token_esperado, token_recebido):
        return "Formulário inválido.", 400

    nova_situacao = request.form.get("situacao", "")

    if nova_situacao not in ("concluido", "falta"):
        return "Situação inválida.", 400

    conexao = conectar()

    try:
        conexao.execute("BEGIN IMMEDIATE")

        agendamento = conexao.execute(
            """
            SELECT a.data, a.hora, a.duracao_minutos, a.status
            FROM agendamento AS a
            JOIN servico AS s
                ON s.id_servico = a.id_servico
            WHERE a.id_agendamento = ?
              AND s.id_profissional = ?
            """,
            (id_agendamento, session["id_profissional"]),
        ).fetchone()

        if agendamento is None:
            flash("Agendamento não encontrado.", "danger")

        elif agendamento[3] != "agendado":
            flash("Este agendamento não está ativo.", "danger")

        else:
            inicio = datetime.strptime(
                f"{agendamento[0]} {agendamento[1]}",
                "%Y-%m-%d %H:%M",
            )

            fim = inicio + timedelta(minutes=agendamento[2])

            if datetime.now() < fim:
                flash(
                    "Aguarde o término previsto do atendimento.",
                    "warning",
                )

            else:
                conexao.execute(
                    """
                    UPDATE agendamento
                    SET status = ?
                    WHERE id_agendamento = ?
                      AND status = 'agendado'
                    """,
                    (nova_situacao, id_agendamento),
                )

                registrar_notificacao(
                    conexao,
                    id_agendamento,
                    "conclusao" if nova_situacao == "concluido" else "falta",
                )

                conexao.commit()

                flash(
                    "Situação atualizada com sucesso!",
                    "success",
                )

    finally:
        conexao.close()

    return redirect(url_for("agenda_profissional"))


# UC - Consultar historico de atendimentos
@app.route("/historico")
@login_obrigatorio
def historico_atendimentos():
    from datetime import date

    data_filtro = request.args.get("data", "").strip()
    status_filtro = request.args.get("status", "todos")

    status_validos = {"todos", "concluido", "cancelado", "falta"}

    erro = None
    historico = []

    if status_filtro not in status_validos:
        erro = "Situação inválida."

    if data_filtro:
        try:
            data_validada = date.fromisoformat(data_filtro)

            if data_validada.isoformat() != data_filtro:
                raise ValueError

        except ValueError:
            erro = "Informe uma data válida."

    if erro is None:
        conexao = conectar()

        try:
            historico = conexao.execute(
                """
                SELECT
                    a.id_agendamento,
                    a.data,
                    a.hora,
                    c.nome,
                    c.telefone,
                    s.nome,
                    a.duracao_minutos,
                    a.preco_praticado,
                    a.status
                FROM agendamento AS a
                JOIN cliente AS c
                    ON c.id_cliente = a.id_cliente
                JOIN servico AS s
                    ON s.id_servico = a.id_servico
                WHERE s.id_profissional = ?
                  AND a.status IN (
                      'concluido', 'cancelado', 'falta'
                  )
                  AND (? = '' OR a.data = ?)
                  AND (? = 'todos' OR a.status = ?)
                ORDER BY a.data DESC, a.hora DESC
                """,
                (
                    session["id_profissional"],
                    data_filtro,
                    data_filtro,
                    status_filtro,
                    status_filtro,
                ),
            ).fetchall()

        finally:
            conexao.close()

    return render_template(
        "historico.html",
        historico=historico,
        data_filtro=data_filtro,
        status_filtro=status_filtro,
        erro=erro,
    )


# UC - Listar notificacoes da profissional
@app.route("/notificacoes")
@login_obrigatorio
def listar_notificacoes():
    token = session.get("csrf_notificacoes")

    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_notificacoes"] = token

    conexao = conectar()

    try:
        notificacoes = conexao.execute(
            """
            SELECT
                n.id_notificacao,
                n.tipo,
                n.data_hora,
                n.visualizada,
                c.nome,
                s.nome,
                a.data,
                a.hora
            FROM notificacao AS n
            JOIN agendamento AS a
                ON a.id_agendamento = n.id_agendamento
            JOIN cliente AS c
                ON c.id_cliente = a.id_cliente
            JOIN servico AS s
                ON s.id_servico = a.id_servico
            WHERE s.id_profissional = ?
            ORDER BY n.id_notificacao DESC
            LIMIT 100
            """,
            (session["id_profissional"],),
        ).fetchall()

        nao_lidas = conexao.execute(
            """
            SELECT COUNT(*)
            FROM notificacao AS n
            JOIN agendamento AS a
                ON a.id_agendamento = n.id_agendamento
            JOIN servico AS s
                ON s.id_servico = a.id_servico
            WHERE s.id_profissional = ?
              AND n.visualizada = 0
            """,
            (session["id_profissional"],),
        ).fetchone()[0]

    finally:
        conexao.close()

    return render_template(
        "notificacoes.html",
        notificacoes=notificacoes,
        nao_lidas=nao_lidas,
        csrf_token=token,
    )


# Marcar notificacao como lida
@app.route(
    "/notificacoes/<int:id_notificacao>/marcar-lida",
    methods=["POST"],
)
@login_obrigatorio
def marcar_notificacao_lida(id_notificacao):
    token_esperado = session.get("csrf_notificacoes", "")
    token_recebido = request.form.get("csrf_token", "")

    if not token_esperado or not secrets.compare_digest(token_esperado, token_recebido):
        return "Formulário inválido.", 400

    conexao = conectar()

    try:
        conexao.execute(
            """
            UPDATE notificacao
            SET visualizada = 1
            WHERE id_notificacao = ?
              AND id_agendamento IN (
                  SELECT a.id_agendamento
                  FROM agendamento AS a
                  JOIN servico AS s
                      ON s.id_servico = a.id_servico
                  WHERE s.id_profissional = ?
              )
            """,
            (id_notificacao, session["id_profissional"]),
        )

        conexao.commit()

    finally:
        conexao.close()

    return redirect(url_for("listar_notificacoes"))


if __name__ == "__main__":
    app.run(debug=False)

