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
        srednica_kabla = wybrany_kabel['średnica zewnętrzna kabla'].values[0] / 10  # Przeliczamy z mm na cm
        promień_gięcia = wybrany_kabel['promień gięcia'].values[0] / 10  # Przeliczamy z mm na cm

        # Zmniejszenie promienia gięcia o 5 cm, jeśli długość kabla < 400 metrów
        if dlugosc_kabla < 400:
            promień_gięcia -= 5

        masa_kabla_na_km = wybrany_kabel['Masa kg/km'].values[0]  # Masa kabla na km

        def minimalna_średnica_wewnętrzna(promień_gięcia):
            return promień_gięcia * 2

        # Funkcja obliczająca długość kabla, jaka zmieści się na bębnie
        def oblicz_dlugosc_na_bebnie(beben, srednica_kabla, dlugosc_kabla):
            warstwa = 0
            calkowita_dlugosc = 0
            bęben_szerokosc = beben['szerokość']  # Prawidłowe przypisanie szerokości bębna

            # Obliczamy długość kabla na każdej warstwie, sprawdzając, czy mamy wystarczająco dużo miejsca
            while calkowita_dlugosc < dlugosc_kabla:
                aktualna_średnica_warstwy = beben['średnica wewnętrzna'] + warstwa * srednica_kabla * 2
                
                # Sprawdź, czy możemy zmieścić kolejną warstwę
                if aktualna_średnica_warstwy > beben['Średnica']:
                    break
                
                # Oblicz obwód warstwy i liczbę zwojów na warstwie
                obwod_warstwy = math.pi * aktualna_średnica_warstwy
                liczba_zwojów_na_warstwie = math.floor(bęben_szerokosc / srednica_kabla)

                # Obliczamy długość kabla, który zmieści się na tej warstwie
                długość_na_warstwie = liczba_zwojów_na_warstwie * obwod_warstwy / 100  # Przeliczenie na metry
                calkowita_dlugosc += długość_na_warstwie

                # Przejdź do kolejnej warstwy
                warstwa += 1
            
            return calkowita_dlugosc

        # Sprawdzamy od najmniejszego bębna
        def wybierz_beben(srednica_kabla, promien_giecia, dlugosc_kabla, bebny_df):
            minimalna_wewnetrzna = minimalna_średnica_wewnętrzna(promien_giecia)
            for index, beben in bebny_df.iterrows():
                if beben['średnica wewnętrzna'] >= minimalna_wewnetrzna:
                    calkowita_dlugosc = oblicz_dlugosc_na_bebnie(beben, srednica_kabla, dlugosc_kabla)
                    if calkowita_dlugosc >= dlugosc_kabla:
                        masa_kabla = (dlugosc_kabla / 1000) * masa_kabla_na_km
                        masa_bębna = beben['Waga']
                        suma_wag = masa_kabla + masa_bębna
                        return beben, masa_kabla, masa_bębna, suma_wag
            return None, None, None, None

        # Zaczynamy od mniejszego bębna i sprawdzamy
        możliwe_bębny = bębny_df.sort_values(by='Średnica')  # Sortujemy od najmniejszego
        odpowiedni_bęben, masa_kabla, masa_bębna, suma_wag = wybierz_beben(srednica_kabla, promień_gięcia, dlugosc_kabla, możliwe_bębny)

        if odpowiedni_bęben is not None:
            wynik = (f"Najlepszy bęben: {odpowiedni_bęben['Średnica']} cm, szerokość {odpowiedni_bęben['szerokość']} cm, "
                     f"średnica wewnętrzna {odpowiedni_bęben['średnica wewnętrzna']} cm.<br>"
                     f"Masa kabla: {masa_kabla:.2f} kg, Masa bębna: {masa_bębna} kg, Łączna masa: {suma_wag:.2f} kg.")
            return render_template('index.html', wynik=wynik, opcje_kabli=get_kable_options())
        else:
            return render_template('index.html', wynik="Nie znaleziono odpowiedniego bębna.", opcje_kabli=get_kable_options())

if __name__ == '__main__':
    app.run(debug=True)
