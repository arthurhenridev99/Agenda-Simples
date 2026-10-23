import sqlite3

from flask import Flask, render_template, request
from werkzeug.security import generate_password_hash

from database import conectar

app = Flask(__name__)


@app.route("/")
def inicio():
    return render_template("index.html")


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
            login = request.form.get("login", "").strip()
            senha = request.form.get("senha", "")
            confirmar_senha = request.form.get("confirmar_senha", "")

            if not nome or not login or not senha:
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
                        (nome, login, senha_hash)
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


if __name__ == "__main__":
    app.run(debug=True)