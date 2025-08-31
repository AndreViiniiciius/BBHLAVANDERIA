
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session, render_template_string
import sqlite3, os, csv, calendar
from datetime import date, timedelta, datetime
from io import StringIO, BytesIO
from werkzeug.security import generate_password_hash, check_password_hash

# PDF (Romaneio)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
except Exception:
    A4 = None

APP_TITLE = "BBH — Lavanderia PRO"

# Itens padrão para pré-preencher a tela de movimentações
DEFAULT_MOV_NAMES = [
    "COLCHA CASAL","COLCHA SOLTEIRO","CORTINA","FRONHA",
    "LENÇOL CASAL","LENÇOL SOLTEIRO","MANTA CASAL","MANTA SOLTEIRO",
    "PESEIRA CASAL","PESEIRA SOLTEIRO","PILLOW TOP","PISO",
    "PROTETOR CASAL","PROTETOR SOLTEIRO","PROTETOR TRAVESSEIRO",
    "REDE","ROLO","ROUPÃO","SAIOTE CASAL","SAIOTE SOLTEIRO",
    "TOALHA BANHO","TOALHA PISCINA","TOALHA ROSTO"
]

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "lavanderia.db")

# ------------- DB helpers -------------
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def row_get(row, key, default=None):
    try:
        return row[key]
    except Exception:
        return default

def init_db():
    conn = db_connect()
    c = conn.cursor()
    # Itens
    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            unit TEXT DEFAULT 'un',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Movimentações
    c.execute("""
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mov_date TEXT NOT NULL,
            mov_type TEXT NOT NULL CHECK(mov_type IN ('entrada','saida','envio','retorno','perda')),
            item_id INTEGER NOT NULL,
            qty REAL NOT NULL,
            ref TEXT,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(item_id) REFERENCES items(id)
        );
    """)
    # Usuários
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def migrate_db():
    """Garante schema compatível com versões anteriores."""
    conn = db_connect(); c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(users);")
        cols = [r[1] for r in c.fetchall()]
        if "active" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN active INTEGER DEFAULT 1;")
            conn.commit()
            c.execute("UPDATE users SET active=1 WHERE active IS NULL;")
            conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def migrate_data():
    """Normaliza dados existentes (tipos e índices)."""
    conn = db_connect(); c = conn.cursor()
    try:
        # Normaliza tipos para minúsculo e sem acentos comuns
        c.execute("UPDATE movements SET mov_type=LOWER(TRIM(mov_type)) WHERE mov_type IS NOT NULL;")
        # Corrige possíveis variações com acento
        c.execute("UPDATE movements SET mov_type='saida' WHERE mov_type IN ('saída');")
        # Garante só valores válidos (se houver algo estranho, mapeia para 'saida' para não quebrar)
        c.execute("UPDATE movements SET mov_type='saida' WHERE mov_type NOT IN ('entrada','saida','envio','retorno','perda');")
        # Índices para desempenho e filtros por data/tipo
        c.execute("CREATE INDEX IF NOT EXISTS idx_mov_date ON movements(mov_date);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mov_type ON movements(mov_type);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mov_item ON movements(item_id);")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
def preload_items():
    # Garante itens padrão
    conn = db_connect(); c = conn.cursor()
    for name in DEFAULT_MOV_NAMES:
        c.execute("INSERT OR IGNORE INTO items(name) VALUES (?);", (name,))
    # Também garante alguns itens extras usados antes
    extras = ["TRAVESSEIRO","VIP COLCHA","VIP FRONHA","VIP LENÇOL","BLACK OUT"]
    for name in extras:
        c.execute("INSERT OR IGNORE INTO items(name) VALUES (?);", (name,))
    conn.commit(); conn.close()

def create_default_user():
    conn = db_connect(); c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users(username,password,active) VALUES (?,?,1)", ("admin", generate_password_hash("1234")))
        conn.commit()
    conn.close()

def bootstrap():
    init_db()
    migrate_db()
    migrate_data()
    preload_items()
    create_default_user()

