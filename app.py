from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import math
import os
import json
import logging
from datetime import datetime
from io import BytesIO
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

app = Flask(__name__)

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('kalkulator.log'),
        logging.StreamHandler()
    ]
)

# Cache dla danych Excel
excel_data_cache = {}

# Pobierz ścieżkę do katalogu, w którym znajduje się plik app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, 'wszystkiekable.xlsx')

def load_excel_data():
    """Ładuje dane z pliku Excel z cache'owaniem"""
    global excel_data_cache
    
    if not excel_data_cache:
        try:
            excel_data_cache['kable_df'] = pd.read_excel(file_path, sheet_name='Kable')
            excel_data_cache['bębny_df'] = pd.read_excel(file_path, sheet_name='Wymiary')
            logging.info("Dane Excel załadowane pomyślnie")
        except Exception as e:
            logging.error(f"Błąd ładowania danych Excel: {e}")
            raise
    
    return excel_data_cache['kable_df'], excel_data_cache['bębny_df']

def get_kable_options():
    """Pobiera opcje kabli i przekrojów żył"""
    kable_df, _ = load_excel_data()
    typy_kabli = kable_df['Nazwa'].unique().tolist()
    opcje_kabli = {}
    for kabel in typy_kabli:
        przekroje = kable_df[kable_df['Nazwa'] == kabel]['Liczba i przekrój żył'].unique().tolist()
        opcje_kabli[kabel] = przekroje
    return opcje_kabli

def validate_input_data(nazwa_kabla, liczba_przekroj, dlugosc_kabla):
    """Waliduje dane wejściowe"""
    errors = []
    
    if not nazwa_kabla:
        errors.append("Nie wybrano typu kabla")
    
    if not liczba_przekroj:
        errors.append("Nie wybrano przekroju żył")
    
    try:
        dlugosc = float(dlugosc_kabla)
        if dlugosc <= 0:
            errors.append("Długość kabla musi być większa od 0")
        if dlugosc > 10000:
            errors.append("Długość kabla wydaje się zbyt duża (max 10000m)")
    except (ValueError, TypeError):
        errors.append("Długość kabla musi być liczbą")
    
    return errors

def calculate_cable_on_drum(beben, srednica_kabla, dlugosc_kabla):
    """Oblicza długość kabla na bębnie z lepszą precyzją"""
    warstwa = 0
    calkowita_dlugosc = 0
    bęben_szerokosc = beben['szerokość']
    max_warstwy = 50  # Zabezpieczenie przed nieskończoną pętlą
    
    while calkowita_dlugosc < dlugosc_kabla and warstwa < max_warstwy:
        aktualna_średnica_warstwy = beben['średnica wewnętrzna'] + warstwa * srednica_kabla * 2
        
        if aktualna_średnica_warstwy > beben['Średnica'] - 5:  # Zmniejszony margines
            break
        
        obwod_warstwy = math.pi * aktualna_średnica_warstwy
        liczba_zwojów_na_warstwie = math.floor(bęben_szerokosc / srednica_kabla)
        
        długość_na_warstwie = liczba_zwojów_na_warstwie * obwod_warstwy / 100
        calkowita_dlugosc += długość_na_warstwie
        warstwa += 1
    
    return calkowita_dlugosc, warstwa

def find_suitable_drums(srednica_kabla, promien_giecia, dlugosc_kabla, bebny_df):
    """Znajduje wszystkie odpowiednie bębny z dodatkowymi informacjami"""
    minimalna_wewnetrzna = promien_giecia * 2
    odpowiednie_bebny = []
    
    for index, beben in bebny_df.iterrows():
        if beben['średnica wewnętrzna'] >= minimalna_wewnetrzna:
            calkowita_dlugosc, liczba_warstw = calculate_cable_on_drum(beben, srednica_kabla, dlugosc_kabla)
            
            if calkowita_dlugosc >= dlugosc_kabla:
                masa_kabla = (dlugosc_kabla / 1000) * kable_df[(kable_df['Nazwa'] == nazwa_kabla) & 
                                                               (kable_df['Liczba i przekrój żył'] == liczba_przekroj)]['Masa kg/km'].values[0]
                masa_bębna = beben['Waga']
                suma_wag = masa_kabla + masa_bębna
                
                wykorzystanie_procent = (dlugosc_kabla / calkowita_dlugosc) * 100
                
                odpowiednie_bebny.append({
                    'beben': beben,
                    'masa_kabla': masa_kabla,
                    'masa_bębna': masa_bębna,
                    'suma_wag': suma_wag,
                    'wykorzystanie_procent': wykorzystanie_procent,
                    'liczba_warstw': liczba_warstw,
                    'max_dlugosc': calkowita_dlugosc
                })
    
    return sorted(odpowiednie_bebny, key=lambda x: x['suma_wag'])

