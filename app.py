from flask import Flask, request, render_template,jsonify, redirect, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
import random
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
        'dbname':"Dessert_Sacre",
        'user':"postgres",
        'password': "123456",
        'port': 5432
    }
def  get_db_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print("Error BD:", e)
        return None



# CONFIG SMTP GMAIL

EMAIL_USER = app.config["EMAIL_USER"]
EMAIL_PASS = app.config["EMAIL_PASS"]  # Contraseña de aplicación Gmail


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

        
# TABLA DE REGISTRO Y RECUPERACION
# Crea la tabla `registro` en la base de datos si no existe     
def crear_tabla():
    # Solicita una conexión a la base de datos
    conexion = get_db_connection()
    if conexion:
        # Crea un cursor para ejecutar la sentencia SQL
        cursor = conexion.cursor()
        # Ejecuta la sentencia SQL para crear la tabla
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
        
        # Inserta datos y cierra cursor y conexión
        conexion.commit()
        cursor.close()
        conexion.close()
        
        
        
# INDEX
# ------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# Registro

@app.route("/register", methods=["GET", "POST"])
def register():
    # Reiniciar sesiones temporales
    session.pop("intentos_reenvio", None)
    session.pop("correo_verificacion", None)
    return render_template("register.html")

@app.route('/guardar', methods=['POST'])   
def guardar(): 
    try:
        #  Obtener conexión a la base de datos
        conexion = get_db_connection()
        if conexion is None:
            # Si no hay conexión, devolver error
            return jsonify(error="Error: No se pudo conectar a la base de datos")

        # Procesar datos del formulario (solo si es POST)
        if request.method == "POST":
            # Capturar valores enviados desde el formulario
            primer_nombre = request.form.get("primer_nombre", "").strip()
            segundo_nombre = request.form.get("segundo_nombre", "").strip()
            primer_apellido = request.form.get("primer_apellido", "").strip()
            segundo_apellido = request.form.get("segundo_apellido", "").strip()
            correo = request.form.get("correo", "").strip()
            password = request.form.get("password", "").strip()
            telefono = request.form.get("telefono", "").strip()
            direccion = request.form.get("direccion", "").strip()

            # Validar campos obligatorios
            if not primer_nombre or not primer_apellido or not correo or not password:
                return jsonify(error="Faltan datos obligatorios")

            #Crear cursor para ejecutar consultas
            cursor = conexion.cursor(cursor_factory=RealDictCursor)

            # Validar si el correo ya existe en la tabla
            cursor.execute("SELECT id FROM registro WHERE correo=%s", (correo,))
            if cursor.fetchone():
                flash("El correo ya está registrado. Inicia sesión.", "warning")
                session["correo_login_auto"] = correo
                return redirect("/login")

            # Encriptar la contraseña
            password_hash = generate_password_hash(password)

            # Generar código de verificación aleatorio
            codigo = str(random.randint(100000, 999999))

            # Insertar nuevo usuario en la tabla
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

            # Confirmar cambios en la base de datos
            conexion.commit()

            #  Enviar código de verificación por correo
            if not enviar_codigo(correo, codigo):
                flash("Error enviando correo")

            # Guardar correo en sesión para verificar después
            session["correo_verificacion"] = correo

            # Cerrar cursor y conexión
            cursor.close()
            conexion.close()

            # Redirigir a la página de verificación
            return redirect("/verify")

    except Exception as e:
        # Manejo de errores: imprimir en consola y devolver mensaje JSON
        print("\n ERROR SQL:")
        print(e)
        traceback.print_exc()
        return jsonify(error="Error al procesar la solicitud")



# VERIFICACION
@app.route("/verify", methods=["GET", "POST"])
def verify():
    correo = session.get("correo_verificacion")

    if not correo:
        flash("No hay correo para verificar", "danger")
        return redirect("/login")

    # PASAR LOS INTENTOS A LA PLANTILLA
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

        codigo_real = result["codigo_verificacion"]

        if codigo_ingresado == codigo_real:
            cursor.execute("UPDATE registro SET verificado=TRUE WHERE correo=%s", (correo,))
            conexion.commit()
            cursor.close()
            conexion.close()

            flash("Correo verificado con éxito", "success")
            session.pop("correo_verificacion", None)
            session.pop("intentos_reenvio", None)
            return redirect("/inicio")
        else:
            flash("El código ingresado es incorrecto", "danger")
            return render_template("verify.html", redirect_login=False, intentos=intentos)

    #Este return final asegura que siempre haya respuesta en caso de GET
    return render_template("verify.html", redirect_login=False, intentos=intentos)

