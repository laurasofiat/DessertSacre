from flask import Flask, request, render_template, jsonify, redirect, session, flash, url_for
import psycopg2
from psycopg2.extras import RealDictCursor
from flask_mail import Mail, Message
import random
import uuid
import smtplib
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from config import Config
import traceback
import os
import hmac
import hashlib
from dotenv import load_dotenv
import stripe
load_dotenv()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")


# ------------------------------------
# CONFIG GENERAL
# ------------------------------------
app = Flask(__name__)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
app.secret_key = "clave_super_secreta"
app.config.from_object(Config)

DB_CONFIG = {
    'host': "localhost", #host.docker.internal
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

# ====================================
# RUTA PRINCIPAL (INDEX)
# ====================================
@app.route("/")  # Ruta raíz de la aplicación
def index():
    # Renderiza la plantilla index.html
    return render_template("index.html")

# ====================================
# RUTAS DE REGISTRO DE USUARIOS
# ====================================
@app.route("/register", methods=["GET", "POST"])  # Ruta para registro, acepta GET y POST
def register():
    # Limpia sesiones relacionadas con verificación para evitar conflictos
    session.pop("intentos_reenvio", None)
    session.pop("correo_verificacion", None)
    # Renderiza la plantilla de registro
    return render_template("register.html")

@app.route('/guardar', methods=['POST'])  # Ruta para guardar datos del registro
def guardar():
    try:
        # Intenta conectar a la base de datos
        conexion = get_db_connection()
        if conexion is None:
            # Si no hay conexión, retorna error en JSON
            return jsonify(error="Error: No se pudo conectar a la base de datos")

        if request.method == "POST":  # Si es una petición POST
            # Obtiene los datos del formulario, eliminando espacios en blanco
            primer_nombre    = request.form.get("primer_nombre", "").strip()
            segundo_nombre   = request.form.get("segundo_nombre", "").strip()
            primer_apellido  = request.form.get("primer_apellido", "").strip()
            segundo_apellido = request.form.get("segundo_apellido", "").strip()
            correo           = request.form.get("correo", "").strip()
            password         = request.form.get("password", "").strip()
            telefono         = request.form.get("telefono", "").strip()
            direccion        = request.form.get("direccion", "").strip()

            # Verifica que los campos obligatorios estén presentes
            if not primer_nombre or not primer_apellido or not correo or not password:
                return jsonify(error="Faltan datos obligatorios")

            # Crea un cursor con resultados como diccionarios
            cursor = conexion.cursor(cursor_factory=RealDictCursor)
            # Verifica si el correo ya existe en la base de datos
            cursor.execute("SELECT id FROM registro WHERE correo=%s", (correo,))
            if cursor.fetchone():
                # Si existe, muestra mensaje y redirige al login
                flash("El correo ya está registrado. Inicia sesión.", "warning")
                session["correo_login_auto"] = correo
                return redirect("/login")

            # Hashea la contraseña para seguridad
            password_hash = generate_password_hash(password)
            # Genera un código de verificación de 6 dígitos
            codigo = str(random.randint(100000, 999999))

            # SQL para insertar el nuevo usuario
            sql_insertar = """
                INSERT INTO registro (
                    primer_nombre, segundo_nombre, primer_apellido, segundo_apellido,
                    correo, password, telefono, direccion, codigo_verificacion, verificado
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            """
            # Ejecuta la inserción con los datos
            cursor.execute(sql_insertar, (
                primer_nombre, segundo_nombre, primer_apellido, segundo_apellido,
                correo, password_hash, telefono, direccion, codigo
            ))
            # Confirma la transacción
            conexion.commit()

            # Intenta enviar el código de verificación por correo
            if not enviar_codigo(correo, codigo):
                flash("Error enviando correo")

            # Guarda el correo en sesión para verificación
            session["correo_verificacion"] = correo
            # Cierra cursor y conexión
            cursor.close()
            conexion.close()
            # Redirige a la página de verificación
            return redirect("/verify")

    except Exception as e:
        # Si hay error, imprime detalles y retorna error
        print("\nERROR SQL:")
        print(e)
        traceback.print_exc()
        return jsonify(error="Error al procesar la solicitud")

# ====================================
# RUTAS DE VERIFICACIÓN DE CORREO
# ====================================
@app.route("/verify", methods=["GET", "POST"])  # Ruta para verificar código
def verify():
    # Obtiene el correo de verificación de la sesión
    correo = session.get("correo_verificacion")
    if not correo:
        # Si no hay correo, muestra error y redirige al login
        flash("No hay correo para verificar", "danger")
        return redirect("/login")

    # Obtiene el número de intentos de reenvío
    intentos = session.get("intentos_reenvio", 0)

    if request.method == "POST":  # Si es POST, verifica el código
        codigo_ingresado = request.form["codigo"]  # Código del formulario
        # Conecta a la BD
        conexion = get_db_connection()
        cursor = conexion.cursor(cursor_factory=RealDictCursor)
        # Obtiene el código de verificación de la BD
        cursor.execute("SELECT codigo_verificacion FROM registro WHERE correo=%s", (correo,))
        result = cursor.fetchone()

        if not result:
            # Si no hay resultado, error interno
            flash("Error interno.")
            return render_template("verify.html", redirect_login=False, intentos=intentos)

        if codigo_ingresado == result["codigo_verificacion"]:  # Si coincide
            # Actualiza el usuario como verificado
            cursor.execute("UPDATE registro SET verificado=TRUE WHERE correo=%s", (correo,))
            conexion.commit()
            cursor.close()
            conexion.close()
            # Mensaje de éxito y limpia sesión
            flash("Correo verificado con éxito", "success")
            session.pop("correo_verificacion", None)
            session.pop("intentos_reenvio", None)
            return redirect("/inicioU")  # Redirige al inicio de usuario
        else:
            # Código incorrecto
            flash("El código ingresado es incorrecto", "danger")
            return render_template("verify.html", redirect_login=False, intentos=intentos)

    # Si es GET, muestra la plantilla
    return render_template("verify.html", redirect_login=False, intentos=intentos)

@app.route("/reenviar_codigo")  # Ruta para reenviar código
def reenviar_codigo():
    correo = session.get("correo_verificacion")
    if not correo:
        flash("No hay correo para verificar", "danger")
        return redirect("/login")

    intentos = session.get("intentos_reenvio", 0)
    if intentos >= 3:  # Límite de 3 reenvíos
        flash("Límite de reenvíos alcanzado.", "warning")
        return redirect("/verify")

    # Genera nuevo código
    nuevo_codigo = str(random.randint(100000, 999999))
    conexion = get_db_connection()
    cursor = conexion.cursor(cursor_factory=RealDictCursor)
    # Actualiza el código en la BD
    cursor.execute("UPDATE registro SET codigo_verificacion=%s WHERE correo=%s", (nuevo_codigo, correo))
    conexion.commit()
    cursor.close()
    conexion.close()

    # Incrementa intentos
    session["intentos_reenvio"] = intentos + 1
    # Intenta enviar el nuevo código
    if not enviar_codigo(correo, nuevo_codigo):
        flash("Error enviando correo")

    flash("Código reenviado. Revisa tu correo.", "success")
    return redirect("/verify")

# ====================================
# RUTAS DE LOGIN
# ====================================
ADMIN_EMAIL    = "dessertsacre@gmail.com"  # Email del administrador
ADMIN_PASSWORD = "123456"  # Contraseña del administrador (cambiar en producción)

@app.route("/login", methods=["GET", "POST"])  # Ruta de login
def login():
    if request.method == "POST":  # Si es POST, procesa login
        correo   = request.form["correo"]  # Email del formulario
        password = request.form["password"]  # Contraseña del formulario

        if correo == ADMIN_EMAIL and password == ADMIN_PASSWORD:  # Si es admin
            session["admin"] = True  # Marca como admin
            session["usuario"] = "Administrador"  # Nombre de usuario
            flash("Bienvenido administrador", "success")
            return redirect("/admin")  # Redirige al panel admin

        # Conecta a BD para verificar usuario normal
        conexion = get_db_connection()
        cursor   = conexion.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM registro WHERE correo=%s", (correo,))
        usuario = cursor.fetchone()  # Obtiene el usuario

        if not usuario:  # Si no existe
            flash("Correo o contraseña incorrectos", "danger")
            return redirect("/login")

        if not check_password_hash(usuario["password"], password):  # Si contraseña incorrecta
            flash("Correo o contraseña incorrectos", "danger")
            return redirect("/login")

        if not usuario["verificado"]:  # Si no está verificado
            session["correo_verificacion"] = correo  # Guarda para verificación
            session["redir_verificar"] = True  # Flag para redirigir
            flash("Debes verificar tu correo antes de iniciar sesión", "warning")
            return redirect("/verify")

        # Si todo bien, guarda datos del usuario en sesión
        session["usuario"] = {
            "nombre":    usuario["primer_nombre"] + " " + usuario["primer_apellido"],
            "email":     usuario["correo"],
            "telefono":  usuario["telefono"],
            "direccion": usuario["direccion"]
        }

        flash("Inicio de sesión exitoso", "success")
        return redirect("/inicioU")  # Redirige al inicio de usuario

    # Si es GET, obtiene flags de sesión
    redir_verificar = session.pop("redir_verificar", None)
    correo_auto     = session.pop("correo_login_auto", "")
    return render_template("login.html", redir_verificar=redir_verificar, correo_auto=correo_auto)

# ====================================
# RUTA DE LOGOUT
# ====================================
@app.route("/logout")  # Ruta para cerrar sesión
def logout():
    session.clear()  # Limpia toda la sesión
    return redirect("/")  # Redirige a la página principal

# ====================================
# RUTA DE DASHBOARD (USUARIO)
# ====================================
@app.route("/dashboard")  # Ruta del dashboard del usuario
def dashboard():
    if not session.get("usuario"):  # Si no hay usuario en sesión
        return redirect("/login")  # Redirige al login
    return render_template("dashboard.html", usuario=session["usuario"])  # Renderiza dashboard

# ====================================
# RUTAS DE ADMINISTRADOR
# ====================================
@app.route("/admin")  # Ruta del panel admin
def admin():
    if not session.get("admin"):  # Si no es admin
        flash("Acceso solo para administradores", "danger")
        return redirect("/login")

    # Conecta a BD y obtiene todos los usuarios
    conexion = get_db_connection()
    if not conexion:  # Verifica que la conexión fue exitosa
        flash("Error de conexión a la base de datos", "danger")
        return redirect("/login")

    cursor = conexion.cursor(cursor_factory=RealDictCursor)
    
    # Usuarios
    cursor.execute("SELECT * FROM registro")  # Obtiene todos los usuarios
    usuarios = cursor.fetchall()
    
    # Mensajes
    cursor.execute("""
        SELECT *
        FROM mensajes
        ORDER BY fecha DESC
    """)
    mensajes = cursor.fetchall()
    
    cursor.close()
    conexion.close()
    
    # Calcula total de ventas
    total_ventas = sum(p["total"] for p in pedidos_guardados.values())
    


    # Renderiza la plantilla admin con datos
    return render_template("admin/dashboard.html",
        usuarios=usuarios,
        pedidos=pedidos_guardados,
        total_ventas=total_ventas,
        calificaciones=calificaciones,
        mensajes=mensajes,          
        now=datetime.now().strftime("%d %b %Y")   # Fecha actual
    )

@app.route("/admin/pedidos")  # Ruta de pedidos en admin
def admin_pedidos():
    if not session.get("admin"): # Si no es admin
        return redirect("/login") # Redirige al login

    total_ventas = sum(p["total"] for p in pedidos_guardados.values()) # Calcula total de ventas

    return render_template("admin/pedidos.html", # Renderiza plantilla de pedidos
        pedidos=pedidos_guardados, # Pasa los pedidos guardados
        total_ventas=total_ventas # Pasa el total de ventas para mostrar en el admin
    )

@app.route("/admin/usuarios")  # Ruta de usuarios en admin
def usuarios_admin():
    if not session.get("admin"): # Si no es admin
        return redirect("/login") # Redirige al login
    # Obtiene usuarios de BD
    conexion = get_db_connection() # Conecta a la base de datos
    cursor   = conexion.cursor(cursor_factory=RealDictCursor) # Crea cursor con resultados como diccionarios
    cursor.execute("SELECT * FROM registro") # Ejecuta consulta para obtener todos los usuarios
    usuarios = cursor.fetchall() # Guarda los usuarios obtenidos en una variable
    cursor.close() # Cierra el cursor
    conexion.close() # Cierra la conexión a la base de datos
    return render_template("admin/usuarios.html", usuarios=usuarios) # Renderiza plantilla de usuarios pasando la lista de usuarios obtenida

@app.route("/admin/calificaciones")  # Ruta de calificaciones en admin
def admin_calificaciones():
    if not session.get("admin"):  # Si no es admin
        return redirect("/login")  # Redirige al login

    return render_template("admin/calificaciones.html",
        calificaciones=calificaciones  # Pasa todas las calificaciones
    )
    
# ====================================
# FUNCIONES Y RUTAS DEL CARRITO DE COMPRAS
# ====================================
def _get_cart():  # Función privada para obtener el carrito de la sesión
    return session.get("carrito", [])  # Retorna lista de items o lista vacía

def _save_cart(cart):  # Función privada para guardar el carrito en sesión
    session["carrito"] = cart  # Actualiza la sesión

def _get_cart_info(cart=None):  # Función para obtener info del carrito
    if cart is None:
        cart = _get_cart()  # Usa el carrito actual si no se pasa
    total_items = sum(item.get('qty', 0) for item in cart)  # Suma cantidades
    total_price = sum(item.get('precio', 0) * item.get('qty', 0) for item in cart)  # Suma precios
    return {'cart': cart, 'total_items': total_items, 'total_price': total_price}  # Retorna diccionario

@app.route('/agregar_carrito', methods=['POST'])  # Ruta para agregar item al carrito
def agregar_carrito():
    data   = request.get_json(silent=True) or request.form  # Obtiene datos JSON o form
    nombre = data.get('nombre')  # Nombre del producto
    precio = data.get('precio')  # Precio del producto
    try:
        precio = float(precio)  # Convierte a float
    except (TypeError, ValueError):
        return jsonify({'error': 'Precio inválido'}), 400  # Error si no es válido

    if not nombre or precio <= 0:  # Valida datos
        return jsonify({'error': 'Datos inválidos'}), 400

    cart = _get_cart()  # Obtiene carrito actual
    for item in cart:  # Busca si ya existe el producto
        if item['nombre'] == nombre:
            item['qty'] = item.get('qty', 1) + 1  # Incrementa cantidad
            break
    else:
        cart.append({'nombre': nombre, 'precio': precio, 'qty': 1})  # Agrega nuevo item

    _save_cart(cart)  # Guarda carrito
    return jsonify({'success': True, 'cart': cart, 'total_items': sum(item['qty'] for item in cart)})

@app.route('/eliminar_del_carrito')  # Ruta para eliminar item del carrito
def eliminar_del_carrito():
    index = request.args.get('index', type=int)  # Obtiene índice del query string
    cart  = _get_cart()  # Obtiene carrito
    if index is not None and 0 <= index < len(cart):  # Si índice válido
        cart.pop(index)  # Elimina el item
        _save_cart(cart)  # Guarda
        flash('Producto eliminado del carrito', 'success')  # Mensaje
    return redirect('/carrito')  # Redirige al carrito

@app.route('/actualizar_carrito', methods=['POST'])  # Ruta para actualizar cantidades
def actualizar_carrito():
    cart = _get_cart()  # Obtiene carrito
    for i, item in enumerate(cart):  # Para cada item
        qty = request.form.get(f"qty_{i}")  # Obtiene cantidad del form
        try:
            qty = int(qty)  # Convierte a int
        except (TypeError, ValueError):
            continue  # Si error, salta
        if qty < 1:
            continue  # Si menor a 1, salta
        cart[i]['qty'] = qty  # Actualiza cantidad
    _save_cart(cart)  # Guarda
    flash('Carrito actualizado', 'success')  # Mensaje
    return redirect('/carrito')  # Redirige

@app.route('/actualiza_carrito', methods=['POST'])  # Otra ruta similar (parece duplicada)
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
    return redirect('/carritoU')  # Redirige a carritoU

@app.route('/carrito')  # Ruta para ver carrito (versión normal)
def carrito():
    cart  = _get_cart()  # Obtiene carrito
    total = sum(item['precio'] * item['qty'] for item in cart)  # Calcula total
    return render_template('carrito.html', cart=cart, total=total)  # Renderiza

@app.route('/carritoU')  # Ruta para ver carrito (versión usuario)
def carritoU():
    cart  = _get_cart()
    total = sum(item['precio'] * item['qty'] for item in cart)
    return render_template('users/carrito1.html', cart=cart, total=total)

@app.route('/api/cart')  # API para obtener info del carrito
def api_cart():
    return jsonify(_get_cart_info())  # Retorna JSON con info del carrito

@app.route('/api/cart/remove', methods=['POST'])  # API para remover item
def api_cart_remove():
    data = request.get_json(silent=True) or request.form  # Obtiene datos
    try:
        index = int(data.get('index', -1))  # Índice a remover
    except (TypeError, ValueError):
        return jsonify({'error': 'Índice inválido'}), 400  # Error si no válido
    cart = _get_cart()
    if 0 <= index < len(cart):  # Si índice válido
        cart.pop(index)  # Remueve
        _save_cart(cart)  # Guarda
        return jsonify({'success': True, **_get_cart_info(cart)})  # Retorna éxito y info
    return jsonify({'error': 'Índice fuera de rango'}), 400  # Error

@app.route('/api/cart/update', methods=['POST'])  # API para actualizar cantidad
def api_cart_update():
    data = request.get_json(silent=True) or request.form
    try:
        index = int(data.get('index', -1))  # Índice
        qty   = int(data.get('qty', 0))  # Nueva cantidad
    except (TypeError, ValueError):
        return jsonify({'error': 'Datos inválidos'}), 400
    if qty < 1:
        return jsonify({'error': 'La cantidad debe ser al menos 1'}), 400
    cart = _get_cart()
    if 0 <= index < len(cart):  # Si válido
        cart[index]['qty'] = qty  # Actualiza
        _save_cart(cart)
        return jsonify({'success': True, **_get_cart_info(cart)})
    return jsonify({'error': 'Índice fuera de rango'}), 400

@app.route('/confirmacion')  # Ruta de confirmación de compra
def confirmacion():
    cart = _get_cart()
    if not cart:  # Si carrito vacío
        flash('El carrito está vacío.', 'warning')
        return redirect('/carrito')
    session.pop('carrito', None)  # Limpia carrito
    flash('¡Tu compra ha sido confirmada!', 'success')
    return redirect('/pasarela')  # Redirige a pasarela

# ====================================
# PASARELA DE PAGOS
# ====================================
@app.route("/pasarela")
def pasarela():
    if not session.get("usuario"):
        flash("Debes iniciar sesión", "danger")
        return redirect("/login")

    cart = _get_cart()
    if not cart:
        flash("El carrito está vacío", "warning")
        return redirect("/carritoU")

    total = sum(item["precio"] * item["qty"] for item in cart)
    usuario = session["usuario"]

    return render_template(
        "users/pasarela.html",
        usuario   = usuario,
        cart      = cart,
        total     = total,
        stripe_pk = os.getenv("STRIPE_PUBLISHABLE_KEY"),
    )

@app.route("/procesar_pago", methods=["POST"])
def procesar_pago():
   
    if not session.get("usuario"):
        return jsonify({"error": "Debes iniciar sesión"}), 401

    cart = _get_cart()
    if not cart:
        return jsonify({"error": "Carrito vacío"}), 400

    total   = sum(item["precio"] * item["qty"] for item in cart)
    usuario = session["usuario"]

    try:
        # 1. Crea o reutiliza cliente de Stripe
        clientes = stripe.Customer.list(email=usuario["email"], limit=1)
        if clientes.data:
            customer_id = clientes.data[0].id
        else:
            cliente = stripe.Customer.create(
                name  = usuario["nombre"],
                email = usuario["email"],
                metadata = {"user_id": str(usuario.get("id", ""))}
            )
            customer_id = cliente.id

        intent = stripe.PaymentIntent.create(
            amount              = int(total * 100),  # COP: cantidad en centavos
            currency            = "cop",
            customer            = customer_id,
            receipt_email       = usuario["email"],
            # Habilita automáticamente todos los métodos configurados en Stripe Dashboard
            automatic_payment_methods = {
                "enabled": True,
                "allow_redirects": "always"  # Requiere confirmación para ciertos métodos (Nequi, etc.)
            },
            metadata = {
                "cart_items": len(cart),
                "total": total,
                "timestamp": datetime.now().isoformat()
            }
        )

        return jsonify({
            "clientSecret": intent.client_secret,
            "total": total,
            "currency": "cop"
        })

    except stripe.error.StripeError as e:
        print(f"Error Stripe: {e}")
        return jsonify({"error": e.user_message or str(e)}), 500
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/pago_exitoso", methods=["GET"])
def pago_exitoso():
    """

    """
    # Limpia el carrito de la sesión
    session.pop("carrito", None)
    
    # Muestra página de éxito o redirige
    flash("¡Pago realizado con éxito! Gracias por tu compra.", "success")
    return redirect("/inicioU")

@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    if not webhook_secret:
        print("STRIPE_WEBHOOK_SECRET no configurada")
        return jsonify({"status": "ok"}), 200
    
    try:
        # Valida la firma del webhook
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        print("Payload inválido")
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        print(" Firma inválida")
        return jsonify({"error": "Invalid signature"}), 400
    
    # Procesa eventos
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        customer_id = payment_intent.get("customer")
        amount = payment_intent.get("amount")
        currency = payment_intent.get("currency")
        
        print(f" Pago exitoso: {payment_intent['id']} - {amount} {currency}")
        
        # Aquí puedes guardar el pedido en BD, enviar confirmación, etc.
        # Ejemplo: _save_order_to_db(payment_intent)
        
    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        print(f" Pago fallido: {payment_intent['id']}")
        
    elif event["type"] == "charge.refunded":
        charge = event["data"]["object"]
        print(f"↩ Reembolso procesado: {charge['id']}")
    
    return jsonify({"status": "received"}), 200


DATOS_PAGO = {
    "nequi":  {"numero": "3025662571", "titular": "Dessert Sacré"},
    "banco":  {"banco": "BANCOLOMBIA", "numero": "123456789",
               "tipo": "Ahorros", "titular": "Dessert Sacré", "cedula": "3214586088"},
    "efecty": {"convenio": "3214586088", "titular": "Dessert Sacré"}
}

@app.route("/api/datos-pago")
def datos_pago():
    metodo = request.args.get("metodo", "nequi")
    return jsonify({"datos": DATOS_PAGO.get(metodo)})

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
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
# Diccionario para almacenar pedidos (en memoria, no persistente)
pedidos_guardados = {}
# Lista para almacenar calificaciones (en memoria, no persistente)
calificaciones = []
@app.route("/api/calificar", methods=["POST"])  # API para guardar calificación
def calificar():
    if not session.get('usuario'):  # Si no hay usuario autenticado
        return jsonify({"error": "No autenticado"}), 401

    try:
        data    = request.get_json()       # Obtiene datos JSON del frontend
        usuario = session.get('usuario')   # Obtiene el usuario de la sesión

        # Agrega la calificación a la lista con todos los datos
        calificaciones.append({
            "cliente":    usuario["nombre"],          # Nombre del cliente
            "email":      usuario["email"],           # Email del cliente
            "producto":   data.get("producto"),       # Nombre del producto calificado
            "estrellas":  int(data.get("estrellas")), # Número de estrellas (1-5)
            "comentario": data.get("comentario"),     # Comentario del cliente
            "fecha":      datetime.now().strftime("%Y-%m-%d %H:%M")  # Fecha
        })

        return jsonify({"success": True})  # Retorna éxito

    except Exception as e:
        print("ERROR CALIFICAR:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    

# ====================================
# RUTA DE PERFIL
# ====================================
@app.route('/perfil')  # ← agrega esta línea
def perfil():
    if not session.get('usuario'):  # Si no hay usuario
        return redirect('/login')  # Redirige al login

    # Filtra solo las calificaciones del usuario actual
    mis_calificaciones = [
        c for c in calificaciones          # recorre todas las calificaciones
        if c["email"] == session['usuario']["email"]  # solo las del usuario logueado
    ]

    return render_template('users/perfil.html',  # Renderiza perfil
        usuario=session['usuario'],        # Pasa datos del usuario
        pedidos=pedidos_guardados,         # Pasa pedidos
        calificaciones=mis_calificaciones  # Pasa calificaciones del usuario
    )



# ====================================
# RUTAS DE NAVEGACIÓN (NAVBAR)
# ====================================
@app.route("/inicio")  # Ruta de inicio (público)
def inicio():
    return render_template("inicio.html")

@app.route("/inicioU")  # Ruta de inicio (usuario logueado)
def inicioU():
    return render_template("users/inicio1.html")

@app.route('/menu')  # Ruta del menú (público)
def menu():
    return render_template('menu.html')

@app.route('/menuU')  # Ruta del menú (usuario)
def menuU():
    return render_template('users/menu1.html')

@app.route('/sobrenosotros')  # Ruta "Sobre nosotros" (público)
def sobrenosotros():
    return render_template('sobrenosotros.html')

@app.route('/sobrenosotrosU')  # Ruta "Sobre nosotros" (usuario)
def sobrenosotrosU():
    return render_template('users/sobrenosotros1.html')

@app.route('/redes')  # Ruta de redes sociales (público)
def redes():
    return render_template('redes.html')

@app.route('/redesU')  # Ruta de redes sociales (usuario)
def redesU():
    return render_template('users/redes1.html')

@app.route('/pedidos') #Ruta para pedidos (usuario)
def pedidos():
    if not session.get('usuario'): #si no se ha iniciado sesion
        return redirect('/login') #redirige a inicio de sesion
    return render_template('users/pedidos1.html', #si se ha iniciado sesion
        usuario=session['usuario'], #Guarda datos del usuario
        pedidos=pedidos_guardados #Guarda los pedidos realizados
    )

@app.route('/panaderia')  # Ruta de panadería (público)
def panaderia():
    return render_template('panaderia.html')

@app.route('/panaderiaU')  # Ruta de panadería (usuario)
def panaderiaU():
    return render_template('users/panaderia1.html')

@app.route('/pasteleria')  # Ruta de pastelería (público)
def pasteleria():
    return render_template('pasteleria.html')

@app.route('/pasteleriaU')  # Ruta de pastelería (usuario)
def pasteleriaU():
    return render_template('users/pasteleria1.html')

@app.route('/reposteria')  # Ruta de repostería (público)
def reposteria():
    return render_template('reposteria.html')

@app.route('/reposteriaU')  # Ruta de repostería (usuario)
def reposteriaU():
    return render_template('users/reposteria1.html')

@app.route('/bebidas')  # Ruta de bebidas (público)
def bebidas():
    return render_template('bebidas.html')

@app.route('/bebidasU')  # Ruta de bebidas (usuario)
def bebidasU():
    return render_template('users/bebidas1.html')

# ====================================
# RUTAS DE RECUPERACIÓN DE CONTRASEÑA
# ====================================
@app.route("/forgot", methods=["GET", "POST"])  # Ruta para solicitar recuperación
def forgot():
    if request.method == "POST":  # Si es POST
        correo = request.form.get("correo", "").strip()  # Obtiene email
        if not correo:  # Si no hay email
            flash("Por favor ingresa un correo.", "warning")
            return redirect("/forgot")

        # Conecta a BD
        conexion = get_db_connection()
        if not conexion:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect("/forgot")

        with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id FROM registro WHERE correo=%s", (correo,))
            usuario = cursor.fetchone()  # Verifica si existe
            if not usuario:
                flash("El correo ingresado no existe.", "danger")
                session["redir_register"] = True  # Flag para redirigir a registro
                return redirect("/forgot")

            codigo     = str(random.randint(100000, 999999))  # Genera código
            expiracion = datetime.now() + timedelta(minutes=15)  # Expira en 15 min
            # Inserta en tabla recuperacion
            cursor.execute("""
                INSERT INTO recuperacion (correo, codigo, expiracion, usado)
                VALUES (%s, %s, %s, FALSE)
            """, (correo, codigo, expiracion))
            conexion.commit()  # Confirma

        conexion.close()
        enviar_codigo(correo, codigo)  # Envía código
        flash("Código enviado a tu correo.", "success")
        session["correo_recuperar"] = correo  # Guarda email en sesión
        return redirect("/reset-code")  # Redirige a ingresar código

    return render_template("forgot.html")  # Renderiza formulario

@app.route("/reset-code", methods=["GET", "POST"])  # Ruta para ingresar código de recuperación
def reset_code():
    correo = session.get("correo_recuperar")  # Obtiene email de sesión
    if not correo:  # Si no hay
        flash("Primero ingresa tu correo", "warning")
        return redirect("/forgot")

    if request.method == "POST":  # Si es POST
        codigo_ingresado = request.form.get("codigo", "").strip()  # Código del form
        # Conecta a BD
        conexion = get_db_connection()
        if not conexion:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect("/reset-code")

        with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
            # Busca el código más reciente no usado
            cursor.execute("""
                SELECT * FROM recuperacion
                WHERE correo=%s AND codigo=%s AND usado=FALSE
                ORDER BY expiracion DESC LIMIT 1
            """, (correo, codigo_ingresado))
            resultado = cursor.fetchone()  # Obtiene resultado

            if not resultado:  # Si no encontrado
                flash("Código incorrecto o ya usado.", "danger")
                return redirect("/reset-code")

            if datetime.now() > resultado["expiracion"]:  # Si expiró
                flash("El código ha expirado.", "danger")
                return redirect("/forgot")

            # Marca como usado
            cursor.execute("UPDATE recuperacion SET usado=TRUE WHERE id=%s", (resultado["id"],))
            conexion.commit()

        conexion.close()
        flash("Código correcto.", "success")
        return redirect("/reset-password")  # Redirige a cambiar contraseña

    return render_template("reset_code.html")  # Renderiza formulario

@app.route("/reset-password", methods=["GET", "POST"])  # Ruta para cambiar contraseña
def reset_password():
    correo = session.get("correo_recuperar")  # Obtiene email
    if not correo:
        flash("Primero ingresa tu correo", "warning")
        return redirect("/forgot")

    if request.method == "POST":  # Si es POST
        new_password = request.form.get("password", "").strip()  # Nueva contraseña
        confirm      = request.form.get("confirm_password", "").strip()  # Confirmación

        if not new_password or not confirm:  # Si faltan
            flash("Debes ingresar una contraseña.", "warning")
            return redirect("/reset-password")

        if new_password != confirm:  # Si no coinciden
            flash("Las contraseñas no coinciden.", "danger")
            return redirect("/reset-password")

        password_hash = generate_password_hash(new_password)  # Hashea nueva contraseña
        # Conecta a BD
        conexion = get_db_connection()
        if not conexion:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect("/reset-password")

        with conexion.cursor() as cursor:
            # Actualiza contraseña
            cursor.execute("UPDATE registro SET password=%s WHERE correo=%s", (password_hash, correo))
            conexion.commit()

        conexion.close()
        session.pop("correo_recuperar", None)  # Limpia sesión
        flash("Contraseña cambiada correctamente ✔", "success")
        return redirect("/login")  # Redirige al login

    return render_template("reset_password.html")  # Renderiza formulario

# ====================================
# MODAL DE LOGIN (ZONA PROTEGIDA)
# ====================================
@app.route("/zona_protegida")  # Ruta para zona protegida
def zona_protegida():
    if not session.get("usuario") and not session.get("modal_cerrado"):  # Si no usuario y modal no cerrado
        return render_template("zona_protegida.html", mostrar_modal=True)  # Muestra modal
    return render_template("zona_protegida.html", mostrar_modal=False)  # No muestra

@app.context_processor  # Procesador de contexto para todas las plantillas
def inject_modal_flag():
    mostrar_modal = (  # Determina si mostrar modal
        not session.get("usuario") and not session.get("modal_cerrado")
    )
    return dict(mostrar_modal=mostrar_modal)  # Retorna flag

@app.route("/cerrar-modal")  # Ruta para cerrar modal
def cerrar_modal():
    session["modal_cerrado"] = True  # Marca como cerrado
    return "", 204  # Respuesta vacía con código 204



# ====================================
# RUTA Y TABLA DE MENSAJES
# ====================================
def crear_tabla_mensajes():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS mensajes (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(100) NOT NULL,
        apellido VARCHAR(100) NOT NULL,
        email VARCHAR(150) NOT NULL,
        mensaje TEXT NOT NULL,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        leido BOOLEAN DEFAULT FALSE
    );
    """)

    conn.commit()
    cur.close()
    conn.close()

#----FUNCION PARA ENVIAR CORREO-----
def enviar_mensaje_contacto(nombre, apellido, email, mensaje):

    cuerpo = f"""
Nuevo mensaje recibido desde Dessert Sacré

Nombre: {nombre} {apellido}
Correo: {email}

Mensaje:
{mensaje}
"""

    msg = MIMEText(cuerpo)

    msg["Subject"] = f"Nuevo mensaje de {nombre}"
    msg["From"] = EMAIL_USER
    msg["To"] = "dessertsacre@gmail.com"

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)

        return True

    except Exception as e:
        print("Error enviando mensaje:", e)
        return False

#-----RUTA PARA GUARDAR MENSAJES-----
@app.route('/enviar_mensaje', methods=['POST'])
def enviar_mensaje():

    if not session.get("usuario"):
        return jsonify({
            "success": False,
            "mensaje": "Debes iniciar sesión"
        }), 401

    nombre = request.form.get("nombre")
    apellido = request.form.get("apellido")
    email = request.form.get("email")
    mensaje = request.form.get("mensaje")

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO mensajes
            (nombre, apellido, email, mensaje)
            VALUES (%s,%s,%s,%s)
        """, (nombre, apellido, email, mensaje))

        conn.commit()

        cur.close()
        conn.close()

        correo_enviado = enviar_mensaje_contacto(
            nombre,
            apellido,
            email,
            mensaje
        )

        return jsonify({
            "success": True,
            "correo_enviado": correo_enviado
        })

    except Exception as e:

        print("ERROR:", e)

        return jsonify({
            "success": False,
            "mensaje": str(e)
        })


#------CONTADOR DE MENSAJES NO LEÍDOS EN EL ADMIN-----
@app.context_processor
def mensajes_sin_leer():

    cantidad = 0

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*)
            FROM mensajes
            WHERE leido = FALSE
        """)

        cantidad = cur.fetchone()[0]

        cur.close()
        conn.close()

    except:
        pass

    return dict(admin_unread_messages=cantidad)


#-----TABLA DE MENSAJES-----
crear_tabla_mensajes() # Crea la tabla de mensajes al iniciar la aplicación
#---------------------------

# ====================================
# EJECUCIÓN DE LA APLICACIÓN
# ====================================
if __name__ == "__main__":  # Si se ejecuta directamente
    crear_tabla()  # Crea las tablas si no existen
    app.run(host="0.0.0.0", port=5000, debug=True)  # Ejecuta el servidor en modo debug