bootstrap()

# ------------- Utils -------------
def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("username") != "admin":
            flash("Acesso restrito ao administrador.", "error")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper

def parse_period(period:str, ref_str:str):
    try:
        ref = datetime.strptime(ref_str, "%Y-%m-%d").date()
    except Exception:
        ref = date.today()
    if period == "semana":
        start = ref - timedelta(days=ref.weekday())  # segunda
        end = start + timedelta(days=6)              # domingo
    elif period == "mes":
        start = ref.replace(day=1)
        last = calendar.monthrange(ref.year, ref.month)[1]
        end = ref.replace(day=last)
    else:
        start = end = ref
    return (start.isoformat(), end.isoformat())

def kpis_range(start, end):
    conn = db_connect(); c = conn.cursor()
    def sum_type(t):
        c.execute("SELECT IFNULL(SUM(qty),0) FROM movements WHERE mov_type=? AND date(mov_date) BETWEEN date(?) AND date(?)", (t, start, end))
        return float(c.fetchone()[0])
    entrada = sum_type('entrada'); saida = sum_type('saida')
    envio = sum_type('envio'); retorno = sum_type('retorno'); perda = sum_type('perda')
    c.execute("SELECT COUNT(*) FROM movements WHERE date(mov_date) BETWEEN date(?) AND date(?)", (start,end))
    linhas = c.fetchone()[0]
    c.execute("""SELECT COUNT(DISTINCT item_id)
                 FROM movements WHERE date(mov_date) BETWEEN date(?) AND date(?)""", (start,end))
    itens_distintos = c.fetchone()[0]
    conn.close()
    return dict(entrada=entrada, saida=saida, envio=envio, retorno=retorno, perda=perda,
                linhas=linhas, itens_distintos=itens_distintos)

def movements_in_range(start, end):
    conn = db_connect(); c = conn.cursor()
    c.execute("""
        SELECT m.mov_date, m.mov_type, i.name as item, m.qty, m.ref, m.note, m.created_at
        FROM movements m JOIN items i ON i.id=m.item_id
        WHERE date(m.mov_date) BETWEEN date(?) AND date(?)
        ORDER BY date(m.mov_date) ASC, m.id ASC;
    """, (start, end))
    rows = c.fetchall(); conn.close()
    return rows

def get_stock_summary():
    conn = db_connect(); c = conn.cursor()
    c.execute("""
        SELECT i.id, i.name,
               IFNULL(SUM(CASE WHEN m.mov_type='entrada' THEN m.qty
                               WHEN m.mov_type='retorno' THEN m.qty
                               WHEN m.mov_type='envio' THEN -m.qty
                               WHEN m.mov_type='saida' THEN -m.qty
                               WHEN m.mov_type='perda' THEN -m.qty
                               ELSE 0 END),0) as no_hotel,
               IFNULL(SUM(CASE WHEN m.mov_type='envio' THEN m.qty
                               WHEN m.mov_type='retorno' THEN -m.qty
                               ELSE 0 END),0) as em_lavanderia
        FROM items i
        LEFT JOIN movements m ON m.item_id = i.id
        WHERE i.active=1
        GROUP BY i.id, i.name
        ORDER BY i.name;
    """)
    rows = c.fetchall(); conn.close()
    data = []
    for r in rows:
        total = (r['no_hotel'] or 0) + (r['em_lavanderia'] or 0)
        data.append(dict(id=r['id'], name=r['name'],
                         no_hotel=round(r['no_hotel'] or 0,2),
                         em_lavanderia=round(r['em_lavanderia'] or 0,2),
                         total=round(total,2)))
    return data

def kpis_for_day(d):
    conn = db_connect(); c = conn.cursor()
    c.execute("SELECT IFNULL(SUM(qty),0) FROM movements WHERE mov_type='envio' AND date(mov_date)=date(?);",(d,)); envios = c.fetchone()[0]
    c.execute("SELECT IFNULL(SUM(qty),0) FROM movements WHERE mov_type='retorno' AND date(mov_date)=date(?);",(d,)); retornos = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM items WHERE active=1;"); itens = c.fetchone()[0]
    conn.close(); return dict(itens=itens, envios=envios, retornos=retornos)

