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
    import hashlib
    
    conversas_raw = get_conversas(conversa_id)
    msgs = [m for m in conversas_raw if str(m.get("chat")) == str(conversa_id)]
    
    usuarios = session.get("usuarios") or get_usuarios()
    usuario = next((u for u in usuarios if str(u["id"]) == str(conversa_id)), None)
    
    # Busca informações completas do usuário
    user_info = {}
    if usuario:
        # Tenta buscar informações adicionais do webhook
        try:
            payload = {"acao": "usuarios"}
            resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            if resp.status_code == 200:
                all_users = resp.json()
                user_data = next((u for u in all_users if str(u.get("id")) == str(conversa_id)), None)
                if user_data:
                    user_info = {
                        "username": user_data.get("username", "Não disponível / Privado"),
                        "id": user_data.get("id", conversa_id),
                        "first_name": user_data.get("firt_name") or user_data.get("first_name", "Não disponível"),
                        "last_name": user_data.get("last_name", "Não disponível / Privado"),
                        "phone": user_data.get("phone", "Não disponível / Privado")
                    }
        except:
            pass
    
    # Se não conseguiu buscar, usa dados básicos
    if not user_info:
        user_info = {
            "username": "Não disponível / Privado",
            "id": conversa_id,
            "first_name": usuario["nome"] if usuario else "Não disponível",
            "last_name": "Não disponível / Privado",
            "phone": usuario.get("phone", "Não disponível / Privado") if usuario else "Não disponível / Privado"
        }
    
    nome_completo = f"{user_info['first_name']} {user_info['last_name']}".strip()
    if nome_completo == "Não disponível Não disponível / Privado":
        nome_completo = f"Usuário {conversa_id}"

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4
    margem = 1.5 * cm
    y = altura - 2 * cm

    # ========== CABEÇALHO ESTILO TELEGRAM ==========
    # Fundo azul do cabeçalho
    pdf.setFillColor(colors.HexColor("#0088cc"))
    pdf.rect(0, altura - 5*cm, largura, 5*cm, fill=1, stroke=0)
    
    # Título branco
    pdf.setFont("Helvetica-Bold", 20)
    pdf.setFillColor(colors.white)
    pdf.drawString(margem, y, "Exportação de Conversa")
    y -= 30
    
    # Informações do usuário em branco
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margem, y, "INFORMAÇÕES DO CONTATO")
    y -= 20
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margem, y, f"Nome: {user_info['first_name']}")
    y -= 15
    pdf.drawString(margem, y, f"Sobrenome: {user_info['last_name']}")
    y -= 15
    pdf.drawString(margem, y, f"Username: @{user_info['username']}" if user_info['username'] != "Não disponível / Privado" else f"Username: {user_info['username']}")
    y -= 15
    pdf.drawString(margem, y, f"Telefone: {user_info['phone']}")
    y -= 15
    pdf.drawString(margem, y, f"ID do Telegram: {user_info['id']}")
    y -= 25
    
    # Informações da exportação
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margem, y, "INFORMAÇÕES DA EXPORTAÇÃO")
    y -= 20
    
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margem, y, f"Data de Exportação: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}")
    y -= 15
    pdf.drawString(margem, y, f"Total de Mensagens: {len(msgs)}")
    y -= 15
    
    if msgs:
        primeira = msgs[0].get("date", "")
        ultima = msgs[-1].get("date", "")
        pdf.drawString(margem, y, f"Período: {primeira} até {ultima}")
        y -= 15
    
    # Hash de integridade
    conteudo_hash = "".join([m.get("text", "") for m in msgs])
    hash_doc = hashlib.sha256(conteudo_hash.encode()).hexdigest()[:16]
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(margem, y, f"Hash de Integridade: {hash_doc}")
    
    y -= 40

    # ========== MENSAGENS ESTILO TELEGRAM ==========
    pdf.setFont("Helvetica", 9)
    
    for msg in msgs:
        sender_id = str(msg.get("sender"))
        text = msg.get("text", "")
        data = msg.get("date", "")
        
        is_me = sender_id == "8222874193"
        
        # Quebra de linha automática (menor para caber nos balões)
        linhas = textwrap.wrap(text, width=55)
        altura_msg = 14 * len(linhas) + 30
        
        # Quebra de página se necessário
        if y - altura_msg < 3*cm:
            pdf.setFont("Helvetica-Oblique", 8)
            pdf.setFillColor(colors.grey)
            pdf.drawCentredString(largura/2, 1.5*cm, f"Página {pdf.getPageNumber()}")
            pdf.showPage()
            y = altura - 3*cm
            pdf.setFont("Helvetica", 9)
        
        # Posicionamento dos balões
        if is_me:
            # Mensagens enviadas (direita) - Verde claro estilo Telegram
            balao_x = largura - margem - 11*cm
            balao_largura = 10*cm
            cor_balao = colors.HexColor("#dcf8c6")
            cor_texto = colors.black
        else:
            # Mensagens recebidas (esquerda) - Branco
            balao_x = margem
            balao_largura = 10*cm
            cor_balao = colors.white
            cor_texto = colors.black
        
        # Desenha balão arredondado
        pdf.setFillColor(cor_balao)
        pdf.setStrokeColor(colors.HexColor("#e0e0e0"))
        pdf.setLineWidth(0.5)
        pdf.roundRect(balao_x, y - altura_msg + 10, balao_largura, altura_msg - 10, 8, fill=1, stroke=1)
        
        # Nome do remetente (apenas para mensagens recebidas)
        pdf.setFillColor(colors.HexColor("#0088cc"))
        pdf.setFont("Helvetica-Bold", 9)
        y_texto = y - 20
        
        if not is_me:
            pdf.drawString(balao_x + 10, y_texto, nome_completo)
            y_texto -= 15
        
        # Texto da mensagem
        pdf.setFillColor(cor_texto)
        pdf.setFont("Helvetica", 9)
        
        for linha in linhas:
            pdf.drawString(balao_x + 10, y_texto, linha)
            y_texto -= 14
        
        # Horário (canto inferior direito do balão)
        pdf.setFont("Helvetica-Oblique", 7)
        pdf.setFillColor(colors.grey)
        pdf.drawRightString(balao_x + balao_largura - 10, y - altura_msg + 15, data)
        
        y -= altura_msg + 8  # Espaço entre mensagens
    
    # ========== RODAPÉ ==========
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColor(colors.grey)
    pdf.drawCentredString(largura/2, 1.5*cm, f"Página {pdf.getPageNumber()}")
    pdf.drawString(margem, 1*cm, "Documento gerado automaticamente")
    pdf.drawRightString(largura - margem, 1*cm, f"Hash: {hash_doc}")
    
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