#Reenvio de código

@app.route("/reenviar_codigo")
def reenviar_codigo():
    correo = session.get("correo_verificacion")

    if not correo:
        flash("No hay correo para verificar", "danger")
        return redirect("/login")

    # Contador de reenvíos
    intentos = session.get("intentos_reenvio", 0)

    if intentos >= 3:
        flash("Límite de reenvíos alcanzado. Verifica tu correo o regístrate de nuevo.", "warning")
        return redirect("/verify")

    # Generar y guardar nuevo código
    nuevo_codigo = str(random.randint(100000, 999999))

    conexion = get_db_connection()
    cursor = conexion.cursor(cursor_factory=RealDictCursor)
    cursor.execute("UPDATE registro SET codigo_verificacion=%s WHERE correo=%s",
                   (nuevo_codigo, correo))
    conexion.commit()
    cursor.close()
    conexion.close()

    # Aumentar contador
    session["intentos_reenvio"] = intentos + 1

    # Enviar código
    if not enviar_codigo(correo,nuevo_codigo):
        flash("Error enviando correo")

    flash("Código reenviado. Revisa tu correo.", "success")
    return redirect("/verify")



# Ruta para mostrar el formulario de inicio de sesión
ADMIN_EMAIL = "dessertsacre@gmail.com"
ADMIN_PASSWORD = "LauraJuanDaAngelicaSalo"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form["correo"]
        password = request.form["password"]

        # LOGIN ADMINISTRADOR
        if correo == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["admin"] = True
            session["usuario"] = "Administrador"
            flash("Bienvenido administrador", "success")
            return redirect("/admin")

        # LOGIN USUARIO NORMAL
        conexion = get_db_connection()
        cursor = conexion.cursor(cursor_factory=RealDictCursor)

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

        session["usuario"] = usuario["primer_nombre"] + " " + usuario["primer_apellido"]
        flash("Inicio de sesión exitoso", "success")
        return redirect("/inicio")

    redir_verificar = session.pop("redir_verificar", None)
    correo_auto = session.pop("correo_login_auto", "")

    return render_template("login.html", redir_verificar=redir_verificar, correo_auto=correo_auto)


# ------------------------------------
# RUTA PARA ADMINISTRADOR
# ------------------------------------
@app.route("/admin")
def admin():
    if not session.get("admin"):
        flash("Acceso solo para administradores", "danger")
        return redirect("/login")

    return render_template("admin/dashboard.html")


# Rutas para ver pedidos(solo para admin)
@app.route("/admin/pedidos")
def admin_pedidos():
    if not session.get("admin"):
        return redirect("/login")

    return render_template("admin/pedidos.html")



#DASHBOARD

@app.route("/dashboard")
def dashboard():
    if not session.get("usuario"):
        return redirect("/login")
    return render_template("dashboard.html", usuario=session["usuario"])


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# # ------------------------------------
# # LOGOUT
# # ------------------------------------
# @app.route("/logout")
# def logout():
#     session.clear()
#     return redirect("/")

# # ------------------------------------
# # NAVBAR
# # ------------------------------------

@app.route("/iniciosesion")
def inicioS():
    usuario = session.get("usuario")
    return render_template("inicio1.html", usuario=usuario)

@app.route("/inicio")
def inicio():
    return render_template("inicio.html")

@app.route('/menu')
def menu():
    return render_template('menu.html')

@app.route('/sobrenosotros')
def sobrenosotros():
    return render_template('sobrenosotros.html')


@app.route('/redes')
def redes():
    return render_template('redes.html')


# rutas de cuenta
@app.route('/perfil')
def perfil():
    return render_template('perfil.html')

@app.route('/pedidos')
def pedidos():
    return render_template('pedidos.html')


#Carrito de compras
@app.route("/carrito") 
def carrito(): 
    return render_template("carrito.html")


#OLVIDO SU CONTRASEÑA?