def series_last_7():
    days = [date.today()-timedelta(days=i) for i in range(6,-1,-1)]
    conn = db_connect(); c = conn.cursor(); series = []
    for d in days:
        ds = d.isoformat()
        c.execute("SELECT IFNULL(SUM(qty),0) FROM movements WHERE mov_type='envio' AND date(mov_date)=date(?);",(ds,)); env = float(c.fetchone()[0])
        c.execute("SELECT IFNULL(SUM(qty),0) FROM movements WHERE mov_type='retorno' AND date(mov_date)=date(?);",(ds,)); ret = float(c.fetchone()[0])
        series.append(dict(day=d.strftime('%d/%m'), env=env, ret=ret))
    conn.close(); return series

def query_romaneio(d):
    conn = db_connect(); c = conn.cursor()
    c.execute("""
        SELECT i.name, SUM(m.qty) as qty
        FROM movements m JOIN items i ON i.id=m.item_id
        WHERE m.mov_type='envio' AND date(m.mov_date)=date(?)
        GROUP BY i.name ORDER BY i.name;
    """,(d,)); envio = c.fetchall()
    c.execute("""
        SELECT i.name, SUM(m.qty) as qty
        FROM movements m JOIN items i ON i.id=m.item_id
        WHERE m.mov_type='retorno' AND date(m.mov_date)=date(?)
        GROUP BY i.name ORDER BY i.name;
    """,(d,)); retorno = c.fetchall()
    conn.close(); return envio, retorno

# ------------- Flask app -------------
app = Flask(__name__)
app.secret_key = "bbh-lavanderia-secret"

@app.context_processor
def inject_globals():
    return dict(APP_TITLE=APP_TITLE, current_user=session.get("username"))

# ---- Auth ----
LOGIN_TEMPLATE = """
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <script src="https://cdn.tailwindcss.com"></script>
  <title>Login — Bessa Beach Hotel</title>
  <style>
    .bg-slide{background-size:cover;background-position:center;filter:contrast(1.05) saturate(1.1);}
  </style>
</head>
<body class="min-h-screen">
  <!-- Carousel de fundo -->
  <div id="bg" class="fixed inset-0 bg-slide transition-opacity duration-700"></div>
  <div class="fixed inset-0 bg-slate-900/45"></div>

  <!-- Card de login -->
  <div class="relative min-h-screen flex items-center justify-center p-4">
    <div class="w-full max-w-sm bg-white/95 backdrop-blur shadow-xl rounded-2xl p-6">
      <div class="text-center mb-4">
        <div class="text-xl font-semibold text-slate-900">Bessa Beach Hotel</div>
        <div class="text-xs text-slate-500">Sistema de Lavanderia</div>
      </div>
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        <div class="space-y-2 mb-2">
          {% for cat,msg in messages %}
            <div class="px-3 py-2 rounded-lg text-sm {% if cat=='ok' %}bg-green-50 text-green-800{% elif cat=='error' %}bg-rose-50 text-rose-700{% else %}bg-amber-50 text-amber-700{% endif %}">{{ msg }}</div>
          {% endfor %}
        </div>
        {% endif %}
      {% endwith %}
      <form method="post" class="grid gap-3">
        <input name="username" placeholder="Usuário" class="px-3 py-2 rounded-xl border" required>
        <input type="password" name="password" placeholder="Senha" class="px-3 py-2 rounded-xl border" required>
        <button class="px-4 py-2 rounded-xl bg-slate-900 text-white hover:bg-slate-800">Entrar</button>
      </form>
      <div class="text-[11px] text-slate-500 mt-3 text-center">Padrão: <b>admin</b> / <b>1234</b></div>
      <div class="text-[11px] text-slate-500 mt-1 text-center">Criado por <b>André Vinicius</b></div>
    </div>
  </div>

  <script>
    const imgs = [
      "{{ url_for('static', filename='img/hotel1.jpg') }}",
      "{{ url_for('static', filename='img/hotel2.jpg') }}",
      "{{ url_for('static', filename='img/hotel3.jpg') }}",
    ];
    const bg = document.getElementById('bg');
    let idx = 0;
    function setBg(url){
      bg.style.opacity = 0;
      setTimeout(()=>{
        bg.style.backgroundImage = `url('${url}')`;
        bg.style.opacity = 1;
      }, 250);
    }
    function nextBg(){
      idx = (idx + 1) % imgs.length;
      setBg(imgs[idx]);
    }
    setBg(imgs[0]);
    setInterval(nextBg, 6000);
  </script>
</body>
</html>
"""

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username","").strip()
        pwd = request.form.get("password","")
        conn = db_connect(); c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (user,))
        u = c.fetchone(); conn.close()
        if u and check_password_hash(u["password"], pwd) and (('active' not in u.keys()) or row_get(u,'active',1)==1):
            session["user_id"] = u["id"]; session["username"] = u["username"]
            flash(f"Bem-vindo, {u['username']}! Tenha um ótimo dia de trabalho. 🌞", "ok")
            return redirect(url_for("dashboard"))
        flash("Usuário/senha incorretos ou usuário inativo.", "error")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada.", "ok")
    return redirect(url_for("login"))

