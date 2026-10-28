import os
import secrets
import sqlite3
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

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
            return render_template(
                "cadastro.html",
                cadastro_existente=True
            )

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
                        (nome, login_informado, senha_hash)
                    )
                    conexao.commit()
                    sucesso = "Cadastro realizado com sucesso!"

                except sqlite3.IntegrityError:
                    conexao.rollback()
                    erro = "Não foi possível realizar o cadastro. Verifique o login."

    finally:
        conexao.close()

    return render_template(
        "cadastro.html",
        erro=erro,
        sucesso=sucesso
    )


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
                (login_informado,)
            ).fetchone()
        finally:
            conexao.close()

        if profissional and check_password_hash(
            profissional[2], senha
        ):
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
    return render_template(
        "painel.html",
        nome=session["nome_profissional"]
    )


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
                        (
                            session["id_profissional"],
                            nome,
                            float(preco),
                            duracao
                        )
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
            (session["id_profissional"],)
        ).fetchall()
    finally:
        conexao.close()

    return render_template(
        "servicos.html",
        servicos=servicos,
        erro=erro,
        csrf_token=token
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
            (id_servico, session["id_profissional"])
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
                            session["id_profissional"]
                        )
                    )

                    conexao.commit()
                    return redirect(url_for("listar_servicos"))

                except (ValueError, InvalidOperation):
                    erro = "Informe um preço e uma duração válidos."

        return render_template(
            "editar_servico.html",
            servico=servico,
            erro=erro,
            csrf_token=token
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
    if (
        not token_esperado
        or not secrets.compare_digest(token_esperado, token_recebido)
    ):
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
            (id_servico, session["id_profissional"])
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
            (
                novo_status,
                id_servico,
                session["id_profissional"]
            )
        )

        conexao.commit()

    finally:
        conexao.close()

    return redirect(url_for("listar_servicos"))

if __name__ == "__main__":
    app.run(debug=True)