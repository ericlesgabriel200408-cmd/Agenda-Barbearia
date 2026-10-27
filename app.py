from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, date, time

app = Flask(__name__)
app.secret_key = "chave_secreta_barbearia_classe_a"

STORE_INFO = {
    "name": "Barbearia Classe A",
    "address": "Atendimento com Horário Agendado",
    "phone": "(11) 99999-9999",
    "hours": {
        "Segunda - Sexta": "09:00 - 19:00",
        "Sábado": "09:00 - 17:00",
        "Domingo": "Fechado"
    }
}

SERVICES = [
    {"id": 1, "name": "Corte de Cabelo / Estilo", "duration": "45 min", "price": "R$ 50,00"},
    {"id": 2, "name": "Barba Completa", "duration": "30 min", "price": "R$ 35,00"},
    {"id": 3, "name": "Combo Corte + Barba", "duration": "1h 15min", "price": "R$ 75,00"},
    {"id": 4, "name": "Tratamento Capilar", "duration": "45 min", "price": "R$ 60,00"}
]

# Dados em memória
appointments_db = []
blocked_slots_db = []  # Armazena horários fechados manualmente pelo Admin [{'date': '2026-10-24', 'time': '10:00'}]

# Senha simples do Painel Admin
ADMIN_PASSWORD = "admin"

@app.route("/")
def index():
    return render_template("index.html", store=STORE_INFO, services=SERVICES)

@app.route("/admin")
def admin_page():
    if not session.get("is_admin"):
        return render_template("admin_login.html")
    return render_template("admin.html", store=STORE_INFO, appointments=appointments_db, blocked_slots=blocked_slots_db)

@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    if data.get("password") == ADMIN_PASSWORD:
        session["is_admin"] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Senha incorreta"}), 401

@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return jsonify({"success": True})

@app.route("/api/slots", methods=["GET"])
def get_slots():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Data não informada"}), 400

    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Formato de data inválido"}), 400

    today = date.today()
    now_time = datetime.now().time()

    weekday = selected_date.weekday() # 0: Seg ... 6: Dom
    if weekday == 6:
        return jsonify({"slots": [], "status": "closed", "message": "Fechado aos domingos"})

    start_hour, end_hour = (9, 17) if weekday == 5 else (9, 19)

    # Buscar horários já reservados ou bloqueados
    booked_times = [a["time"] for a in appointments_db if a["date"] == date_str]
    blocked_times = [b["time"] for b in blocked_slots_db if b["date"] == date_str]

    slots = []
    for hour in range(start_hour, end_hour):
        for minute in (0, 30):
            slot_time_str = f"{hour:02d}:{minute:02d}"
            slot_time_obj = time(hour, minute)

            is_available = True
            reason = "disponivel"

            # 1. Regra: Se a data for HOJE e o horário já passou
            if selected_date == today and slot_time_obj <= now_time:
                is_available = False
                reason = "passado"
            # 2. Regra: Se a data já for do passado
            elif selected_date < today:
                is_available = False
                reason = "passado"
            # 3. Regra: Se já está agendado
            elif slot_time_str in booked_times:
                is_available = False
                reason = "reservado"
            # 4. Regra: Se foi bloqueado pelo Admin
            elif slot_time_str in blocked_times:
                is_available = False
                reason = "bloqueado"

            slots.append({
                "time": slot_time_str,
                "available": is_available,
                "reason": reason
            })

    return jsonify({"slots": slots, "status": "open"})

@app.route("/api/book", methods=["POST"])
def book_appointment():
    data = request.json or {}
    required = ["service_id", "date", "time", "client_name", "client_phone"]

    if not all(k in data and data[k] for k in required):
        return jsonify({"success": False, "error": "Preencha todos os campos obrigatórios."}), 400

    date_str = data["date"]
    time_str = data["time"]

    # Validar se o horário já passou
    selected_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    if selected_dt <= datetime.now():
        return jsonify({"success": False, "error": "Este horário já passou. Escolha um horário futuro."}), 400

    # Validar se já está ocupado ou bloqueado
    if any(a["date"] == date_str and a["time"] == time_str for a in appointments_db):
        return jsonify({"success": False, "error": "Este horário já foi agendado por outro cliente."}), 400

    if any(b["date"] == date_str and b["time"] == time_str for b in blocked_slots_db):
        return jsonify({"success": False, "error": "Este horário foi fechado pelo estabelecimento."}), 400

    service = next((s for s in SERVICES if str(s["id"]) == str(data["service_id"])), None)
    if not service:
        return jsonify({"success": False, "error": "Serviço inválido."}), 400

    new_app = {
        "id": len(appointments_db) + 1,
        "service": service["name"],
        "price": service["price"],
        "date": date_str,
        "time": time_str,
        "client_name": data["client_name"],
        "client_phone": data["client_phone"]
    }

    appointments_db.append(new_app)
    return jsonify({"success": True, "appointment": new_app})

# ROTA ADMIN: Cancelar/Remover Agendamento
@app.route("/admin/cancel", methods=["POST"])
def admin_cancel():
    if not session.get("is_admin"):
        return jsonify({"success": False, "error": "Não autorizado"}), 403

    app_id = request.json.get("id")
    global appointments_db
    appointments_db = [a for a in appointments_db if str(a["id"]) != str(app_id)]
    return jsonify({"success": True})

# ROTA ADMIN: Bloquear/Desbloquear Horário
@app.route("/admin/toggle-block", methods=["POST"])
def admin_toggle_block():
    if not session.get("is_admin"):
        return jsonify({"success": False, "error": "Não autorizado"}), 403

    data = request.json or {}
    date_str = data.get("date")
    time_str = data.get("time")

    if not date_str or not time_str:
        return jsonify({"success": False, "error": "Dados incompletos"}), 400

    existing = next((b for b in blocked_slots_db if b["date"] == date_str and b["time"] == time_str), None)

    if existing:
        blocked_slots_db.remove(existing)
        return jsonify({"success": True, "blocked": False})
    else:
        blocked_slots_db.append({"date": date_str, "time": time_str})
        return jsonify({"success": True, "blocked": True})

if __name__ == "__main__":
    app.run(debug=True)