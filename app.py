from flask import Flask, render_template, request, redirect, url_for, session
import pyodbc
from config import server, database, username, password, driver
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configuración de conexión a la base de datos
connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'

# Definición de las tasas de conversión
conversion_rates = {
    'EUR': {
        'USD': 1.18,
        'PEN': 4.42
    },
    'USD': {
        'EUR': 0.85,
        'PEN': 3.75
    },
    'PEN': {
        'EUR': 0.23,
        'USD': 0.27
    }
}

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    else:
        return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            conn = pyodbc.connect(connection_string)
            cursor = conn.cursor()

            # Consulta para verificar las credenciales del usuario
            cursor.execute("SELECT UserId, Username, PasswordHash FROM Users WHERE Username = ?", username)
            user = cursor.fetchone()

            if user and password == user.PasswordHash:
                session['user_id'] = user.UserId
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error='Credenciales incorrectas. Inténtelo de nuevo.')

        except Exception as e:
            print(e)
            return render_template('login.html', error='Error de conexión. Inténtelo de nuevo más tarde.')

        finally:
            cursor.close()
            conn.close()

@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        user_id = session['user_id']
        try:
            conn = pyodbc.connect(connection_string)
            cursor = conn.cursor()

            # Obtener saldo actual del usuario
            cursor.execute("SELECT BalanceUSD, BalanceEUR, BalancePEN FROM Accounts WHERE UserId = ?", user_id)
            account = cursor.fetchone()
            if account:
                saldo_usd = account.BalanceUSD
                saldo_eur = account.BalanceEUR
                saldo_pen = account.BalancePEN
                return render_template('dashboard.html', saldo_usd=saldo_usd, saldo_eur=saldo_eur, saldo_pen=saldo_pen)
            else:
                return render_template('dashboard.html', error='No se encontró información de cuenta para este usuario.')

        except Exception as e:
            print(e)
            return render_template('dashboard.html', error='Error al recuperar información de la cuenta.')

        finally:
            cursor.close()
            conn.close()
    else:
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/cotizar', methods=['GET', 'POST'])
def cotizar():
    if request.method == 'POST':
        monto = float(request.form['monto'])
        divisa_origen = request.form['divisa_origen']
        divisa_destino = request.form['divisa_destino']

        if divisa_origen in conversion_rates and divisa_destino in conversion_rates[divisa_origen]:
            tasa_conversion = conversion_rates[divisa_origen][divisa_destino]
            monto_convertido = monto * tasa_conversion
            return render_template('cotizar_resultado.html', monto=monto, divisa_origen=divisa_origen, divisa_destino=divisa_destino, monto_convertido=monto_convertido)
        else:
            error = 'Error: Las divisas seleccionadas no tienen una tasa de conversión definida.'
            return render_template('cotizar.html', error=error)

    return render_template('cotizar.html')

@app.route('/conversion', methods=['GET', 'POST'])
def conversion():
    if request.method == 'POST':
        try:
            monto = Decimal(request.form['monto']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)  # Redondear a dos decimales
            divisa_origen = request.form['divisa_origen']
            divisa_destino = request.form['divisa_destino']

            if divisa_origen in conversion_rates and divisa_destino in conversion_rates[divisa_origen]:
                tasa_conversion = Decimal(conversion_rates[divisa_origen][divisa_destino]).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)  # Redondear tasa de conversión
                monto_convertido = (monto * tasa_conversion).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)  # Redondear monto convertido

                # Actualizar saldo del usuario en la base de datos
                conn = pyodbc.connect(connection_string)
                cursor = conn.cursor()

                user_id = session['user_id']
                cursor.execute(f"SELECT Balance{divisa_origen} FROM Accounts WHERE UserId = ?", user_id)
                balance_origen = Decimal(cursor.fetchone()[0])

                if balance_origen >= monto:
                    nuevo_balance_origen = (balance_origen - monto).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    cursor.execute(f"UPDATE Accounts SET Balance{divisa_origen} = ? WHERE UserId = ?", nuevo_balance_origen, user_id)

                    cursor.execute(f"SELECT Balance{divisa_destino} FROM Accounts WHERE UserId = ?", user_id)
                    balance_destino = Decimal(cursor.fetchone()[0])
                    nuevo_balance_destino = (balance_destino + monto_convertido).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    cursor.execute(f"UPDATE Accounts SET Balance{divisa_destino} = ? WHERE UserId = ?", nuevo_balance_destino, user_id)

                    # Registrar la transacción en la tabla Transactions
                    cursor.execute("INSERT INTO Transactions (UserId, FromCurrency, ToCurrency, Amount, Rate, Result, TransactionDate) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                   user_id, divisa_origen, divisa_destino, monto, tasa_conversion, monto_convertido, datetime.now())

                    conn.commit()
                    return render_template('conversion_resultado.html', monto=monto, divisa_origen=divisa_origen, divisa_destino=divisa_destino, monto_convertido=monto_convertido)
                else:
                    error = 'Saldo insuficiente para realizar la conversión.'
                    return render_template('conversion.html', error=error)

            else:
                error = 'Error: Las divisas seleccionadas no tienen una tasa de conversión definida.'
                return render_template('conversion.html', error=error)

        except pyodbc.Error as e:
            print(f"Error de base de datos: {e}")
            return render_template('conversion.html', error='Error al realizar la conversión.')

        except Exception as e:
            print(f"Error inesperado: {e}")
            return render_template('conversion.html', error='Error al realizar la conversión.')

        finally:
            cursor.close()
            conn.close()

    return render_template('conversion.html')

@app.route('/historial')
def historial():
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        user_id = session['user_id']
        cursor.execute("SELECT * FROM Transactions WHERE UserId = ? ORDER BY TransactionDate DESC", user_id)
        transactions = cursor.fetchall()

        return render_template('historial.html', transactions=transactions)

    except pyodbc.Error as e:
        print(f"Error de base de datos: {e}")
        return render_template('historial.html', error='Error al cargar el historial de transacciones.')

    except Exception as e:
        print(f"Error inesperado: {e}")
        return render_template('historial.html', error='Error al cargar el historial de transacciones.')

    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)