# ---- Usuários (admin) ----
@app.route("/usuarios")
@admin_required
def usuarios():
    conn = db_connect(); c = conn.cursor()
    c.execute("SELECT id, username, active, created_at FROM users ORDER BY username;")
    users = c.fetchall(); conn.close()
    return render_template("usuarios.html", users=users)

@app.route("/usuarios/add", methods=["POST"])
@admin_required
def usuarios_add():
    username = request.form.get("username","").strip()
    password = request.form.get("password","").strip()
    if not username or not password:
        flash("Usuário e senha são obrigatórios.", "error")
        return redirect(url_for("usuarios"))
    conn = db_connect(); c = conn.cursor()
    try:
        c.execute("INSERT INTO users(username,password,active) VALUES (?,?,1)",
                  (username, generate_password_hash(password)))
        conn.commit(); flash("Usuário criado.", "ok")
    except sqlite3.IntegrityError:
        flash("Usuário já existe.", "error")
    finally:
        conn.close()
    return redirect(url_for("usuarios"))

@app.route("/usuarios/<int:uid>/reset", methods=["POST"])
@admin_required
def usuarios_reset(uid):
    new_pwd = request.form.get("new_password","").strip()
    if not new_pwd:
        flash("Informe a nova senha.", "error"); return redirect(url_for("usuarios"))
    conn = db_connect(); c = conn.cursor()
    c.execute("UPDATE users SET password=? WHERE id=?;", (generate_password_hash(new_pwd), uid))
    conn.commit(); conn.close()
    flash("Senha atualizada.", "ok"); return redirect(url_for("usuarios"))

@app.route("/usuarios/<int:uid>/toggle", methods=["POST"])
@admin_required
def usuarios_toggle(uid):
    conn = db_connect(); c = conn.cursor()
    c.execute("UPDATE users SET active = CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?;", (uid,))
    conn.commit(); conn.close()
    flash("Status do usuário alterado.", "ok"); return redirect(url_for("usuarios"))

# ---- Páginas principais ----
@app.route("/")
@login_required
def dashboard():
    # Filtros de período
    period = request.args.get("period","dia")
    ref = request.args.get("ref") or date.today().isoformat()
    start, end = parse_period(period, ref)

    stock = get_stock_summary()
    kpis = kpis_for_day(date.today().isoformat())
    series = series_last_7()
    k_range = kpis_range(start, end)

    # Arrays seguros para o Chart.js
    series_labels = [s.get('day') for s in series] if series else []
    series_envios = [float(s.get('env',0) or 0) for s in series] if series else []
    series_retornos = [float(s.get('ret',0) or 0) for s in series] if series else []

    return render_template("dashboard.html",
                           stock=stock, kpis=kpis, series=series,
                           series_labels=series_labels, series_envios=series_envios, series_retornos=series_retornos,
                           period=period, ref=ref, start=start, end=end, k_range=k_range)