def create_drum_visualization(drum_data, cable_length):
    """Tworzy wizualizację bębna z kablem"""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Parametry bębna
    drum_diameter = drum_data['beben']['Średnica']
    inner_diameter = drum_data['beben']['średnica wewnętrzna']
    width = drum_data['beben']['szerokość']
    
    # Rysowanie bębna
    drum_circle = plt.Circle((0, 0), drum_diameter/2, fill=False, color='black', linewidth=3)
    inner_circle = plt.Circle((0, 0), inner_diameter/2, fill=False, color='gray', linewidth=2)
    
    ax.add_patch(drum_circle)
    ax.add_patch(inner_circle)
    
    # Rysowanie kabla (spirala)
    layers = drum_data['liczba_warstw']
    for layer in range(min(layers, 10)):  # Maksymalnie 10 warstw dla wizualizacji
        radius = inner_diameter/2 + layer * 0.5
        if radius < drum_diameter/2:
            cable_circle = plt.Circle((0, 0), radius, fill=False, color='red', linewidth=1, alpha=0.7)
            ax.add_patch(cable_circle)
    
    # Ustawienia wykresu
    ax.set_xlim(-drum_diameter/2 - 10, drum_diameter/2 + 10)
    ax.set_ylim(-drum_diameter/2 - 10, drum_diameter/2 + 10)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_title(f'Bęben {drum_diameter}cm - {cable_length}m kabla\n'
                f'{layers} warstw, wykorzystanie: {drum_data["wykorzystanie_procent"]:.1f}%')
    
    # Zapisz do base64
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    
    return image_base64

def save_calculation_history(calculation_data):
    """Zapisuje historię obliczeń do pliku JSON"""
    history_file = os.path.join(BASE_DIR, 'calculation_history.json')
    
    try:
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []
        
        calculation_data['timestamp'] = datetime.now().isoformat()
        history.append(calculation_data)
        
        # Zachowaj tylko ostatnie 100 obliczeń
        history = history[-100:]
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logging.error(f"Błąd zapisywania historii: {e}")

def generate_pdf_report(drum_data, cable_info, output_path):
    """Generuje raport PDF z wynikami"""
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    # Nagłówek
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Raport Kalkulacji Bębna Kablowego")
    
    # Data
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 80, f"Data: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    # Dane kabla
    y_pos = height - 120
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, "Dane kabla:")
    
    y_pos -= 25
    c.setFont("Helvetica", 10)
    c.drawString(70, y_pos, f"Typ: {cable_info['nazwa']}")
    y_pos -= 20
    c.drawString(70, y_pos, f"Przekrój: {cable_info['przekroj']}")
    y_pos -= 20
    c.drawString(70, y_pos, f"Długość: {cable_info['dlugosc']} m")
    
    # Wyniki
    y_pos -= 40
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, "Zalecany bęben:")
    
    y_pos -= 25
    c.setFont("Helvetica", 10)
    beben = drum_data['beben']
    c.drawString(70, y_pos, f"Średnica: {beben['Średnica']} cm")
    y_pos -= 20
    c.drawString(70, y_pos, f"Szerokość: {beben['szerokość']} cm")
    y_pos -= 20
    c.drawString(70, y_pos, f"Średnica wewnętrzna: {beben['średnica wewnętrzna']} cm")
    y_pos -= 20
    c.drawString(70, y_pos, f"Masa bębna: {drum_data['masa_bębna']} kg")
    y_pos -= 20
    c.drawString(70, y_pos, f"Masa kabla: {drum_data['masa_kabla']:.2f} kg")
    y_pos -= 20
    c.drawString(70, y_pos, f"Łączna masa: {drum_data['suma_wag']:.2f} kg")
    y_pos -= 20
    c.drawString(70, y_pos, f"Liczba warstw: {drum_data['liczba_warstw']}")
    y_pos -= 20
    c.drawString(70, y_pos, f"Wykorzystanie bębna: {drum_data['wykorzystanie_procent']:.1f}%")
    
    c.save()

@app.route('/')
def index():
    try:
        opcje_kabli = get_kable_options()
        return render_template('index.html', opcje_kabli=opcje_kabli)
    except Exception as e:
        logging.error(f"Błąd na stronie głównej: {e}")
        return render_template('error.html', error="Błąd ładowania danych")

