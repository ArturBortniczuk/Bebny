from flask import Flask, render_template, request, jsonify
import openpyxl
import math
import os
import json
import logging
from datetime import datetime

app = Flask(__name__)

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)

# Cache dla danych Excel
excel_data_cache = {}

# Pobierz ścieżkę do katalogu, w którym znajduje się plik app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, 'wszystkiekable.xlsx')

def load_excel_data():
    """Ładuje dane z pliku Excel z cache'owaniem (bez pandas)"""
    global excel_data_cache
    
    if not excel_data_cache:
        try:
            workbook = openpyxl.load_workbook(file_path)
            
            # Ładowanie arkusza "Kable"
            kable_sheet = workbook['Kable']
            kable_data = []
            headers_kable = [cell.value for cell in kable_sheet[1]]
            
            for row in kable_sheet.iter_rows(min_row=2, values_only=True):
                if row[0]:  # Sprawdź czy pierwsza kolumna nie jest pusta
                    row_dict = {headers_kable[i]: row[i] for i in range(len(headers_kable)) if i < len(row)}
                    kable_data.append(row_dict)
            
            # Ładowanie arkusza "Wymiary"
            bebny_sheet = workbook['Wymiary']
            bebny_data = []
            headers_bebny = [cell.value for cell in bebny_sheet[1]]
            
            for row in bebny_sheet.iter_rows(min_row=2, values_only=True):
                if row[0]:  # Sprawdź czy pierwsza kolumna nie jest pusta
                    row_dict = {headers_bebny[i]: row[i] for i in range(len(headers_bebny)) if i < len(row)}
                    bebny_data.append(row_dict)
            
            excel_data_cache['kable_data'] = kable_data
            excel_data_cache['bebny_data'] = bebny_data
            
            logging.info("Dane Excel załadowane pomyślnie")
        except Exception as e:
            logging.error(f"Błąd ładowania danych Excel: {e}")
            raise
    
    return excel_data_cache['kable_data'], excel_data_cache['bebny_data']

def get_kable_options():
    """Pobiera opcje kabli i przekrojów żył"""
    kable_data, _ = load_excel_data()
    typy_kabli = list(set([kabel['Nazwa'] for kabel in kable_data if kabel.get('Nazwa')]))
    opcje_kabli = {}
    
    for kabel_typ in typy_kabli:
        przekroje = list(set([
            kabel['Liczba i przekrój żył'] 
            for kabel in kable_data 
            if kabel.get('Nazwa') == kabel_typ and kabel.get('Liczba i przekrój żył')
        ]))
        opcje_kabli[kabel_typ] = przekroje
    
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

def find_suitable_drums(srednica_kabla, promien_giecia, dlugosc_kabla, bebny_data, masa_kabla_na_km):
    """Znajduje wszystkie odpowiednie bębny z dodatkowymi informacjami"""
    minimalna_wewnetrzna = promien_giecia * 2
    odpowiednie_bebny = []
    
    for beben in bebny_data:
        if beben.get('średnica wewnętrzna', 0) >= minimalna_wewnetrzna:
            calkowita_dlugosc, liczba_warstw = calculate_cable_on_drum(beben, srednica_kabla, dlugosc_kabla)
            
            if calkowita_dlugosc >= dlugosc_kabla:
                masa_kabla = (dlugosc_kabla / 1000) * masa_kabla_na_km
                masa_bębna = beben.get('Waga', 0)
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

