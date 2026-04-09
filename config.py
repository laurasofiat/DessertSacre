import os

class Config:

    # Clave secreta para sesiones y formularios

    SECRET_KEY = os.environ.get("SECRET_KEY") or "clave_super_secreta_local"

    #Configuracion de la base de datos

    DB_CONFIG = {

        'host': os.environ.get("DB_HOST") or "localhost",

        'dbname': os.environ.get("DB_NAME") or "Dessert_Sacre",

        'user': os.environ.get("DB_USER") or "postgres",

        'password': os.environ.get("DB_PASS") or "123456",

        'port': int(os.environ.get("DB_PORT") or 5432)

    }

       # CONFIG SMTP GMAIL

    EMAIL_USER = "dessertsacre@gmail.com"

    EMAIL_PASS = "utrehsexsumaxznm"   # Contraseña de aplicación Gmail