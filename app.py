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
    conversas_raw = get_conversas(conversa_id)
    msgs = [m for m in conversas_raw if str(m.get("chat")) == str(conversa_id)]  # 🔹 CORRIGIDO: usar 'chat'
    
    usuarios = session.get("usuarios") or []
    usuario = next((u for u in usuarios if str(u["id"]) == str(conversa_id)), None)
    nome = usuario["nome"] if usuario else f"Usuário {conversa_id}"

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4
    margem = 2 * cm
    y = altura - 2.5 * cm

    # ========== CABEÇALHO JURÍDICO ==========
    # Logo/Título da empresa
    pdf.setFont("Helvetica-Bold", 18)
    pdf.setFillColor(colors.HexColor("#1a1a1a"))
    pdf.drawString(margem, y, "RELATÓRIO DE CONVERSAÇÃO")
    y -= 25
    
    # Linha decorativa
    pdf.setStrokeColor(colors.HexColor("#FFD500"))
    pdf.setLineWidth(2)
    pdf.line(margem, y, largura - margem, y)
    y -= 30

    # ========== INFORMAÇÕES DO DOCUMENTO ==========
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(colors.black)
    pdf.drawString(margem, y, "DADOS DA CONVERSA")
    y -= 18
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margem, y, f"Participante: {nome}")
    y -= 15
    pdf.drawString(margem, y, f"ID da Conversa: {conversa_id}")
    y -= 15
    pdf.drawString(margem, y, f"Data de Exportação: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}")
    y -= 15
    pdf.drawString(margem, y, f"Total de Mensagens: {len(msgs)}")
    y -= 15
    
    # Período da conversa
    if msgs:
        primeira = msgs[0].get("date", "")
        ultima = msgs[-1].get("date", "")
        pdf.drawString(margem, y, f"Período: {primeira} até {ultima}")
        y -= 20
    
    # Linha separadora
    pdf.setStrokeColor(colors.grey)
    pdf.setLineWidth(1)
    pdf.line(margem, y, largura - margem, y)
    y -= 25

    # ========== HASH/INTEGRIDADE (OPCIONAL MAS RECOMENDADO) ==========
    import hashlib
    conteudo_hash = "".join([m.get("text", "") for m in msgs])
    hash_doc = hashlib.sha256(conteudo_hash.encode()).hexdigest()[:16]
    
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColor(colors.grey)
    pdf.drawString(margem, y, f"Hash de Integridade: {hash_doc}")
    y -= 25

    # ========== MENSAGENS ==========
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(colors.black)
    pdf.drawString(margem, y, "HISTÓRICO DE MENSAGENS")
    y -= 20

    pdf.setFont("Helvetica", 10)
    msg_count = 1

    for msg in msgs:
        sender_id = str(msg.get("sender"))
        text = msg.get("text", "")
        data = msg.get("date", "")
        
        is_me = sender_id == "8222874193"  # 🔹 Seu número
        remetente = "Você" if is_me else nome

        # Quebra de linha automática
        linhas = textwrap.wrap(text, width=80)
        altura_msg = 15 * len(linhas) + 35

        # Quebra de página se necessário
        if y - altura_msg < 3*cm:
            # Rodapé da página
            pdf.setFont("Helvetica-Oblique", 8)
            pdf.setFillColor(colors.grey)
            pdf.drawCentredString(largura/2, 1.5*cm, f"Página {pdf.getPageNumber()}")
            
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = altura - 3*cm

        # Box da mensagem (mais formal)
        pdf.setStrokeColor(colors.HexColor("#e0e0e0"))
        pdf.setLineWidth(0.5)
        pdf.rect(margem, y - altura_msg, largura - 2*margem, altura_msg, stroke=1, fill=0)

        # Cabeçalho da mensagem
        pdf.setFont("Helvetica-Bold", 9)
        pdf.setFillColor(colors.HexColor("#1a1a1a"))
        pdf.drawString(margem + 10, y - 15, f"#{msg_count} - {remetente}")
        
        pdf.setFont("Helvetica-Oblique", 8)
        pdf.setFillColor(colors.grey)
        pdf.drawRightString(largura - margem - 10, y - 15, data)

        # Conteúdo da mensagem
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(colors.black)
        y_text = y - 30
        for linha in linhas:
            pdf.drawString(margem + 10, y_text, linha)
            y_text -= 14

        y -= altura_msg + 10
        msg_count += 1

    # ========== RODAPÉ FINAL ==========
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColor(colors.grey)
    pdf.drawCentredString(largura/2, 1.5*cm, f"Página {pdf.getPageNumber()}")
    pdf.drawString(margem, 1*cm, "Este documento foi gerado automaticamente pelo sistema.")
    pdf.drawRightString(largura - margem, 1*cm, f"Hash: {hash_doc}")
    
    pdf.save()
    buffer.seek(0)
    
    # Nome do arquivo mais formal
    data_arquivo = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Relatorio_Conversa_{conversa_id}_{data_arquivo}.pdf",
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