@app.route("/itens")
@login_required
def itens():
    q = request.args.get("q","").strip()
    conn = db_connect(); c = conn.cursor()
    if q:
        c.execute("SELECT * FROM items WHERE active=1 AND name LIKE ? ORDER BY name;", (f"%{q}%",))
    else:
        c.execute("SELECT * FROM items WHERE active=1 ORDER BY name;")
    items = c.fetchall(); conn.close()
    return render_template("itens.html", items=items, q=q)

@app.route("/itens/add", methods=["POST"])
@login_required
def itens_add():
    name = request.form.get("name","").strip()
    if not name:
        flash("Nome do item é obrigatório.", "error")
        return redirect(url_for("itens"))
    conn = db_connect(); c = conn.cursor()
    try:
        c.execute("INSERT INTO items(name) VALUES (?);", (name,))
        conn.commit(); flash("Item cadastrado.", "ok")
    except sqlite3.IntegrityError:
        flash("Item já existe.", "warn")
    finally:
        conn.close()
    return redirect(url_for("itens"))

@app.route("/itens/<int:item_id>/inativar", methods=["POST"])
@login_required
def itens_inativar(item_id):
    conn = db_connect(); c = conn.cursor()
    c.execute("UPDATE items SET active=0 WHERE id=?;", (item_id,))
    conn.commit(); conn.close()
    flash("Item inativado.", "ok")
    return redirect(url_for("itens"))

@app.route("/movimentos")
@login_required
def movimentos():
    conn = db_connect(); c = conn.cursor()
    c.execute("SELECT id, name FROM items WHERE active=1 ORDER BY name;")
    items = c.fetchall()
    # ids padrão
    id_map = {row['name']: row['id'] for row in items}
    default_ids = [id_map[name] for name in DEFAULT_MOV_NAMES if name in id_map]
    c.execute("""
        SELECT m.id, m.mov_date, m.mov_type, m.qty, m.ref, m.note, i.name as item_name
        FROM movements m JOIN items i ON i.id = m.item_id
        ORDER BY m.id DESC LIMIT 50;
    """); movs = c.fetchall(); conn.close()
    return render_template("movimentos.html", items=items, movs=movs, today=date.today().isoformat(), default_ids=default_ids)

@app.route("/movimentos/add", methods=["POST"])
@login_required
def movimentos_add():
    mov_date = request.form.get("mov_date") or date.today().isoformat()
    mov_type = (request.form.get("mov_type") or '').strip().lower()
    if mov_type not in ('entrada','saida','envio','retorno','perda'):
        flash('Tipo de movimentação inválido.', 'error'); return redirect(url_for('movimentos'))
    item_id = int(request.form.get("item_id"))
    qty = float(request.form.get("qty") or 0)
    ref = request.form.get("ref","").strip()
    note = request.form.get("note","").strip()
    if qty <= 0:
        flash("Quantidade deve ser maior que zero.", "error")
        return redirect(url_for("movimentos"))
    conn = db_connect(); c = conn.cursor()
    c.execute("""INSERT INTO movements(mov_date,mov_type,item_id,qty,ref,note)
                 VALUES (?,?,?,?,?,?);""",(mov_date, mov_type, item_id, qty, ref, note))
    conn.commit(); conn.close()
    flash("Movimentação registrada.", "ok")
    return redirect(url_for("movimentos"))

