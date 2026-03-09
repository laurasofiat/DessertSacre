from flask import Flask, request, render_template, redirect, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import smtplib
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash

# ------------------------------------
# CONFIG GENERAL
# ------------------------------------
app = Flask(__name__)
app.secret_key = "clave_super_secreta"

DB_CONFIG = {
    'host': 'localhost',
    'database': 'mayron_formulario',
    'user': 'postgres',
    'password': '123456',
    'port': 5432
}

def conectar_bd():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print("Error BD:", e)
        return None


# ------------------------------------
# CONFIG SMTP GMAIL
# ------------------------------------
EMAIL_USER = "dessertsacre@gmail.com"
EMAIL_PASS = "utrehsexsumaxznm"   # Contraseña de aplicación Gmail


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
    # Reiniciar sesiones temporales
    session.pop("intentos_reenvio", None)
    session.pop("correo_verificacion", None)

    if request.method == "POST":
        nombre = request.form["nombre"]
        correo = request.form["correo"]
        password = request.form["password"]

        conexion = conectar_bd()
        cursor = conexion.cursor()

        # Validar si el correo ya existe
        cursor.execute("SELECT id FROM usuarios WHERE correo=%s", (correo,))
        if cursor.fetchone():
            flash("El correo ya está registrado. Inicia sesión.", "warning")
            # Guardar correo en sesión para ayudar al usuario en login
            session["correo_login_auto"] = correo
            return redirect("/login")

        # Encriptar contraseña
        password_hash = generate_password_hash(password)

        # Generar código
        codigo = str(random.randint(100000, 999999))

        cursor.execute("""
            INSERT INTO usuarios (nombre, correo, password, codigo_verificacion, verificado)
            VALUES (%s, %s, %s, %s, FALSE)
        """, (nombre, correo, password_hash, codigo))

        conexion.commit()

        # ENVIAR CÓDIGO
        enviar_codigo(correo, codigo)

        # Guardar correo temporal para verify
        session["correo_verificacion"] = correo

        cursor.close()
        conexion.close()

        flash("Registro exitoso. Revisa tu correo para verificar la cuenta", "success")
        return redirect("/verify")

    return render_template("register.html")



# ------------------------------------
# VERIFICACIÓN
# ------------------------------------
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

        conexion = conectar_bd()
        cursor = conexion.cursor()

        cursor.execute("SELECT codigo_verificacion FROM usuarios WHERE correo=%s", (correo,))
        result = cursor.fetchone()

        if not result:
            flash("Error interno.", "danger")
            return render_template("verify.html", redirect_login=False, intentos=intentos)

        codigo_real = result[0]

        if codigo_ingresado == codigo_real:
            cursor.execute("UPDATE usuarios SET verificado=TRUE WHERE correo=%s", (correo,))
            conexion.commit()
            cursor.close()
            conexion.close()

            flash("Correo verificado con éxito", "success")
            session.pop("correo_verificacion", None)
            session.pop("intentos_reenvio", None)

            return redirect("/login")


        
        flash("El código ingresado es incorrecto", "danger")
        return render_template("verify.html", redirect_login=False, intentos=intentos)

    return render_template("verify.html", redirect_login=False, intentos=intentos)


#------------------------------------
# REENVÍO DE CÓDIGO
#------------------------------------
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

    conexion = conectar_bd()
    cursor = conexion.cursor()
    cursor.execute("UPDATE usuarios SET codigo_verificacion=%s WHERE correo=%s",
                   (nuevo_codigo, correo))
    conexion.commit()
    cursor.close()
    conexion.close()

    # Aumentar contador
    session["intentos_reenvio"] = intentos + 1

    # Enviar código
    enviar_codigo(correo, nuevo_codigo)

    flash("Código reenviado. Revisa tu correo.", "success")
    return redirect("/verify")



# ------------------------------------
# LOGIN
# ------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form["correo"]
        password = request.form["password"]

        conexion = conectar_bd()
        cursor = conexion.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT * FROM usuarios WHERE correo=%s", (correo,))
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

        session["usuario"] = usuario["nombre"]
        flash("Inicio de sesión exitoso", "success")
        return render_template("login.html", redirect_dashboard=True)
    
    # Limpia el redirect cuando se carga el login
        
    redir_verificar = session.pop("redir_verificar", None)
    
    correo_auto = session.pop("correo_login_auto", "")

    return render_template("login.html", redir_verificar=redir_verificar, correo_auto=correo_auto)

