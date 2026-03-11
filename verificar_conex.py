import psycopg2
DB_CONFIG = {
        'host': "localhost",
        'dbname':"Dessert_Sacre",
        'user':"postgres",
        'password': "123456",
        'port': 5432
    }
try:
    conn = psycopg2.connect(**DB_CONFIG)
    print('Conectado :)')
    conn.close()
except Exception as e:
    print('ERROR:', e)