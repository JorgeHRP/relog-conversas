from flask import Flask, render_template, request, redirect, url_for, session, send_file
from dotenv import load_dotenv
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os, requests
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.units import cm
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
    """Obtém a lista de usuários do webhook configurado no .env"""
    try:
        payload = {"acao": "usuarios"}

        r = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=10
        )

        if r.status_code != 200:
            return []

        data = r.json()
        usuarios = []

        for item in data:
            nome = item.get("firt_name") or item.get("first_name") or "Sem nome"
            sobrenome = item.get("last_name") or ""
            nome_completo = f"{nome} {sobrenome}".strip()

            usuarios.append({
                "id": str(item.get("id", "")),
                "nome": str(nome_completo),
                "phone": str(item.get("phone", ""))
            })

        return usuarios

    except Exception:
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
        conversas_raw = get_conversas(conversa_id)
        # Filtra mensagens do chat específico
        msgs = [m for m in conversas_raw if str(m.get("chat")) == str(conversa_id)]

        usuario = next((u for u in usuarios if str(u["id"]) == str(conversa_id)), None)
        nome = usuario["nome"] if usuario else f"Usuário {conversa_id}"

        conversa = {
            "id": conversa_id,
            "nome": nome,
            "messages": msgs  # 🔹 Agora envia a mensagem completa com sender, text, date
        }

    return render_template("conversas.html", conversas=usuarios, conversa=conversa)

