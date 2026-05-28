# psycopg2 es una librería que permite conectarse a bases de datos PostgreSQL desde Python
import psycopg2

# Diccionario que contiene los parámetros necesarios para la conexión
# Cada clave representa un dato requerido por PostgreSQL
DB_CONFIG = {
    'host': "localhost",        # Dirección del servidor (localhost = tu propio equipo)
    'dbname': "Dessert_Sacre",  # Nombre de la base de datos
    'user': "postgres",         # Usuario de PostgreSQL
    'password': "123456",       # Contraseña del usuario
    'port': "5432"              # Puerto por defecto de PostgreSQL
}
try:
    # Se intenta establecer la conexión usando los parámetros definidos
    conn = psycopg2.connect(**DB_CONFIG)
    
    # Si la conexión es exitosa, se muestra este mensaje
    print("Conexión exitosa.")
    
    # Es importante cerrar la conexión para liberar recursos
    conn.close()
except psycopg2.Error as e:
    # Si ocurre un error, se captura y se muestra en consola
    print("Error al conectar:", e)