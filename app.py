from flask import Flask, request, render_template, jsonify, redirect, session, flash, url_for #pip install flask
import psycopg2 #pip install psycopg2
from psycopg2.extras import RealDictCursor #pip install psycopg2-binary
from flask_mail import Mail, Message 
import random
import uuid
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from config import Config
import traceback
import os
from dotenv import load_dotenv #pip install python-dotenv
import stripe
import smtplib
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer #pip install reportlab
from reportlab.lib.styles import getSampleStyleSheet
from flask import send_file
import io
load_dotenv()


# ------------------------------------
# CONFIG GENERAL
# ------------------------------------
app = Flask(__name__)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
app.secret_key = "clave_super_secreta"
app.config.from_object(Config)
stripe.api_key = Config.STRIPE_SECRET_KEY

"""DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'port': os.getenv('DB_PORT')
}"""

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

# Carpeta donde se guardan físicamente los comprobantes subidos
UPLOAD_FOLDER_COMPROBANTES = os.path.join("static", "uploads", "comprobantes")
os.makedirs(UPLOAD_FOLDER_COMPROBANTES, exist_ok=True)

# ------------------------------------
# CONFIG SMTP GMAIL
# ------------------------------------
app.config.from_object(Config)
mail = Mail(app)


def enviar_codigo(correo_destino, codigo):

    msg = Message(
        "Código de verificación",
        sender=app.config["MAIL_USERNAME"],
        recipients=[correo_destino]
    )

    msg.body = f"Tu código de verificación es: {codigo}"

    try:
        mail.send(msg)
        print("Correo enviado ")
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
   
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id SERIAL PRIMARY KEY,
            referencia VARCHAR(30) UNIQUE NOT NULL,
            correo VARCHAR(150) REFERENCES registro(correo),
            cliente VARCHAR(150) NOT NULL,
            telefono VARCHAR(20),
            direccion TEXT,
            metodo VARCHAR(30),
            total NUMERIC(10,2),
            estado VARCHAR(30),
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS detalle_pedido (
            id SERIAL PRIMARY KEY,
            pedido_id INTEGER REFERENCES pedidos(id) ON DELETE CASCADE,
            producto VARCHAR(150),
            cantidad INTEGER,
            precio NUMERIC(10,2)
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(150) NOT NULL,
            categoria VARCHAR(50),
            descripcion TEXT,
            precio NUMERIC(10,2),
            imagen VARCHAR(255),
            disponible BOOLEAN DEFAULT TRUE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS calificaciones (
            id SERIAL PRIMARY KEY,
            correo VARCHAR(150) REFERENCES registro(correo),
            producto VARCHAR(150),
            estrellas INTEGER CHECK (estrellas BETWEEN 1 AND 5),
            comentario TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS comprobantes (
            id SERIAL PRIMARY KEY,
            pedido_id INTEGER REFERENCES pedidos(id) ON DELETE CASCADE,
            archivo VARCHAR(255),
            estado VARCHAR(30),
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transacciones (
            id SERIAL PRIMARY KEY,
            pedido_id INTEGER REFERENCES pedidos(id) ON DELETE CASCADE,
            payment_intent VARCHAR(100),
            estado VARCHAR(30),
            monto NUMERIC(10,2),
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
# PEDIDOS: HELPER PARA LEER DESDE LA BASE DE DATOS
# ====================================
def obtener_pedidos(correo=None):
    """
    Lee los pedidos desde las tablas 'pedidos' y 'detalle_pedido' de la BD
    y los entrega como un diccionario {referencia: {...}} con la MISMA forma
    que antes tenía 'pedidos_guardados' en memoria, para no tener que tocar
    las plantillas (perfil.html, pedidos1.html, admin/pedidos.html, etc).

    Si se pasa 'correo', solo trae los pedidos de ese usuario.
    """
    conexion = get_db_connection()
    if not conexion:
        return {}

    cursor = conexion.cursor(cursor_factory=RealDictCursor)

    base_sql = """
        SELECT p.id, p.referencia, p.correo, p.cliente, p.telefono,
               p.direccion, p.metodo, p.total, p.estado, p.fecha,
               COALESCE(
                   array_agg(d.producto) FILTER (WHERE d.producto IS NOT NULL),
                   '{}'
               ) AS productos
        FROM pedidos p
        LEFT JOIN detalle_pedido d ON d.pedido_id = p.id
    """

    if correo:
        cursor.execute(base_sql + " WHERE p.correo = %s GROUP BY p.id ORDER BY p.fecha DESC", (correo,))
    else:
        cursor.execute(base_sql + " GROUP BY p.id ORDER BY p.fecha DESC")

    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    pedidos = {}
    for f in filas:
        pedidos[f["referencia"]] = {
            "productos": f["productos"],
            "fecha":     f["fecha"].strftime("%Y-%m-%d %H:%M") if f["fecha"] else "",
            "metodo":    f["metodo"],
            "total":     float(f["total"]) if f["total"] is not None else 0,
            "estado":    f["estado"],
            "email":     f["correo"],
            "nombre":    f["cliente"],
            "telefono":  f["telefono"],
            "direccion": f["direccion"]
        }
    return pedidos

def obtener_calificaciones(correo=None):
    """
    Lee las calificaciones desde la tabla 'calificaciones' de la BD
    (antes vivían solo en una lista en memoria, por eso la tabla
    aparecía vacía y el admin mostraba datos inconsistentes).

    Se une con 'registro' para el nombre del cliente y con 'productos'
    para traer la imagen del producto calificado (si existe un producto
    con ese mismo nombre en la tabla productos).
    """
    conexion = get_db_connection()
    if not conexion:
        return []

    cursor = conexion.cursor(cursor_factory=RealDictCursor)

    base_sql = """
        SELECT cal.correo, cal.producto, cal.estrellas, cal.comentario, cal.fecha,
               reg.primer_nombre, reg.primer_apellido,
               prod.imagen AS imagen
        FROM calificaciones cal
        LEFT JOIN registro reg ON reg.correo = cal.correo
        LEFT JOIN productos prod ON prod.nombre = cal.producto
    """

    if correo:
        cursor.execute(base_sql + " WHERE cal.correo = %s ORDER BY cal.fecha DESC", (correo,))
    else:
        cursor.execute(base_sql + " ORDER BY cal.fecha DESC")

    filas = cursor.fetchall()
    cursor.close()
    conexion.close()

    resultado = []
    for f in filas:
        nombre_cliente = f"{f['primer_nombre'] or ''} {f['primer_apellido'] or ''}".strip() or f["correo"]
        resultado.append({
            "cliente":    nombre_cliente,
            "email":      f["correo"],
            "producto":   f["producto"],
            "estrellas":  f["estrellas"],
            "comentario": f["comentario"],
            "fecha":      f["fecha"].strftime("%Y-%m-%d %H:%M") if f["fecha"] else "",
            "imagen":     f["imagen"]  # None si el producto no existe en la tabla productos
        })
    return resultado

# ====================================
# RUTAS DE ADMINISTRADOR
# ====================================
@app.route("/admin")  # Ruta del panel admin
def admin():
    if not session.get("admin"):  # Si no es admin
        flash("Acceso solo para administradores", "danger") # Muestra mensaje de error
        return redirect("/login") # Redirige al login

    # Conecta a BD y obtiene todos los usuarios
    conexion = get_db_connection()
    if not conexion:  # Verifica que la conexión fue exitosa
        flash("Error de conexión a la base de datos", "danger") # Muestra mensaje de error
        return redirect("/login") # Redirige al login si hay error de conexión

    cursor = conexion.cursor(cursor_factory=RealDictCursor) # Crea cursor con resultados como diccionarios
    
    # Usuarios
    cursor.execute("SELECT * FROM registro")  # Obtiene todos los usuarios
    usuarios = cursor.fetchall() # Guarda los usuarios obtenidos en una variable
    
    # Mensajes
    cursor.execute("""
        SELECT *
        FROM mensajes
        ORDER BY fecha DESC
    """) # Obtiene todos los mensajes ordenados por fecha
    mensajes = cursor.fetchall() # Guarda los mensajes obtenidos en una variable
    
    print("MENSAJES:", len(mensajes))
    print(mensajes)
    
    
    cursor.close() # Cierra el cursor
    conexion.close() # Cierra la conexión a la base de datos
    
    # Pedidos desde la base de datos (antes venía de pedidos_guardados en memoria)
    pedidos_guardados = obtener_pedidos()

    # Calcula total de ventas
    total_ventas = sum(p["total"] for p in pedidos_guardados.values()) # Calcula total de ventas sumando los totales de los pedidos guardados
    


    # Renderiza la plantilla admin con datos
    return render_template("admin/dashboard.html", # Renderiza plantilla de dashboard del admin
        usuarios=usuarios, # Pasa los usuarios obtenidos de la BD
        pedidos=pedidos_guardados, # Pasa los pedidos guardados (desde la BD)
        total_ventas=total_ventas, # Pasa el total de ventas
        calificaciones=obtener_calificaciones(), # Pasa todas las calificaciones (desde la BD)
        mensajes=mensajes, # Pasa los mensajes obtenidos de la BD
        now=datetime.now().strftime("%d %b %Y")   # Fecha actual para mostrar en el dashboard
    )

@app.route("/admin/pedidos")  # Ruta de pedidos en admin
def admin_pedidos():
    if not session.get("admin"): # Si no es admin
        return redirect("/login") # Redirige al login

    # Pedidos desde la base de datos (antes venía de pedidos_guardados en memoria)
    pedidos_guardados = obtener_pedidos()

    total_ventas = sum(p["total"] for p in pedidos_guardados.values()) # Calcula total de ventas

    return render_template("admin/pedidos.html", # Renderiza plantilla de pedidos
        pedidos=pedidos_guardados, # Pasa los pedidos guardados (desde la BD)
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
        calificaciones=obtener_calificaciones()  # Pasa todas las calificaciones (desde la BD)
    )

@app.route("/admin/mensajes")
def admin_mensajes():

    if not session.get("admin"):
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT *
        FROM mensajes
        ORDER BY fecha DESC
    """)

    mensajes = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "admin/mensajes.html",
        mensajes=mensajes
    )

# ====================================
# RUTA Y TABLA DE MENSAJES
# ====================================
def crear_tabla_mensajes():
    
    conn = get_db_connection()

    if conn is None:
        print("No se pudo crear tabla mensajes: sin conexión BD")
        return

    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS mensajes (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100),
                correo VARCHAR(150),
                mensaje TEXT,
                leido BOOLEAN DEFAULT FALSE,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()

        cur.close()
        conn.close()

        print("Tabla mensajes lista")

    except Exception as e:
        print("Error creando tabla mensajes:", e)

# ---- FUNCION PARA ENVIAR CORREO -----

def enviar_mensaje_contacto(nombre, apellido, email, mensaje):

    cuerpo = f"""
Nuevo mensaje recibido desde Dessert Sacré

Nombre: {nombre} {apellido}
Correo: {email}

Mensaje:
{mensaje}
"""

    msg = Message(
        subject=f"Nuevo mensaje de {nombre}",
        sender=app.config["MAIL_USERNAME"],
        recipients=[app.config["MAIL_USERNAME"]]
    )

    msg.body = cuerpo

    try:
        mail.send(msg)
        print("Mensaje enviado correctamente")
        return True

    except Exception as e:
        print("Error enviando mensaje:", e)
        return False

#-----RUTA PARA GUARDAR MENSAJES-----
@app.route('/enviar_mensaje', methods=['POST'])
def enviar_mensaje():
    print("RUTA ENVIAR_MENSAJE EJECUTADA")

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

        print("ERROR INSERTANDO MENSAJE:")
        print(repr(e))

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

#-----RUTA DE MENSAJES PARA VER EN DASHBOARD-----
@app.route("/admin/mensaje/<int:id>")
def ver_mensaje(id):

    if not session.get("admin"):
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT *
        FROM mensajes
        WHERE id = %s
    """, (id,))

    mensaje = cur.fetchone()

    cur.close()
    conn.close()

    return render_template(
        "admin/ver_mensaje.html",
        mensaje=mensaje
    )


#====================================
# RUTAS PARA REPORTES PDF DE ADMINISTRADOR
#====================================

@app.route("/admin/generar_reporte", methods=["POST"])
def generar_reporte():

    if not session.get("admin"):
        return redirect("/login")

    tipo = request.form.get("tipo_reporte")

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(buffer)

    styles = getSampleStyleSheet()

    contenido = []

    contenido.append(
        Paragraph(
            f"Reporte de {tipo.capitalize()}",
            styles["Title"]
        )
    )

    contenido.append(Spacer(1, 20))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # USUARIOS
    if tipo == "usuarios":

        cur.execute("""
            SELECT *
            FROM registro
            ORDER BY id
        """)

        usuarios = cur.fetchall()

        for u in usuarios:

            contenido.append(
                Paragraph(
                    f"""
                    ID: {u['id']}<br/>
                    Nombre: {u['primer_nombre']} {u['primer_apellido']}<br/>
                    Correo: {u['correo']}<br/>
                    Teléfono: {u['telefono']}
                    """,
                    styles["BodyText"]
                )
            )

            contenido.append(Spacer(1,10))

    # MENSAJES
    elif tipo == "mensajes":

        cur.execute("""
            SELECT *
            FROM mensajes
            ORDER BY fecha DESC
        """)

        mensajes = cur.fetchall()

        for m in mensajes:

            contenido.append(
                Paragraph(
                    f"""
                    Nombre: {m['nombre']} {m['apellido']}<br/>
                    Correo: {m['email']}<br/>
                    Mensaje: {m['mensaje']}<br/>
                    Fecha: {m['fecha']}
                    """,
                    styles["BodyText"]
                )
            )

            contenido.append(Spacer(1,10))

    # PEDIDOS (ahora desde la base de datos)
    elif tipo == "pedidos":

        pedidos_reporte = obtener_pedidos()

        for ref, p in pedidos_reporte.items():

            contenido.append(
                Paragraph(
                    f"""
                    Referencia: {ref}<br/>
                    Cliente: {p['nombre']}<br/>
                    Correo: {p['email']}<br/>
                    Productos: {', '.join(p['productos'])}<br/>
                    Total: ${p['total']:,.0f}<br/>
                    Método: {p['metodo']}<br/>
                    Estado: {p['estado']}<br/>
                    Fecha: {p['fecha']}
                    """,
                    styles["BodyText"]
                )
            )

            contenido.append(Spacer(1,10))

    # CALIFICACIONES
    elif tipo == "calificaciones":

        for c in obtener_calificaciones():

            contenido.append(
                Paragraph(
                    f"""
                    Cliente: {c['cliente']}<br/>
                    Producto: {c['producto']}<br/>
                    Estrellas: {c['estrellas']}<br/>
                    Comentario: {c['comentario']}<br/>
                    Fecha: {c['fecha']}
                    """,
                    styles["BodyText"]
                )
            )

            contenido.append(Spacer(1,10))

    cur.close()
    conn.close()

    doc.build(contenido)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"reporte_{tipo}.pdf",
        mimetype="application/pdf"
    )

    
# ====================================
# FUNCIONES Y RUTAS DEL CARRITO DE COMPRAS
# ====================================
def _get_cart():  # Función privada para obtener el carrito de la sesión
    return session.get("carrito", [])  # Retorna lista de items o lista vacía

def _save_cart(cart):  # Función privada para guardar el carrito en sesión
    session["carrito"] = cart  # Actualiza la sesión
    session.modified = True

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
    
    return redirect('/pasarela')  # Redirige a pasarela
@app.route("/vaciar_carrito", methods=["POST"])
def vaciar_carrito():
    session.pop("carrito", None)
    return jsonify({"ok": True})

@app.context_processor
def inject_cart_count():
    cart = session.get("carrito", [])
    cart_count = sum(item.get("qty", 0) for item in cart)
    return dict(cart_count=cart_count)
# ====================================
# PASARELA DE PAGOS CON STRIPE ELEMENTS
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
            amount              = int(total ),  # COP: cantidad en centavos
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

    usuario = session.get("usuario")
    cart = _get_cart()

    payment_intent = request.args.get("payment_intent")

    print("PAYMENT INTENT:", payment_intent)  # prueba


    if usuario and cart:

        total = sum(item["precio"] * item["qty"] for item in cart)

        referencia = f"PED-{uuid.uuid4().hex[:8].upper()}"

        conexion = get_db_connection()
        cursor = conexion.cursor()

        cursor.execute("""
        INSERT INTO pedidos
        (referencia, correo, cliente, telefono, direccion, metodo, total, estado)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """, (
            referencia,
            usuario["email"],
            usuario["nombre"],
            usuario["telefono"],
            usuario["direccion"],
            "Tarjeta",
            total,
            "Pagado"
        ))

        pedido_id = cursor.fetchone()[0]


        for item in cart:
            cursor.execute("""
            INSERT INTO detalle_pedido
            (pedido_id, producto, cantidad, precio)
            VALUES (%s,%s,%s,%s)
            """, (
                pedido_id,
                item["nombre"],
                item["qty"],
                item["precio"]
            ))


        cursor.execute("""
        INSERT INTO transacciones
        (pedido_id, payment_intent, estado, monto)
        VALUES (%s,%s,%s,%s)
        """, (
            pedido_id,
            payment_intent,
            "Pagado",
            total
        ))


        conexion.commit()
        cursor.close()
        conexion.close()


    session.pop("carrito", None)

    flash("¡Pago realizado con éxito!", "success")

    return redirect("/inicioU")

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Webhook para eventos de Stripe
    Valida la firma y procesa eventos de pago
    """
    import hmac
    import hashlib
    
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

        
    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        print(f" Pago fallido: {payment_intent['id']}")
        
    elif event["type"] == "charge.refunded":
        charge = event["data"]["object"]
        print(f" Reembolso procesado: {charge['id']}")
    
    return jsonify({"status": "received"}), 200




DATOS_PAGO = {
    "nequi":  {"numero": "123456789", "titular": "Dessert Sacré"},
    "banco":  {"banco": "BANCOLOMBIA", "numero": "123456789",
               "tipo": "Ahorros", "titular": "Dessert Sacré", "cedula": "3214586088"},
    "efecty": {"convenio": "3214586088", "titular": "Dessert Sacré"}
}

@app.route("/api/datos-pago")
def datos_pago():
    metodo = request.args.get("metodo", "nequi")
    return jsonify({"datos": DATOS_PAGO.get(metodo)})

# Las listas en memoria de pedidos y calificaciones ya no se usan: ahora
# viven en las tablas 'pedidos'/'detalle_pedido' y 'calificaciones' de la
# base de datos (ver funciones obtener_pedidos y obtener_calificaciones).


@app.route("/api/crear-pedido", methods=["POST"])
def crear_pedido():
    if not session.get('usuario'):
        return jsonify({"error": "No autenticado"}), 401

    try:
        data = request.get_json()
        cart = _get_cart()

        if not cart:
            return jsonify({"error": "Carrito vacío"}), 400

        total   = sum(item['precio'] * item['qty'] for item in cart)
        ref     = f"PED-{uuid.uuid4().hex[:8].upper()}"
        usuario = session["usuario"]

        # Guarda el pedido y su detalle en la base de datos
        conexion = get_db_connection()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO pedidos
            (referencia, correo, cliente, telefono, direccion, metodo, total, estado)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            ref,
            data.get("email") or usuario.get("email"),
            data.get("nombre") or usuario.get("nombre"),
            data.get("telefono") or usuario.get("telefono"),
            usuario.get("direccion"),
            data.get("metodo"),
            total,
            "Pendiente"
        ))

        pedido_id = cursor.fetchone()[0]

        for item in cart:
            cursor.execute("""
                INSERT INTO detalle_pedido
                (pedido_id, producto, cantidad, precio)
                VALUES (%s,%s,%s,%s)
            """, (
                pedido_id,
                item["nombre"],
                item["qty"],
                item["precio"]
            ))

        conexion.commit()
        cursor.close()
        conexion.close()

        # ENVIAR CORREO AL DUEÑO
        msg = Message(
            subject=f"Nuevo pedido {ref}",
            sender=app.config['MAIL_USERNAME'],
            recipients=["dessertsacre@gmail.com"]
        )

        msg.body = f"""
Nuevo pedido registrado

Referencia: {ref}
Cliente: {data.get('nombre')}
Correo: {data.get('email')}
Teléfono: {data.get('telefono')}
Total: ${total:,.0f} COP
Método: {data.get('metodo')}
"""

        mail.send(msg)

        session.pop("carrito", None)

        return jsonify({
            "referencia": ref,
            "total": total
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/calificar", methods=["POST"])  # API para guardar calificación
def calificar():
    if not session.get('usuario'):  # Si no hay usuario autenticado
        return jsonify({"error": "No autenticado"}), 401

    try:
        data    = request.get_json()       # Obtiene datos JSON del frontend
        usuario = session.get('usuario')   # Obtiene el usuario de la sesión

        conexion = get_db_connection()
        if not conexion:
            return jsonify({"error": "Error de conexión a la base de datos"}), 500

        cursor = conexion.cursor()
        cursor.execute("""
            INSERT INTO calificaciones (correo, producto, estrellas, comentario)
            VALUES (%s,%s,%s,%s)
        """, (
            usuario["email"],
            data.get("producto"),
            int(data.get("estrellas")),
            data.get("comentario")
        ))
        conexion.commit()
        cursor.close()
        conexion.close()

        return jsonify({"success": True})  # Retorna éxito

    except Exception as e:
        print("ERROR CALIFICAR:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
@app.route("/subir-comprobante", methods=["POST"])
def subir_comprobante():

    try:

        archivo = request.files.get("comprobante")

        if not archivo:
            return jsonify({
                "ok": False,
                "error": "No llegó archivo"
            })

        usuario = session.get("usuario")

       
        cart = _get_cart()

        total = sum(item["precio"] * item["qty"] for item in cart)

        ref = f"PED-{uuid.uuid4().hex[:8].upper()}"

        # Lee el archivo UNA sola vez: se usa para guardarlo en disco
        # y también para adjuntarlo en el correo
        contenido_archivo = archivo.read()
        nombre_seguro      = secure_filename(archivo.filename) or f"{ref}.dat"
        nombre_guardado     = f"{ref}_{nombre_seguro}"
        ruta_disco           = os.path.join(UPLOAD_FOLDER_COMPROBANTES, nombre_guardado)

        with open(ruta_disco, "wb") as f:
            f.write(contenido_archivo)

        ruta_relativa = f"uploads/comprobantes/{nombre_guardado}"

        conexion = get_db_connection()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO pedidos
            (referencia, correo, cliente, telefono, direccion, metodo, total, estado)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            ref,
            usuario["email"],
            usuario["nombre"],
            usuario["telefono"],
            usuario["direccion"],
            request.form.get("metodo"),
            total,
            "Pago realizado"
        ))

        pedido_id = cursor.fetchone()[0]

        for item in cart:
            cursor.execute("""
                INSERT INTO detalle_pedido
                (pedido_id, producto, cantidad, precio)
                VALUES (%s,%s,%s,%s)
            """, (
                pedido_id,
                item["nombre"],
                item["qty"],
                item["precio"]
            ))

        # Registra el comprobante subido en la base de datos
        cursor.execute("""
            INSERT INTO comprobantes
            (pedido_id, archivo, estado)
            VALUES (%s,%s,%s)
        """, (
            pedido_id,
            ruta_relativa,
            "Pendiente de revisión"
        ))

        conexion.commit()
        cursor.close()
        conexion.close()

        msg = Message(
            subject="Nuevo comprobante de pago",
            sender=app.config["MAIL_USERNAME"],
            recipients=["dessertsacre@gmail.com"]
        )

        msg.body = f"""
Nuevo comprobante recibido

Cliente: {usuario["nombre"]}
Correo: {usuario["email"]}
Teléfono: {usuario["telefono"]}
Dirección: {usuario["direccion"]}

"""

        msg.attach(
            archivo.filename,
            archivo.content_type,
            contenido_archivo
        )

        mail.send(msg)

       
        session.pop("carrito", None)
        session.modified = True
        

        return jsonify({"ok": True})

    except Exception as e:

        print("ERROR:", str(e))

        return jsonify({
            "ok": False,
            "error": str(e)
        })
        
        
# ====================================
# RUTA DE PERFIL
# ====================================
@app.route('/perfil')  # ← agrega esta línea
def perfil():
    if not session.get('usuario'):  # Si no hay usuario
        return redirect('/login')  # Redirige al login

    correo_usuario = session['usuario']["email"]

    # Pedidos del usuario actual, leídos desde la base de datos
    mis_pedidos = obtener_pedidos(correo_usuario)

    # Calificaciones del usuario actual, leídas desde la base de datos
    mis_calificaciones = obtener_calificaciones(correo_usuario)

    return render_template('users/perfil.html',  # Renderiza perfil
        usuario=session['usuario'],        # Pasa datos del usuario
        pedidos=mis_pedidos,               # Pasa pedidos (desde la BD, ya filtrados)
        calificaciones=mis_calificaciones  # Pasa calificaciones del usuario (desde la BD)
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

    correo_usuario = session['usuario']["email"]

    return render_template('users/pedidos1.html', #si se ha iniciado sesion
        usuario=session['usuario'], #Guarda datos del usuario
        pedidos=obtener_pedidos(correo_usuario) #Pedidos del usuario, desde la BD
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
# EJECUCIÓN DE LA APLICACIÓN
# ====================================
if __name__ == "__main__":  # Si se ejecuta directamente
    crear_tabla()  # Crea las tablas si no existen
    app.run(host="0.0.0.0", port=5000, debug=True)  # Ejecuta el servidor en modo debug