@app.route('/api/cable-options')
def api_cable_options():
    """API endpoint dla opcji kabli"""
    try:
        return jsonify(get_kable_options())
    except Exception as e:
        logging.error(f"Błąd API cable-options: {e}")
        return jsonify({"error": "Błąd serwera"}), 500

@app.route('/oblicz', methods=['POST'])
def oblicz_beben():
    global kable_df
    
    try:
        # Pobranie danych z formularza
        nazwa_kabla = request.form.get('nazwa_kabla', '').strip()
        liczba_przekroj = request.form.get('liczba_przekroj', '').strip()
        dlugosc_kabla = request.form.get('dlugosc_kabla', '')
        
        # Walidacja danych
        errors = validate_input_data(nazwa_kabla, liczba_przekroj, dlugosc_kabla)
        if errors:
            return render_template('index.html', 
                                 wynik=f"Błędy walidacji: {'; '.join(errors)}", 
                                 opcje_kabli=get_kable_options())
        
        dlugosc_kabla = float(dlugosc_kabla)
        kable_df, bębny_df = load_excel_data()
        
        # Filtrowanie kabla
        wybrany_kabel = kable_df[(kable_df['Nazwa'] == nazwa_kabla) & 
                                 (kable_df['Liczba i przekrój żył'] == liczba_przekroj)]
        
        if wybrany_kabel.empty:
            return render_template('index.html', 
                                 wynik="Nie znaleziono kabla o podanych parametrach.", 
                                 opcje_kabli=get_kable_options())
        
        # Parametry kabla
        srednica_kabla = wybrany_kabel['średnica zewnętrzna kabla'].values[0] / 10
        promień_gięcia = wybrany_kabel['promień gięcia'].values[0] / 10
        
        if dlugosc_kabla < 400:
            promień_gięcia -= 5
        
        # Znajdź wszystkie odpowiednie bębny
        odpowiednie_bebny = find_suitable_drums(srednica_kabla, promień_gięcia, dlugosc_kabla, bębny_df)
        
        if not odpowiednie_bebny:
            return render_template('index.html', 
                                 wynik="Nie znaleziono odpowiedniego bębna.", 
                                 opcje_kabli=get_kable_options())
        
        # Najlepszy bęben (pierwszy z posortowanej listy)
        najlepszy_beben = odpowiednie_bebny[0]
        
        # Generuj wizualizację
        visualization = create_drum_visualization(najlepszy_beben, dlugosc_kabla)
        
        # Zapisz historię
        calculation_data = {
            'nazwa_kabla': nazwa_kabla,
            'przekroj': liczba_przekroj,
            'dlugosc': dlugosc_kabla,
            'wynik': najlepszy_beben
        }
        save_calculation_history(calculation_data)
        
        return render_template('results.html',
                             najlepszy_beben=najlepszy_beben,
                             wszystkie_bebny=odpowiednie_bebny[:5],  # Pokaż top 5
                             cable_info={
                                 'nazwa': nazwa_kabla,
                                 'przekroj': liczba_przekroj,
                                 'dlugosc': dlugosc_kabla
                             },
                             visualization=visualization,
                             opcje_kabli=get_kable_options())
                             
    except Exception as e:
        logging.error(f"Błąd podczas obliczeń: {e}")
        return render_template('index.html', 
                             wynik=f"Wystąpił błąd podczas obliczeń: {str(e)}", 
                             opcje_kabli=get_kable_options())

@app.route('/history')
def history():
    """Wyświetla historię obliczeń"""
    try:
        history_file = os.path.join(BASE_DIR, 'calculation_history.json')
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
        else:
            history_data = []
        
        return render_template('history.html', history=history_data[-20:])  # Ostatnie 20
    except Exception as e:
        logging.error(f"Błąd ładowania historii: {e}")
        return render_template('error.html', error="Błąd ładowania historii")

@app.route('/download-pdf')
def download_pdf():
    """Generuje i pobiera raport PDF"""
    try:
        # Tu powinieneś przekazać dane z ostatniego obliczenia
        # Dla uproszczenia, zwróć informację o braku danych
        return jsonify({"error": "Funkcja w przygotowaniu"}), 501
    except Exception as e:
        logging.error(f"Błąd generowania PDF: {e}")
        return jsonify({"error": "Błąd serwera"}), 500

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Strona nie została znaleziona"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Wewnętrzny błąd serwera"), 500

if __name__ == '__main__':
    app.run(debug=True)
