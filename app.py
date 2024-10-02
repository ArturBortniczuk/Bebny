from flask import Flask, render_template, request
import pandas as pd
import math
import os

app = Flask(__name__)

# Pobierz ścieżkę do katalogu, w którym znajduje się plik app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Relatywna ścieżka do pliku Excel
file_path = os.path.join(BASE_DIR, 'wszystkiekable.xlsx')

# Załaduj dane z pliku Excel
kable_df = pd.read_excel(file_path, sheet_name='Kable')
bębny_df = pd.read_excel(file_path, sheet_name='Wymiary')

# Utwórz listę unikalnych typów kabli i przekrojów żył
def get_kable_options():
    typy_kabli = kable_df['Nazwa'].unique().tolist()  # Unikalne typy kabli
    opcje_kabli = {}
    for kabel in typy_kabli:
        przekroje = kable_df[kable_df['Nazwa'] == kabel]['Liczba i przekrój żył'].unique().tolist()
        opcje_kabli[kabel] = przekroje
    return opcje_kabli

@app.route('/')
def index():
    opcje_kabli = get_kable_options()  # Pobierz opcje kabli i przekrojów żył
    return render_template('index.html', opcje_kabli=opcje_kabli)

@app.route('/oblicz', methods=['POST'])
def oblicz_beben():
    # Pobranie danych z formularza
    nazwa_kabla = request.form['nazwa_kabla']
    liczba_przekroj = request.form['liczba_przekroj']
    dlugosc_kabla = float(request.form['dlugosc_kabla'])

    # Filtrujemy kabel na podstawie wprowadzonych danych
    wybrany_kabel = kable_df[(kable_df['Nazwa'] == nazwa_kabla) & 
                             (kable_df['Liczba i przekrój żył'] == liczba_przekroj)]

    if wybrany_kabel.empty:
        return render_template('index.html', wynik="Nie znaleziono kabla o podanych parametrach.", opcje_kabli=get_kable_options())
    else:
        # Pobieranie parametrów dla wybranego kabla
        średnica_kabla = wybrany_kabel['średnica zewnętrzna kabla'].values[0] / 10  # Przeliczamy z mm na cm
        promień_gięcia = wybrany_kabel['promień gięcia'].values[0] / 10  # Przeliczamy z mm na cm

        # Zmniejszenie promienia gięcia o 5 cm, jeśli długość kabla < 400 metrów
        if dlugosc_kabla < 400:
            promień_gięcia -= 5

        masa_kabla_na_km = wybrany_kabel['Masa kg/km'].values[0]  # Masa kabla na km

        def minimalna_średnica_wewnętrzna(promień_gięcia):
            return promień_gięcia * 2

        def oblicz_długość_na_bębnie(bęben, średnica_kabla, długość_kabla):
            warstwa = 0
            całkowita_długość = 0
            bęben_szerokosc = bęben['szerokość']

            while całkowita_długość < długość_kabla and (bęben['średnica wewnętrzna'] + warstwa * średnica_kabla * 2) <= bęben['Średnica']:
                aktualna_średnica_warstwy = bęben['średnica wewnętrzna'] + warstwa * średnica_kabla * 2
                obwód_warstwy = math.pi * aktualna_średnica_warstwy
                liczba_zwojów_na_warstwie = math.floor(bęben_szerokosc / średnica_kabla)
                długość_na_warstwie = liczba_zwojów_na_warstwie * obwód_warstwy / 100  # Przeliczenie na metry
                całkowita_długość += długość_na_warstwie
                warstwa += 1
            return całkowita_długość

        def wybierz_bęben(średnica_kabla, promień_gięcia, długość_kabla, bębny_df):
            minimalna_wewnętrzna = minimalna_średnica_wewnętrzna(promień_gięcia)
            for index, bęben in bębny_df.iterrows():
                if bęben['średnica wewnętrzna'] >= minimalna_wewnętrzna:
                    całkowita_długość = oblicz_długość_na_bębnie(bęben, średnica_kabla, długość_kabla)
                    if całkowita_długość >= dlugosc_kabla:
                        masa_kabla = (dlugosc_kabla / 1000) * masa_kabla_na_km
                        masa_bębna = bęben['Waga']
                        suma_wag = masa_kabla + masa_bębna
                        return bęben, masa_kabla, masa_bębna, suma_wag
            return None, None, None, None

        # Wynik
        odpowiedni_bęben, masa_kabla, masa_bębna, suma_wag = wybierz_bęben(średnica_kabla, promień_gięcia, dlugosc_kabla, bębny_df)

        if odpowiedni_bęben is not None:
            wynik = (f"Najlepszy bęben: {odpowiedni_bęben['Średnica']} cm, szerokość {odpowiedni_bęben['szerokość']} cm, "
                     f"średnica wewnętrzna {odpowiedni_bęben['średnica wewnętrzna']} cm.<br>"
                     f"Masa kabla: {masa_kabla:.2f} kg, Masa bębna: {masa_bębna} kg, Łączna masa: {suma_wag:.2f} kg.")
            return render_template('index.html', wynik=wynik, opcje_kabli=get_kable_options())
        else:
            return render_template('index.html', wynik="Nie znaleziono odpowiedniego bębna.", opcje_kabli=get_kable_options())

if __name__ == '__main__':
    app.run(debug=True)