@app.route("/movimentos/bulk_add", methods=["POST"])
@login_required
def movimentos_bulk_add():
    mov_date = request.form.get("mov_date") or date.today().isoformat()
    mov_type = (request.form.get("mov_type") or '').strip().lower()
    if mov_type not in ('entrada','saida','envio','retorno','perda'):
        flash('Tipo de movimentação inválido.', 'error'); return redirect(url_for('movimentos'))
    ref = request.form.get("ref","").strip()
    note = request.form.get("note","").strip()
    item_ids = request.form.getlist("item_id[]")
    qtys = request.form.getlist("qty[]")
    if not item_ids or not qtys:
        flash("Inclua pelo menos um item.", "error")
        return redirect(url_for("movimentos"))
    conn = db_connect(); c = conn.cursor(); inserted = 0
    for i, q in zip(item_ids, qtys):
        try:
            iid = int(i); qty = float(q or 0)
            if qty <= 0: continue
            c.execute("""INSERT INTO movements(mov_date,mov_type,item_id,qty,ref,note)
                         VALUES (?,?,?,?,?,?);""", (mov_date, mov_type, iid, qty, ref, note))
            inserted += 1
        except Exception:
            pass
    conn.commit(); conn.close()
    flash(f"{inserted} movimentação(ões) registradas." if inserted else "Nenhuma linha válida.", "ok" if inserted else "warn")
    return redirect(url_for("movimentos"))

@app.route("/movimentos/<int:mid>/delete", methods=["POST"])
@login_required
def movimentos_delete(mid):
    conn = db_connect(); c = conn.cursor()
    c.execute("DELETE FROM movements WHERE id=?;", (mid,))
    conn.commit(); conn.close()
    flash("Movimentação removida.", "ok")
    return redirect(url_for("movimentos"))

@app.route("/romaneio")
@login_required
def romaneio():
    d = request.args.get("data") or date.today().isoformat()
    envio, retorno = query_romaneio(d)
    tot_env = int(round(sum([(r['qty'] or 0) for r in envio])))
    tot_ret = int(round(sum([(r['qty'] or 0) for r in retorno])))
    return render_template("romaneio.html", data=d, envio=envio, retorno=retorno, tot_env=tot_env, tot_ret=tot_ret)

# ---- Exportações ----
@app.route("/export/romaneio.csv")
@login_required
def export_romaneio_csv():
    d = request.args.get("data") or date.today().isoformat()
    envio, retorno = query_romaneio(d)
    si = StringIO(); cw = csv.writer(si, delimiter=';')
    cw.writerow(["Data", d]); cw.writerow([]); cw.writerow(["Tipo","Item","Quantidade"])
    for r in envio: cw.writerow(["ENVIO", r["name"], r["qty"] or 0])
    for r in retorno: cw.writerow(["RETORNO", r["name"], r["qty"] or 0])
    output = BytesIO(si.getvalue().encode('utf-8-sig')); output.seek(0)
    return send_file(output, mimetype="text/csv", as_attachment=True, download_name=f"romaneio_{d}.csv")

