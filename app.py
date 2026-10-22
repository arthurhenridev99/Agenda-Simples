from flask import Flask

app = Flask(__name__)

@app.route("/")
def inicio():
    return "<h1>Agendamento de Manicure e Pedicure</h1><p>Ambiente configurado com sucesso!</p>"

if __name__ == "__main__":
    app.run(debug=True)