def save_calculation_history(calculation_data):
    """Zapisuje historię obliczeń do pliku JSON"""
    history_file = os.path.join(BASE_DIR, 'calculation_history.json')
    
    try:
        # Dodaj timestamp
        calculation_data['timestamp'] = datetime.now().isoformat()
        
        # Debug log
        logging.info(f"Zapisywanie historii: {calculation_data['nazwa_kabla']} - {calculation_data['dlugosc']}m")
        
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []
            logging.info("Tworzenie nowego pliku historii")
        
        history.append(calculation_data)
        
        # Zachowaj tylko ostatnie 100 obliczeń
        history = history[-100:]
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        
        logging.info(f"Historia zapisana, łącznie {len(history)} obliczeń")
            
    except Exception as e:
        logging.error(f"Błąd zapisywania historii: {e}")
        # W przypadku błędu, spróbuj zapisać bez indentacji
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump([calculation_data], f, ensure_ascii=False)
            logging.info("Historia zapisana w trybie awaryjnym")
        except Exception as e2:
            logging.error(f"Krytyczny błąd zapisywania historii: {e2}")

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
        kable_data, bebny_data = load_excel_data()
        
        # Znajdź wybrany kabel
        wybrany_kabel = None
        for kabel in kable_data:
            if (kabel.get('Nazwa') == nazwa_kabla and 
                kabel.get('Liczba i przekrój żył') == liczba_przekroj):
                wybrany_kabel = kabel
                break
        
        if not wybrany_kabel:
            return render_template('index.html', 
                                 wynik="Nie znaleziono kabla o podanych parametrach.", 
                                 opcje_kabli=get_kable_options())
        
        # Parametry kabla
        srednica_kabla = wybrany_kabel.get('średnica zewnętrzna kabla', 0) / 10
        promień_gięcia = wybrany_kabel.get('promień gięcia', 0) / 10
        masa_kabla_na_km = wybrany_kabel.get('Masa kg/km', 0)
        
        if dlugosc_kabla < 400:
            promień_gięcia -= 5
        
        # Znajdź wszystkie odpowiednie bębny
        odpowiednie_bebny = find_suitable_drums(
            srednica_kabla, promień_gięcia, dlugosc_kabla, bebny_data, masa_kabla_na_km
        )
        
        if not odpowiednie_bebny:
            return render_template('index.html', 
                                 wynik="Nie znaleziono odpowiedniego bębna.", 
                                 opcje_kabli=get_kable_options())
        
        # Najlepszy bęben (pierwszy z posortowanej listy)
        najlepszy_beben = odpowiednie_bebny[0]
        
        # Przekaż dane do template jako strukturę (bez zapisywania historii na serwerze)
        return render_template('index.html',
                             wynik_data={
                                 'nazwa_kabla': nazwa_kabla,
                                 'przekroj': liczba_przekroj,
                                 'dlugosc': dlugosc_kabla,
                                 'srednica_bebna': najlepszy_beben['beben']['Średnica'],
                                 'laczna_masa': najlepszy_beben['suma_wag'],
                                 'szczegoly': najlepszy_beben
                             },
                             save_to_history={
                                 'nazwa_kabla': nazwa_kabla,
                                 'przekroj': liczba_przekroj,
                                 'dlugosc': dlugosc_kabla,
                                 'wynik': {
                                     'beben': {
                                         'Średnica': najlepszy_beben['beben']['Średnica'],
                                         'szerokość': najlepszy_beben['beben']['szerokość'],
                                         'średnica wewnętrzna': najlepszy_beben['beben']['średnica wewnętrzna'],
                                         'Waga': najlepszy_beben['beben'].get('Waga', 0)
                                     },
                                     'masa_kabla': najlepszy_beben['masa_kabla'],
                                     'masa_bębna': najlepszy_beben['masa_bębna'],
                                     'suma_wag': najlepszy_beben['suma_wag'],
                                     'wykorzystanie_procent': najlepszy_beben['wykorzystanie_procent'],
                                     'liczba_warstw': najlepszy_beben['liczba_warstw']
                                 }
                             },
                             opcje_kabli=get_kable_options())
                             
    except Exception as e:
        logging.error(f"Błąd podczas obliczeń: {e}")
        return render_template('index.html', 
                             wynik=f"Wystąpił błąd podczas obliczeń: {str(e)}", 
                             opcje_kabli=get_kable_options())

@app.route('/history')
def history():
    """Wyświetla historię obliczeń z localStorage"""
    # Historia będzie ładowana z localStorage po stronie klienta
    return render_template('history.html')

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Strona nie została znaleziona"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Wewnętrzny błąd serwera"), 500

# Dla Vercel
if __name__ == '__main__':
    app.run(debug=False)