@app.route("/export/romaneio.pdf")
@login_required
def export_romaneio_pdf():
    d = request.args.get("data") or date.today().isoformat()

    if A4 is None:
        output = BytesIO()
        output.write(("Instale a dependência 'reportlab': pip install reportlab").encode("utf-8"))
        output.seek(0)
        return send_file(output, mimetype="text/plain", as_attachment=True, download_name="instalar_reportlab.txt")

    envio, retorno = query_romaneio(d)
    total_env = int(round(sum((row_get(r,'qty',0) or 0) for r in envio)))
    total_ret = int(round(sum((row_get(r,'qty',0) or 0) for r in retorno)))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Romaneio {d}", leftMargin=2*cm, rightMargin=2*cm, topMargin=1.6*cm, bottomMargin=1.6*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", fontSize=9, textColor=colors.grey))
    title_style = styles["Title"]; title_style.textColor = colors.HexColor("#0f172a")

    elements = []
    logo_path = os.path.join(BASE_DIR, "static", "logo.png")
    if os.path.exists(logo_path):
        elements.append(RLImage(logo_path, width=3.2*cm, height=3.2*cm))
        elements.append(Spacer(1, 6))

    when = datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y (%A)").title()
    elements.append(Paragraph("BBH — Romaneio de Lavanderia", title_style))
    elements.append(Paragraph(f"Data: <b>{when}</b>", styles["Normal"]))
    elements.append(Paragraph("Criado por André Vinicius · Bessa Beach Hotel — Solicitado por Helbo Moura (Diretor)", styles["Small"]))
    elements.append(Paragraph("Responsável: Micheline Moura", styles["Small"]))
    elements.append(Spacer(1, 14))

    # Envios
    elements.append(Paragraph("<b>Envios</b>", styles["Heading2"]))
    data_env = [["Item","Quantidade"]] + [[row_get(r,"name","—"), int(round(row_get(r,"qty",0) or 0))] for r in envio]
    if len(data_env) == 1: data_env.append(["—", 0])
    tbl_env = Table(data_env, hAlign="LEFT", colWidths=[340, 110])
    tbl_env.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR",(0,0),(-1,0), colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,0),10),
        ("ALIGN",(1,1),(1,-1),"RIGHT"),
        ("GRID",(0,0),(-1,-1),0.25, colors.grey),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.whitesmoke, colors.HexColor("#eef2ff")]),
        ("BOTTOMPADDING",(0,0),(-1,0),6),
    ]))
    elements.append(tbl_env)
    elements.append(Paragraph(f"<br/><b>Total de Envios:</b> {total_env}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    # Retornos
    elements.append(Paragraph("<b>Retornos</b>", styles["Heading2"]))
    data_ret = [["Item","Quantidade"]] + [[row_get(r,"name","—"), int(round(row_get(r,"qty",0) or 0))] for r in retorno]
    if len(data_ret) == 1: data_ret.append(["—", 0])
    tbl_ret = Table(data_ret, hAlign="LEFT", colWidths=[340, 110])
    tbl_ret.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR",(0,0),(-1,0), colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("FONTSIZE",(0,0),(-1,0),10),
        ("ALIGN",(1,1),(1,-1),"RIGHT"),
        ("GRID",(0,0),(-1,-1),0.25, colors.grey),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.whitesmoke, colors.HexColor("#eef2ff")]),
        ("BOTTOMPADDING",(0,0),(-1,0),6),
    ]))
    elements.append(tbl_ret)
    elements.append(Paragraph(f"<br/><b>Total de Retornos:</b> {total_ret}", styles["Normal"]))
    elements.append(Spacer(1, 18))
    elements.append(Paragraph("<br/>Conferido por: ____________________________", styles["Normal"]))
    elements.append(Paragraph("Recebido por: ____________________________", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"romaneio_{d}.pdf")

@app.route("/export/movimentos.csv")
@login_required
def export_mov_period_csv():
    period = request.args.get("period","dia")
    ref = request.args.get("ref") or date.today().isoformat()
    start, end = parse_period(period, ref)
    rows = movements_in_range(start, end)
    si = StringIO(); cw = csv.writer(si, delimiter=';')
    cw.writerow(["Período", period, "Referência", ref, "Início", start, "Fim", end])
    cw.writerow([]); cw.writerow(["Data","Tipo","Item","Quantidade","Ref","Observação","Criado em"])
    for r in rows:
        cw.writerow([r["mov_date"][:10], r["mov_type"].upper(), r["item"], r["qty"], r["ref"] or "", r["note"] or "", r["created_at"]])
    output = BytesIO(si.getvalue().encode('utf-8-sig')); output.seek(0)
    return send_file(output, mimetype="text/csv", as_attachment=True,
                     download_name=f"movimentos_{period}_{start}_a_{end}.csv")

@app.route("/export/estoque.csv")
@login_required
def export_estoque_csv():
    data = get_stock_summary()
    si = StringIO(); cw = csv.writer(si, delimiter=';')
    cw.writerow(["Item","No Hotel","Em Lavanderia","Total"])
    for r in data: cw.writerow([r['name'], r['no_hotel'], r['em_lavanderia'], r['total']])
    output = BytesIO(si.getvalue().encode('utf-8-sig')); output.seek(0)
    return send_file(output, mimetype="text/csv", as_attachment=True, download_name="inventario_atual.csv")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
