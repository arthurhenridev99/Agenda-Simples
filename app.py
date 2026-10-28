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


if __name__ == "__main__":
    app.run(debug=True)