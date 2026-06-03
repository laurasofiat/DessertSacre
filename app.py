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
    cursor.execute("SELECT * FROM registro")  # Obtiene todos los usuarios
    usuarios = cursor.fetchall()
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
    return render_template('carrito1.html', cart=cart, total=total)

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
@app.route("/pasarela")  # Ruta de la pasarela de pagos
def pasarela():
    usuario = session.get('usuario')  # Obtiene usuario de sesión
    if not usuario:  # Si no hay usuario
        flash("Debes iniciar sesión", "danger")
        return redirect("/login")
    cart  = _get_cart()  # Obtiene carrito
    total = sum(item['precio'] * item['qty'] for item in cart)  # Calcula total
    return render_template("pasarela.html", usuario=usuario, total=total, cart=cart)  # Renderiza

DATOS_PAGO = {  # Diccionario con datos de pago para diferentes métodos
    "nequi": {
        "numero":  "123456789",  # Número de Nequi
        "titular": "Dessert Sacré"  # Titular
    },
    "banco": {
        "banco":   "BANCOLOMBIA",  # Banco
        "numero":  "123456789",  # Número de cuenta
        "tipo":    "Ahorros",  # Tipo de cuenta
        "titular": "Dessert Sacré",  # Titular
        "cedula":  "3214586088"  # Cédula
    },
    "efecty": {
        "convenio": "3214586088",  # Convenio Efecty
        "titular":  "Dessert Sacré"  # Titular
    }
}

@app.route("/api/datos-pago")  # API para obtener datos de pago
def datos_pago():
    metodo = request.args.get("metodo", "nequi")  # Método por defecto nequi
    return jsonify({"datos": DATOS_PAGO.get(metodo)})  # Retorna datos del método

# Diccionario para almacenar pedidos (en memoria, no persistente)
pedidos_guardados = {}
# Lista para almacenar calificaciones (en memoria, no persistente)
calificaciones = []
@app.route("/api/crear-pedido", methods=["POST"])  # API para crear pedido
def crear_pedido():
    if not session.get('usuario'):  # Si no hay usuario
        return jsonify({"error": "No autenticado"}), 401

    try:
        data = request.get_json()  # Obtiene datos JSON
        cart = _get_cart()  # Obtiene carrito

        if not cart:  # Si carrito vacío
            return jsonify({"error": "Carrito vacío"}), 400

        total = sum(item['precio'] * item['qty'] for item in cart)  # Calcula total
        ref   = f"PED-{uuid.uuid4().hex[:8].upper()}"  # Genera referencia única

        # Guarda pedido en diccionario
        pedidos_guardados[ref] = {
            "total":    total,
            "metodo":   data.get("metodo"),  # Método de pago
            "nombre":   data.get("nombre"),  # Nombre del comprador
            "email":    data.get("email"),  # Email
            "telefono": data.get("telefono"),  # Teléfono
            "fecha":    datetime.now().strftime("%Y-%m-%d %H:%M"),  # Fecha
            "productos": [item["nombre"] for item in cart]  # ← lista de productos del carrito
        }

        session.pop("carrito", None)  # Limpia carrito

        return jsonify({"referencia": ref, "total": total})  # Retorna referencia y total

    except Exception as e:
        print("ERROR CREAR PEDIDO:", e)  # Imprime error
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500  # Retorna error

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

    return render_template('perfil.html',  # Renderiza perfil
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
    return render_template("inicio1.html")

@app.route('/menu')  # Ruta del menú (público)
def menu():
    return render_template('menu.html')

@app.route('/menuU')  # Ruta del menú (usuario)
def menuU():
    return render_template('menu1.html')

@app.route('/sobrenosotros')  # Ruta "Sobre nosotros" (público)
def sobrenosotros():
    return render_template('sobrenosotros.html')

@app.route('/sobrenosotrosU')  # Ruta "Sobre nosotros" (usuario)
def sobrenosotrosU():
    return render_template('sobrenosotros1.html')

@app.route('/redes')  # Ruta de redes sociales (público)
def redes():
    return render_template('redes.html')

@app.route('/redesU')  # Ruta de redes sociales (usuario)
def redesU():
    return render_template('redes1.html')

@app.route('/pedidos') #Ruta para pedidos (usuario)
def pedidos():
    if not session.get('usuario'): #si no se ha iniciado sesion
        return redirect('/login') #redirige a inicio de sesion
    return render_template('pedidos1.html', #si se ha iniciado sesion
        usuario=session['usuario'], #Guarda datos del usuario
        pedidos=pedidos_guardados #Guarda los pedidos realizados
    )

@app.route('/panaderia')  # Ruta de panadería (público)
def panaderia():
    return render_template('panaderia.html')

@app.route('/panaderiaU')  # Ruta de panadería (usuario)
def panaderiaU():
    return render_template('panaderia1.html')

@app.route('/pasteleria')  # Ruta de pastelería (público)
def pasteleria():
    return render_template('pasteleria.html')

@app.route('/pasteleriaU')  # Ruta de pastelería (usuario)
def pasteleriaU():
    return render_template('pasteleria1.html')

@app.route('/reposteria')  # Ruta de repostería (público)
def reposteria():
    return render_template('reposteria.html')

@app.route('/reposteriaU')  # Ruta de repostería (usuario)
def reposteriaU():
    return render_template('reposteria1.html')

@app.route('/bebidas')  # Ruta de bebidas (público)
def bebidas():
    return render_template('bebidas.html')

@app.route('/bebidasU')  # Ruta de bebidas (usuario)
def bebidasU():
    return render_template('bebidas1.html')

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
# EJECUCIÓN DE LA APLICACIÓN
# ====================================
if __name__ == "__main__":  # Si se ejecuta directamente
    crear_tabla()  # Crea las tablas si no existen
    app.run(host="0.0.0.0", port=5000, debug=True)  # Ejecuta el servidor en modo debug