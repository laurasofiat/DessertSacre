from flask import Flask, request, render_template, jsonify, redirect, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import uuid
import smtplib
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from config import Config
import traceback

# ------------------------------------
# CONFIG GENERAL
# ------------------------------------
app = Flask(__name__)
app.secret_key = "clave_super_secreta"
app.config.from_object(Config)

DB_CONFIG = {
    'host': "localhost",
    'dbname': "Dessert_Sacre",
    'user': "postgres",
    'password': "123456",
    'port': 5432
}

def get_db_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print("Error BD:", e)
        return None

# ------------------------------------
# CONFIG SMTP GMAIL
# ------------------------------------
EMAIL_USER = app.config["EMAIL_USER"]
EMAIL_PASS = app.config["EMAIL_PASS"]

def enviar_codigo(correo_destino, codigo):
    msg = MIMEText(f"Tu código de verificación es: {codigo}")
    msg["Subject"] = "Código de verificación"
    msg["From"] = EMAIL_USER
    msg["To"] = correo_destino
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
            print("Correo enviado ✔")
            return True
    except Exception as e:
        print("Error enviando correo:", e)
        return False

# ------------------------------------
# TABLAS
# ------------------------------------
def crear_tabla():
    conexion = get_db_connection()
    if conexion:
        cursor = conexion.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS registro (
            id SERIAL PRIMARY KEY,
            primer_nombre VARCHAR(100) NOT NULL,
            segundo_nombre VARCHAR(100),
            primer_apellido VARCHAR(100) NOT NULL,
            segundo_apellido VARCHAR(100),
            correo VARCHAR(150) UNIQUE NOT NULL,
            password TEXT NOT NULL,
            telefono VARCHAR(20),
            direccion TEXT,
            codigo_verificacion VARCHAR(6),
            verificado BOOLEAN DEFAULT FALSE
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recuperacion (
            id SERIAL PRIMARY KEY,
            correo VARCHAR(150) NOT NULL REFERENCES registro(correo),
            codigo VARCHAR(6) NOT NULL,
            expiracion TIMESTAMP DEFAULT (NOW() + INTERVAL '15 minutes'),
            usado BOOLEAN DEFAULT FALSE
        );
        """)
        conexion.commit()
        cursor.close()
        conexion.close()

# ------------------------------------
# INDEX
# ------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# ------------------------------------
# REGISTRO
# ------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    session.pop("intentos_reenvio", None)
    session.pop("correo_verificacion", None)
    return render_template("register.html")

@app.route('/guardar', methods=['POST'])
def guardar():
    try:
        conexion = get_db_connection()
        if conexion is None:
            return jsonify(error="Error: No se pudo conectar a la base de datos")

        if request.method == "POST":
            primer_nombre    = request.form.get("primer_nombre", "").strip()
            segundo_nombre   = request.form.get("segundo_nombre", "").strip()
            primer_apellido  = request.form.get("primer_apellido", "").strip()
            segundo_apellido = request.form.get("segundo_apellido", "").strip()
            correo           = request.form.get("correo", "").strip()
            password         = request.form.get("password", "").strip()
            telefono         = request.form.get("telefono", "").strip()
            direccion        = request.form.get("direccion", "").strip()

            if not primer_nombre or not primer_apellido or not correo or not password:
                return jsonify(error="Faltan datos obligatorios")

            cursor = conexion.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT id FROM registro WHERE correo=%s", (correo,))
            if cursor.fetchone():
                flash("El correo ya está registrado. Inicia sesión.", "warning")
                session["correo_login_auto"] = correo
                return redirect("/login")

            password_hash = generate_password_hash(password)
            codigo = str(random.randint(100000, 999999))

            sql_insertar = """
                INSERT INTO registro (
                    primer_nombre, segundo_nombre, primer_apellido, segundo_apellido,
                    correo, password, telefono, direccion, codigo_verificacion, verificado
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            """
            cursor.execute(sql_insertar, (
                primer_nombre, segundo_nombre, primer_apellido, segundo_apellido,
                correo, password_hash, telefono, direccion, codigo
            ))
            conexion.commit()

            if not enviar_codigo(correo, codigo):
                flash("Error enviando correo")

            session["correo_verificacion"] = correo
            cursor.close()
            conexion.close()
            return redirect("/verify")

    except Exception as e:
        print("\nERROR SQL:")
        print(e)
        traceback.print_exc()
        return jsonify(error="Error al procesar la solicitud")

# ------------------------------------
# VERIFICACIÓN
# ------------------------------------
@app.route("/verify", methods=["GET", "POST"])
def verify():
    correo = session.get("correo_verificacion")
    if not correo:
        flash("No hay correo para verificar", "danger")
        return redirect("/login")

    intentos = session.get("intentos_reenvio", 0)

    if request.method == "POST":
        codigo_ingresado = request.form["codigo"]
        conexion = get_db_connection()
        cursor = conexion.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT codigo_verificacion FROM registro WHERE correo=%s", (correo,))
        result = cursor.fetchone()

        if not result:
            flash("Error interno.")
            return render_template("verify.html", redirect_login=False, intentos=intentos)

        if codigo_ingresado == result["codigo_verificacion"]:
            cursor.execute("UPDATE registro SET verificado=TRUE WHERE correo=%s", (correo,))
            conexion.commit()
            cursor.close()
            conexion.close()
            flash("Correo verificado con éxito", "success")
            session.pop("correo_verificacion", None)
            session.pop("intentos_reenvio", None)
            return redirect("/inicioU")
        else:
            flash("El código ingresado es incorrecto", "danger")
            return render_template("verify.html", redirect_login=False, intentos=intentos)

    return render_template("verify.html", redirect_login=False, intentos=intentos)

@app.route("/reenviar_codigo")
def reenviar_codigo():
    correo = session.get("correo_verificacion")
    if not correo:
        flash("No hay correo para verificar", "danger")
        return redirect("/login")

    intentos = session.get("intentos_reenvio", 0)
    if intentos >= 3:
        flash("Límite de reenvíos alcanzado.", "warning")
        return redirect("/verify")

    nuevo_codigo = str(random.randint(100000, 999999))
    conexion = get_db_connection()
    cursor = conexion.cursor(cursor_factory=RealDictCursor)
    cursor.execute("UPDATE registro SET codigo_verificacion=%s WHERE correo=%s", (nuevo_codigo, correo))
    conexion.commit()
    cursor.close()
    conexion.close()

    session["intentos_reenvio"] = intentos + 1
    if not enviar_codigo(correo, nuevo_codigo):
        flash("Error enviando correo")

    flash("Código reenviado. Revisa tu correo.", "success")
    return redirect("/verify")

# ------------------------------------
# LOGIN
# ------------------------------------
ADMIN_EMAIL    = "dessertsacre@gmail.com"
ADMIN_PASSWORD = "123456"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo   = request.form["correo"]
        password = request.form["password"]

        if correo == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["admin"] = True
            session["usuario"] = "Administrador"
            flash("Bienvenido administrador", "success")
            return redirect("/admin")

        conexion = get_db_connection()
        cursor   = conexion.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM registro WHERE correo=%s", (correo,))
        usuario = cursor.fetchone()

        if not usuario:
            flash("Correo o contraseña incorrectos", "danger")
            return redirect("/login")

        if not check_password_hash(usuario["password"], password):
            flash("Correo o contraseña incorrectos", "danger")
            return redirect("/login")

        if not usuario["verificado"]:
            session["correo_verificacion"] = correo
            session["redir_verificar"] = True
            flash("Debes verificar tu correo antes de iniciar sesión", "warning")
            return redirect("/verify")

        session["usuario"] = {
            "nombre":    usuario["primer_nombre"] + " " + usuario["primer_apellido"],
            "email":     usuario["correo"],
            "telefono":  usuario["telefono"],
            "direccion": usuario["direccion"]
        }

        flash("Inicio de sesión exitoso", "success")
        return redirect("/inicioU")

    redir_verificar = session.pop("redir_verificar", None)
    correo_auto     = session.pop("correo_login_auto", "")
    return render_template("login.html", redir_verificar=redir_verificar, correo_auto=correo_auto)

# ------------------------------------
# LOGOUT
# ------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ------------------------------------
# DASHBOARD
# ------------------------------------
@app.route("/dashboard")
def dashboard():
    if not session.get("usuario"):
        return redirect("/login")
    return render_template("dashboard.html", usuario=session["usuario"])

# ------------------------------------
# ADMIN
# ------------------------------------
@app.route("/admin")
def admin():
    if not session.get("admin"):
        flash("Acceso solo para administradores", "danger")
        return redirect("/login")

    conexion = get_db_connection()
    cursor   = conexion.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM registro")
    usuarios = cursor.fetchall()
    cursor.close()
    conexion.close()

    total_ventas = sum(p["total"] for p in pedidos_guardados.values())

    return render_template("admin/dashboard.html",
        usuarios=usuarios,
        pedidos=pedidos_guardados,
        total_ventas=total_ventas
    )

@app.route("/admin/pedidos")
def admin_pedidos():
    if not session.get("admin"):
        return redirect("/login")
    return render_template("admin/pedidos.html")

@app.route("/admin/usuarios")
def usuarios_admin():
    if not session.get("admin"):
        return redirect("/login")
    conexion = get_db_connection()
    cursor   = conexion.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM registro")
    usuarios = cursor.fetchall()
    cursor.close()
    conexion.close()
    return render_template("admin/usuarios.html", usuarios=usuarios)

# ------------------------------------
# CARRITO
# ------------------------------------
def _get_cart():
    return session.get("carrito", [])

def _save_cart(cart):
    session["carrito"] = cart

def _get_cart_info(cart=None):
    if cart is None:
        cart = _get_cart()
    total_items = sum(item.get('qty', 0) for item in cart)
    total_price = sum(item.get('precio', 0) * item.get('qty', 0) for item in cart)
    return {'cart': cart, 'total_items': total_items, 'total_price': total_price}

@app.route('/agregar_carrito', methods=['POST'])
def agregar_carrito():
    data   = request.get_json(silent=True) or request.form
    nombre = data.get('nombre')
    precio = data.get('precio')
    try:
        precio = float(precio)
    except (TypeError, ValueError):
        return jsonify({'error': 'Precio inválido'}), 400

    if not nombre or precio <= 0:
        return jsonify({'error': 'Datos inválidos'}), 400

    cart = _get_cart()
    for item in cart:
        if item['nombre'] == nombre:
            item['qty'] = item.get('qty', 1) + 1
            break
    else:
        cart.append({'nombre': nombre, 'precio': precio, 'qty': 1})

    _save_cart(cart)
    return jsonify({'success': True, 'cart': cart, 'total_items': sum(item['qty'] for item in cart)})

@app.route('/eliminar_del_carrito')
def eliminar_del_carrito():
    index = request.args.get('index', type=int)
    cart  = _get_cart()
    if index is not None and 0 <= index < len(cart):
        cart.pop(index)
        _save_cart(cart)
        flash('Producto eliminado del carrito', 'success')
    return redirect('/carrito')

@app.route('/actualizar_carrito', methods=['POST'])
def actualizar_carrito():
    cart = _get_cart()
    for i, item in enumerate(cart):
        qty = request.form.get(f"qty_{i}")
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            continue
        if qty < 1:
            continue
        cart[i]['qty'] = qty
    _save_cart(cart)
    flash('Carrito actualizado', 'success')
    return redirect('/carrito')

@app.route('/actualiza_carrito', methods=['POST'])
def actualiza_carrito():
    cart = _get_cart()
    for i, item in enumerate(cart):
        qty = request.form.get(f"qty_{i}")
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            continue
        if qty < 1:
            continue
        cart[i]['qty'] = qty
    _save_cart(cart)
    flash('Carrito actualizado', 'success')
    return redirect('/carritoU')

@app.route('/carrito')
def carrito():
    cart  = _get_cart()
    total = sum(item['precio'] * item['qty'] for item in cart)
    return render_template('carrito.html', cart=cart, total=total)

@app.route('/carritoU')
def carritoU():
    cart  = _get_cart()
    total = sum(item['precio'] * item['qty'] for item in cart)
    return render_template('carrito1.html', cart=cart, total=total)

@app.route('/api/cart')
def api_cart():
    return jsonify(_get_cart_info())

@app.route('/api/cart/remove', methods=['POST'])
def api_cart_remove():
    data = request.get_json(silent=True) or request.form
    try:
        index = int(data.get('index', -1))
    except (TypeError, ValueError):
        return jsonify({'error': 'Índice inválido'}), 400
    cart = _get_cart()
    if 0 <= index < len(cart):
        cart.pop(index)
        _save_cart(cart)
        return jsonify({'success': True, **_get_cart_info(cart)})
    return jsonify({'error': 'Índice fuera de rango'}), 400

@app.route('/api/cart/update', methods=['POST'])
def api_cart_update():
    data = request.get_json(silent=True) or request.form
    try:
        index = int(data.get('index', -1))
        qty   = int(data.get('qty', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Datos inválidos'}), 400
    if qty < 1:
        return jsonify({'error': 'La cantidad debe ser al menos 1'}), 400
    cart = _get_cart()
    if 0 <= index < len(cart):
        cart[index]['qty'] = qty
        _save_cart(cart)
        return jsonify({'success': True, **_get_cart_info(cart)})
    return jsonify({'error': 'Índice fuera de rango'}), 400

@app.route('/confirmacion')
def confirmacion():
    cart = _get_cart()
    if not cart:
        flash('El carrito está vacío.', 'warning')
        return redirect('/carrito')
    session.pop('carrito', None)
    flash('¡Tu compra ha sido confirmada!', 'success')
    return redirect('/pasarela')

# ------------------------------------
# PASARELA DE PAGOS
# ------------------------------------
@app.route("/pasarela")
def pasarela():
    usuario = session.get('usuario')
    if not usuario:
        flash("Debes iniciar sesión", "danger")
        return redirect("/login")
    cart  = _get_cart()
    total = sum(item['precio'] * item['qty'] for item in cart)
    return render_template("pasarela.html", usuario=usuario, total=total, cart=cart)

DATOS_PAGO = {
    "nequi": {
        "numero":  "123456789",
        "titular": "Dessert Sacré"
    },
    "banco": {
        "banco":   "BANCOLOMBIA",
        "numero":  "123456789",
        "tipo":    "Ahorros",
        "titular": "Dessert Sacré",
        "cedula":  "3214586088"
    },
    "efecty": {
        "convenio": "3214586088",
        "titular":  "Dessert Sacré"
    }
}

@app.route("/api/datos-pago")
def datos_pago():
    metodo = request.args.get("metodo", "nequi")
    return jsonify({"datos": DATOS_PAGO.get(metodo)})

# Diccionario de pedidos (renombrado para no chocar con def pedidos())
pedidos_guardados = {}

@app.route("/api/crear-pedido", methods=["POST"])
def crear_pedido():
    if not session.get('usuario'):
        return jsonify({"error": "No autenticado"}), 401

    try:
        data = request.get_json()
        cart = _get_cart()

        if not cart:
            return jsonify({"error": "Carrito vacío"}), 400

        total = sum(item['precio'] * item['qty'] for item in cart)
        ref   = f"PED-{uuid.uuid4().hex[:8].upper()}"

        pedidos_guardados[ref] = {
            "total":    total,
            "metodo":   data.get("metodo"),
            "nombre":   data.get("nombre"),
            "email":    data.get("email"),
            "telefono": data.get("telefono"),
            "fecha":    datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        session.pop("carrito", None)

        return jsonify({"referencia": ref, "total": total})

    except Exception as e:
        print("ERROR CREAR PEDIDO:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ------------------------------------
# PERFIL
# ------------------------------------
@app.route('/perfil')
def perfil():
    if not session.get('usuario'):
        return redirect('/login')
    return render_template('perfil.html',
        usuario=session['usuario'],
        pedidos=pedidos_guardados
    )

# ------------------------------------
# NAVBAR — RUTAS
# ------------------------------------
@app.route("/inicio")
def inicio():
    return render_template("inicio.html")

@app.route("/inicioU")
def inicioU():
    return render_template("inicio1.html")

@app.route('/menu')
def menu():
    return render_template('menu.html')

@app.route('/menuU')
def menuU():
    return render_template('menu1.html')

@app.route('/sobrenosotros')
def sobrenosotros():
    return render_template('sobrenosotros.html')

@app.route('/sobrenosotrosU')
def sobrenosotrosU():
    return render_template('sobrenosotros1.html')

@app.route('/redes')
def redes():
    return render_template('redes.html')

@app.route('/redesU')
def redesU():
    return render_template('redes1.html')

@app.route('/pedidos')
def pedidos():
    if not session.get('usuario'):
        return redirect('/login')
    return render_template('pedidos.html',
        usuario=session['usuario'],
        pedidos=pedidos_guardados
    )

@app.route('/panaderia')
def panaderia():
    return render_template('panaderia.html')

@app.route('/panaderiaU')
def panaderiaU():
    return render_template('panaderia1.html')

@app.route('/pasteleria')
def pasteleria():
    return render_template('pasteleria.html')

@app.route('/pasteleriaU')
def pasteleriaU():
    return render_template('pasteleria1.html')

@app.route('/reposteria')
def reposteria():
    return render_template('reposteria.html')

@app.route('/reposteriaU')
def reposteriaU():
    return render_template('reposteria1.html')

@app.route('/bebidas')
def bebidas():
    return render_template('bebidas.html')

@app.route('/bebidasU')
def bebidasU():
    return render_template('bebidas1.html')

# ------------------------------------
# RECUPERACIÓN DE CONTRASEÑA
# ------------------------------------
@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip()
        if not correo:
            flash("Por favor ingresa un correo.", "warning")
            return redirect("/forgot")

        conexion = get_db_connection()
        if not conexion:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect("/forgot")

        with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id FROM registro WHERE correo=%s", (correo,))
            usuario = cursor.fetchone()
            if not usuario:
                flash("El correo ingresado no existe.", "danger")
                session["redir_register"] = True
                return redirect("/forgot")

            codigo     = str(random.randint(100000, 999999))
            expiracion = datetime.now() + timedelta(minutes=15)
            cursor.execute("""
                INSERT INTO recuperacion (correo, codigo, expiracion, usado)
                VALUES (%s, %s, %s, FALSE)
            """, (correo, codigo, expiracion))
            conexion.commit()

        conexion.close()
        enviar_codigo(correo, codigo)
        flash("Código enviado a tu correo.", "success")
        session["correo_recuperar"] = correo
        return redirect("/reset-code")

    return render_template("forgot.html")

@app.route("/reset-code", methods=["GET", "POST"])
def reset_code():
    correo = session.get("correo_recuperar")
    if not correo:
        flash("Primero ingresa tu correo", "warning")
        return redirect("/forgot")

    if request.method == "POST":
        codigo_ingresado = request.form.get("codigo", "").strip()
        conexion = get_db_connection()
        if not conexion:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect("/reset-code")

        with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM recuperacion
                WHERE correo=%s AND codigo=%s AND usado=FALSE
                ORDER BY expiracion DESC LIMIT 1
            """, (correo, codigo_ingresado))
            resultado = cursor.fetchone()

            if not resultado:
                flash("Código incorrecto o ya usado.", "danger")
                return redirect("/reset-code")

            if datetime.now() > resultado["expiracion"]:
                flash("El código ha expirado.", "danger")
                return redirect("/forgot")

            cursor.execute("UPDATE recuperacion SET usado=TRUE WHERE id=%s", (resultado["id"],))
            conexion.commit()

        conexion.close()
        flash("Código correcto.", "success")
        return redirect("/reset-password")

    return render_template("reset_code.html")

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    correo = session.get("correo_recuperar")
    if not correo:
        flash("Primero ingresa tu correo", "warning")
        return redirect("/forgot")

    if request.method == "POST":
        new_password = request.form.get("password", "").strip()
        confirm      = request.form.get("confirm_password", "").strip()

        if not new_password or not confirm:
            flash("Debes ingresar una contraseña.", "warning")
            return redirect("/reset-password")

        if new_password != confirm:
            flash("Las contraseñas no coinciden.", "danger")
            return redirect("/reset-password")

        password_hash = generate_password_hash(new_password)
        conexion = get_db_connection()
        if not conexion:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect("/reset-password")

        with conexion.cursor() as cursor:
            cursor.execute("UPDATE registro SET password=%s WHERE correo=%s", (password_hash, correo))
            conexion.commit()

        conexion.close()
        session.pop("correo_recuperar", None)
        flash("Contraseña cambiada correctamente ✔", "success")
        return redirect("/login")

    return render_template("reset_password.html")

# ------------------------------------
# MODAL LOGIN
# ------------------------------------
@app.route("/zona_protegida")
def zona_protegida():
    if not session.get("usuario") and not session.get("modal_cerrado"):
        return render_template("zona_protegida.html", mostrar_modal=True)
    return render_template("zona_protegida.html", mostrar_modal=False)

@app.context_processor
def inject_modal_flag():
    mostrar_modal = (
        not session.get("usuario") and not session.get("modal_cerrado")
    )
    return dict(mostrar_modal=mostrar_modal)

@app.route("/cerrar-modal")
def cerrar_modal():
    session["modal_cerrado"] = True
    return "", 204

# ------------------------------------
# RUN
# ------------------------------------
if __name__ == "__main__":
    crear_tabla()
    app.run(host="0.0.0.0", port=5000, debug=True)