# ------------------------------------
# DASHBOARD
# ------------------------------------
@app.route("/dashboard")
def dashboard():
    if not session.get("usuario"):
        return redirect("/login")
    return render_template("dashboard.html", usuario=session["usuario"])


# ------------------------------------
# LOGOUT
# ------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ------------------------------------
# NAVBAR
# ------------------------------------

@app.route('/inicio')
def inicio():
    return render_template('inicio.html')

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

@app.route('/cerrar_sesion')
def cerrar_sesion():
    # lógica de logout
    return "Sesión cerrada", 200

# ------------------------------------
# OLVIDO SU CONTRASEÑA?
# ------------------------------------
#Ruta para solicitar la recuperación

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        correo = request.form["correo"]
        
        if not correo:
            flash("Por favor ingresa un correo.", "warning")
            return redirect("/forgot")
        
        conexion = conectar_bd()
        cursor = conexion.cursor()

        cursor.execute("SELECT id FROM usuarios WHERE correo=%s", (correo,))
        usuario = cursor.fetchone()

        if not usuario:
            flash("El correo ingresado no existe ❌", "danger")
            session["redir_register"] = True  
            return redirect("/forgot")

        # Generar código de recuperación
        codigo = str(random.randint(100000, 999999))

        cursor.execute("""
            UPDATE usuarios
            SET codigo_verificacion = %s
            WHERE correo = %s
        """, (codigo, correo))

        conexion.commit()
        conexion.close()

        enviar_codigo(correo, codigo)
        
        flash("Código enviado a tu correo 📩", "success")
        session["correo_recuperar"] = correo

        return redirect("/reset-code")
    
    # Limpia el redirect cuando se carga el forgot
    redir_register = session.pop("redir_register", None)

    return render_template("forgot.html", redir_register=redir_register)

#Crear vista para ingresar el código
@app.route("/reset-code", methods=["GET", "POST"])
def reset_code():
    correo = session.get("correo_recuperar")
    if not correo:
        flash("Primero ingresa tu correo", "warning")
        return redirect("/forgot")

    if request.method == "POST":
        codigo_ingresado = request.form["codigo"]

        conexion = conectar_bd()
        cursor = conexion.cursor()

        cursor.execute("SELECT codigo_verificacion FROM usuarios WHERE correo=%s", (correo,))
        codigo_real = cursor.fetchone()[0]

        if codigo_ingresado == codigo_real:
            flash("Código correcto ✔", "success")
            return redirect("/reset-password")

        flash("Código incorrecto ❌", "danger")
        return redirect("/reset-code")

    return render_template("reset_code.html")

#Ruta para cambiar la contraseña
@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    correo = session.get("correo_recuperar")
    if not correo:
        flash("Primero ingresa tu correo", "warning")
        return redirect("/forgot")

    if request.method == "POST":
        new_password = request.form["password"]
        password_hash = generate_password_hash(new_password)

        conexion = conectar_bd()
        cursor = conexion.cursor()

        cursor.execute("""
            UPDATE usuarios SET password=%s WHERE correo=%s
        """, (password_hash, correo))

        conexion.commit()
        conexion.close()

        session.pop("correo_recuperar", None)

        flash("Contraseña cambiada correctamente ✔", "success")
        return redirect("/login")

    return render_template("reset_password.html")

# ------------------------------------
# DETECTAR EL LOGIN
# ------------------------------------
# @app.route("/zona_protegida")
# def zona_protegida():
#     if not session.get("usuario") and not session.get("modal_cerrado"):
#         return render_template("zona_protegida.html", mostrar_modal=True)
#     return render_template("zona_protegida.html", mostrar_modal=False)


# @app.context_processor
# def inject_modal_flag():
#     mostrar_modal = (
#         not session.get("usuario")
#         and not session.get("modal_cerrado")
#     )
#     return dict(mostrar_modal=mostrar_modal)


# @app.route("/cerrar-modal")
# def cerrar_modal():
#     session["modal_cerrado"] = True
#     return "", 204


# ------------------------------------
# RUN
# ------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True )
