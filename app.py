from flask import Flask, render_template, request, redirect, url_for, session, send_file
from dotenv import load_dotenv
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os, requests
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import send_file
import textwrap

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

APP_USER = os.getenv("APP_USER")
APP_PASS = os.getenv("APP_PASS")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# ---------------------------------
# Funções auxiliares
# ---------------------------------
def get_usuarios():
    """Obtém e salva os usuários na sessão"""
    try:
        resp = requests.post(WEBHOOK_URL, json={"acao": "usuarios"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            usuarios = []
            for u in data:
                usuarios.append({
                    "id": str(u.get("id")),
                    "nome": (
                        u.get("firt_name") or u.get("first_name") or
                        u.get("username") or f"Usuário {u.get('id')}"
                    ),
                })
            session["usuarios"] = usuarios
            return usuarios
    except Exception as e:
        print("❌ Erro ao buscar usuários:", e)
    return []


def get_conversas(user_id=None):
    """Obtém conversas do webhook (para um usuário específico, se informado)"""
    try:
        payload = {"acao": "conversas"}
        if user_id:
            payload["id"] = user_id  # 🔹 agora envia o ID do usuário
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        print("❌ Erro ao buscar conversas:", e)
        return []


# ---------------------------------
# Rotas
# ---------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("usuario")
        senha = request.form.get("senha")

        if user == APP_USER and senha == APP_PASS:
            session["user"] = user
            get_usuarios()  # carrega usuários na sessão após login
            return redirect(url_for("conversas"))
        else:
            return render_template("login.html", erro="Usuário ou senha inválidos.")

    return render_template("login.html")


@app.route("/conversas")
def conversas():
    if "user" not in session:
        return redirect(url_for("login"))

    usuarios = session.get("usuarios") or get_usuarios()
    conversa_id = request.args.get("id")

    conversa = None
    if conversa_id:
        conversas_raw = get_conversas(conversa_id)  # 🔹 agora envia o ID do usuário
        msgs = [m for m in conversas_raw if str(m.get("id")) == str(conversa_id)]

        usuario = next((u for u in usuarios if str(u["id"]) == str(conversa_id)), None)
        nome = usuario["nome"] if usuario else f"Usuário {conversa_id}"

        conversa = {
            "id": conversa_id,
            "nome": nome,
            "messages": [
                {"human": m["text"], "system": ""} if str(m["sender"]) == str(conversa_id)
                else {"system": m["text"], "human": ""}
                for m in msgs
            ],
        }

    return render_template("conversas.html", conversas=usuarios, conversa=conversa)


@app.route("/exportar_pdf/<conversa_id>")
def exportar_pdf(conversa_id):
    conversas_raw = get_conversas(conversa_id)
    msgs = [m for m in conversas_raw if str(m.get("id")) == str(conversa_id)]

    usuarios = session.get("usuarios") or []
    usuario = next((u for u in usuarios if str(u["id"]) == str(conversa_id)), None)
    nome = usuario["nome"] if usuario else f"Usuário {conversa_id}"

    # Configuração inicial
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4
    margem = 2 * cm
    y = altura - 3 * cm

    # Cabeçalho
    pdf.setFont("Helvetica-Bold", 16)
    pdf.setFillColor(colors.HexColor("#3ca9f0"))
    pdf.drawString(margem, y, f"Histórico de conversa com {nome}")
    y -= 20
    pdf.setStrokeColor(colors.grey)
    pdf.line(margem, y, largura - margem, y)
    y -= 25

    pdf.setFont("Helvetica", 11)

    # Loop de mensagens
    for msg in msgs:
        sender_id = str(msg.get("sender"))
        text = msg.get("text", "")
        data = msg.get("date")

        # Data legível
        try:
            data_fmt = datetime.fromisoformat(data.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
        except:
            data_fmt = data or ""

        # Define remetente
        is_user = sender_id == str(conversa_id)

        # Cores e posição
        cor_fundo = colors.HexColor("#dcf8c6") if is_user else colors.whitesmoke
        x = largura - (margem + 9*cm) if is_user else margem
        max_largura = 9 * cm

        # Quebra de linha automática
        linhas = textwrap.wrap(text, width=45)
        altura_msg = 15 * len(linhas) + 20

        # Quebra de página se precisar
        if y - altura_msg < 3*cm:
            pdf.showPage()
            pdf.setFont("Helvetica", 11)
            y = altura - 3*cm

        # Fundo da mensagem
        pdf.setFillColor(cor_fundo)
        pdf.roundRect(x, y - altura_msg, max_largura, altura_msg, 8, fill=1, stroke=0)

        # Texto
        pdf.setFillColor(colors.black)
        y_text = y - 15
        for linha in linhas:
            pdf.drawString(x + 10, y_text, linha)
            y_text -= 14

        # Data da mensagem
        pdf.setFont("Helvetica-Oblique", 8)
        pdf.setFillColor(colors.grey)
        pdf.drawRightString(x + max_largura - 10, y - altura_msg + 5, data_fmt)
        pdf.setFont("Helvetica", 11)
        pdf.setFillColor(colors.black)

        # Espaçamento entre mensagens
        y -= altura_msg + 15

    # Rodapé
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.setFillColor(colors.grey)
    pdf.drawString(margem, 1.5*cm, f"Exportado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    pdf.save()

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{nome}_conversa.pdf",
        mimetype="application/pdf",
    )
    
@app.route("/atualizar_usuarios")
def atualizar_usuarios():
    if "user" not in session:
        return redirect(url_for("login"))
    get_usuarios()  # força atualização
    return redirect(url_for("conversas"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