#Ruta para solicitar la recuperación
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

            # Generar código de recuperación
            codigo = str(random.randint(100000, 999999))
            expiracion = datetime.now() + timedelta(minutes=15)
            cursor.execute("""
                INSERT INTO recuperacion (correo, codigo, expiracion, usado)
                VALUES (%s, %s, %s, FALSE)
            """, (correo, codigo, expiracion))
            conexion.commit()

        conexion.close()
        
        # Enviar código por correo
        enviar_codigo(correo, codigo)
        flash("Código enviado a tu correo.", "success")
        session["correo_recuperar"] = correo
        
        return redirect("/reset-code")

    #Este return final cubre el caso GET
    return render_template("forgot.html")



# Crear vista para ingresar el código
@app.route("/reset-code", methods=["GET", "POST"])
def reset_code():
    # Recuperar el correo guardado en sesión
    correo = session.get("correo_recuperar")
    if not correo:
        flash("Primero ingresa tu correo", "warning")
        return redirect("/forgot")

    if request.method == "POST":
        # Obtener el código ingresado en el formulario
        codigo_ingresado = request.form.get("codigo", "").strip()

        # Conexión a la base de datos
        conexion = get_db_connection()
        if not conexion:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect("/reset-code")
        
        # Usar el cursor dentro del bloque with
        with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
            # Buscar el código en la tabla de recuperación
            cursor.execute("""
                SELECT * FROM recuperacion
                WHERE correo=%s AND codigo=%s AND usado=FALSE
                ORDER BY expiracion DESC
                LIMIT 1
            """, (correo, codigo_ingresado))
            resultado = cursor.fetchone()
            
            # Validar si existe el código
            if not resultado:
                flash("Código incorrecto o ya usado.", "danger")
                return redirect("/reset-code")
        
            # Validar si el código expiró
            if datetime.now() > resultado["expiracion"]:
                flash("El código ha expirado.", "danger")
                return redirect("/forgot")

            # Código válido: marcar como usado dentro del mismo cursor
            cursor.execute("UPDATE recuperacion SET usado=TRUE WHERE id=%s", (resultado["id"],))
            conexion.commit()

        # Cerrar conexión después de usar el cursor
        conexion.close()

        # Mensaje de éxito y redirección
        flash("Código correcto.", "success")
        return redirect("/reset-password")

    # Caso GET: mostrar el formulario
    return render_template("reset_code.html")


#Ruta para cambiar la contraseña
# Ruta para cambiar la contraseña
@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    # Recuperar el correo guardado en sesión
    correo = session.get("correo_recuperar")
    if not correo:
        flash("Primero ingresa tu correo", "warning")
        return redirect("/forgot")

    if request.method == "POST":
        # Obtener las contraseñas del formulario
        new_password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()

        # Validar que no estén vacías
        if not new_password or not confirm:
            flash("Debes ingresar una contraseña.", "warning")
            return redirect("/reset-password")

        # Validar coincidencia
        if new_password != confirm:
            flash("Las contraseñas no coinciden.", "danger")
            return redirect("/reset-password")

        # Generar hash seguro
        password_hash = generate_password_hash(new_password)

        # Conexión a la base de datos
        conexion = get_db_connection()
        if not conexion:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect("/reset-password")

        # Actualizar contraseña en la tabla registro
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE registro SET password=%s WHERE correo=%s",
                (password_hash, correo)
            )
            conexion.commit()

        conexion.close()

        # Limpiar sesión y mostrar mensaje
        session.pop("correo_recuperar", None)
        flash("Contraseña cambiada correctamente ✔", "success")
        return redirect("/login")

    # Caso GET: mostrar formulario
    return render_template("reset_password.html")

# # ------------------------------------
# DETECTAR EL LOGIN
# ------------------------------------
@app.route("/zona_protegida")
def zona_protegida():
    if not session.get("usuario") and not session.get("modal_cerrado"):
        return render_template("zona_protegida.html", mostrar_modal=True)
    return render_template("zona_protegida.html", mostrar_modal=False)


@app.context_processor
def inject_modal_flag():
    mostrar_modal = (
        not session.get("usuario")
        and not session.get("modal_cerrado")
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
    app.run(debug=True)