@app.route("/exportar_pdf/<conversa_id>")
def exportar_pdf(conversa_id):
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    import textwrap
    from datetime import datetime
    import requests

    # ===== BUSCA DE DADOS =====
    conversas_raw = get_conversas(conversa_id)
    msgs = [m for m in conversas_raw if str(m.get("chat")) == str(conversa_id)]

    usuarios = session.get("usuarios") or get_usuarios()
    usuario = next((u for u in usuarios if str(u["id"]) == str(conversa_id)), None)

    # Buscar informações completas do usuário
    user_info = {
        "username": "",
        "id": conversa_id,
        "first_name": "",
        "last_name": "",
        "phone": ""
    }
    try:
        payload = {"acao": "usuarios"}
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            all_users = resp.json()
            user_data = next((u for u in all_users if str(u.get("id")) == str(conversa_id)), None)
            if user_data:
                user_info = {
                    "username": user_data.get("username", ""),
                    "id": str(user_data.get("id", conversa_id)),
                    "first_name": user_data.get("firt_name") or user_data.get("first_name", ""),
                    "last_name": user_data.get("last_name", ""),
                    "phone": user_data.get("phone", "")
                }
    except Exception:
        pass

    # Fallback com dados básicos
    if not user_info.get("first_name") and usuario:
        user_info["first_name"] = usuario.get("nome", "")
        user_info["phone"] = usuario.get("phone", "")

    nome_completo = f"{user_info['first_name']} {user_info['last_name']}".strip() or f"Usuário {conversa_id}"

    # ===== CRIAÇÃO DO PDF =====
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4
    margem = 1.5 * cm
    y = altura - 1.5 * cm

    # ===== CABEÇALHO =====
    pdf.setFillColor(colors.HexColor("#0088cc"))
    pdf.rect(0, altura - 3*cm, largura, 3*cm, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margem, altura - 2*cm, nome_completo)

    y = altura - 3.8 * cm

    # ===== INFORMAÇÕES DO CONTATO =====
    def format_info(value):
        return str(value).strip() if value else "Não informado / Privado"

    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(colors.black)
    pdf.drawString(margem, y, "INFORMAÇÕES DO CONTATO")
    y -= 18
    pdf.setFont("Helvetica", 9)

    pdf.drawString(margem, y, f"Username: @{user_info['username']}" if user_info['username'] else "Username: Não informado / Privado")
    y -= 13
    pdf.drawString(margem, y, f"ID: {user_info['id']}")
    y -= 13
    pdf.drawString(margem, y, f"Primeiro nome: {format_info(user_info['first_name'])}")
    y -= 13
    pdf.drawString(margem, y, f"Sobrenome: {format_info(user_info['last_name'])}")
    y -= 13
    pdf.drawString(margem, y, f"Telefone: {format_info(user_info['phone'])}")
    y -= 25

    # ===== INFORMAÇÕES DA EXPORTAÇÃO =====
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margem, y, "INFORMAÇÕES DA EXPORTAÇÃO")
    y -= 16
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margem, y, f"Exportado em: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}")
    y -= 13
    pdf.drawString(margem, y, f"Total de mensagens: {len(msgs)}")
    y -= 13
    if msgs:
        primeira = msgs[0].get("date", "")
        ultima = msgs[-1].get("date", "")
        pdf.drawString(margem, y, f"Período: {primeira} até {ultima}")
        y -= 20

    # ===== FUNDO =====
    pdf.setFillColor(colors.HexColor("#f4f4f5"))
    pdf.rect(0, 0, largura, y, fill=1, stroke=0)
    y -= 0.5 * cm
    pdf.setFont("Helvetica", 9)

    # ===== MENSAGENS =====
    for msg in msgs:
        sender_id = str(msg.get("sender"))
        text = msg.get("text", "").strip()
        data = msg.get("date", "")
        if not text:
            continue

        is_operacao = sender_id == "2119777974"

        # Quebra de linha ajustada
        max_width_chars = 60
        linhas = textwrap.wrap(text, width=max_width_chars)
        altura_msg = 11 * len(linhas) + 20
        max_largura = 11.5 * cm
        largura_texto = max(pdf.stringWidth(l, "Helvetica", 9) for l in linhas)
        largura_necessaria = min(largura_texto + 0.8 * cm, max_largura)

        # Nova página se necessário
        if y - altura_msg < 2.5 * cm:
            pdf.setFont("Helvetica-Oblique", 8)
            pdf.setFillColor(colors.grey)
            pdf.drawCentredString(largura / 2, 1.5 * cm, f"Página {pdf.getPageNumber()}")
            pdf.showPage()
            pdf.setFillColor(colors.HexColor("#f4f4f5"))
            pdf.rect(0, 0, largura, altura, fill=1, stroke=0)
            y = altura - 2 * cm
            pdf.setFont("Helvetica", 9)

        # Lado e cor
        if is_operacao:
            balao_x = largura - margem - largura_necessaria
            cor_balao = colors.HexColor("#dcf8c6")
        else:
            balao_x = margem
            cor_balao = colors.white

        # Balão
        pdf.setFillColor(cor_balao)
        pdf.setStrokeColor(colors.HexColor("#d1d1d1"))
        pdf.setLineWidth(0.3)
        pdf.roundRect(
            balao_x, y - altura_msg + 10,
            largura_necessaria, altura_msg - 10, 5, fill=1, stroke=1
        )

        # Texto
        y_texto = y - 17
        pdf.setFillColor(colors.black)
        for linha in linhas:
            pdf.drawString(balao_x + 0.35 * cm, y_texto, linha)
            y_texto -= 10.5

        # Data — lado oposto ao remetente
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(colors.HexColor("#777777"))
        hora_texto = f"{data} ✓✓" if is_operacao else data

        if is_operacao:
            # Alinhado à direita
            pdf.drawRightString(balao_x + largura_necessaria, y - altura_msg + 5, hora_texto)
        else:
            # Alinhado à esquerda
            pdf.drawString(balao_x, y - altura_msg + 5, hora_texto)

        y -= altura_msg + 8
        pdf.setFont("Helvetica", 9)

    # ===== RODAPÉ =====
    pdf.setFont("Helvetica-Oblique", 7)
    pdf.setFillColor(colors.grey)
    pdf.drawCentredString(
        largura / 2, 1.2 * cm,
        f"Página {pdf.getPageNumber()} - Documento gerado automaticamente pelo sistema"
    )

    pdf.save()
    buffer.seek(0)

    data_arquivo = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Conversa_Telegram_{conversa_id}_{data_arquivo}.pdf",
        mimetype="application/pdf",
    )



    
@app.route("/atualizar_usuarios")
def atualizar_usuarios():
    if "user" not in session:
        return redirect(url_for("login"))

    usuarios = get_usuarios()  # força atualização
    session["usuarios"] = usuarios  # salva na sessão

    return redirect(url_for("conversas"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)