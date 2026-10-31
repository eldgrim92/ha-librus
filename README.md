# Home Assistant — Librus Synergia Integration (`ha-librus`)

Natywna integracja **Home Assistant (`custom_components/librus`)** z dziennikiem elektronicznym **Librus Synergia**, zaprojektowana z myślą o rodzicach i uczniach (z obsługą **jednego lub wielu kont dzieci**).

---

## ✨ Główne funkcje

1. **Obsługa 1 lub więcej dzieci (Multi-Child Support)**:
   - Każde konto dziecka dodawane jest z poziomu interfejsu UI Home Assistant (`Ustawienia -> Urządzenia oraz usługi -> Dodaj integrację -> Librus Synergia`) jako osobny wpis z własnym loginem i hasłem.
   - Każde dziecko tworzy dedykowane **Urządzenie (`Librus - [Imię Dziecka]`)**, grupujące wszystkie jego encje.
2. **Czytelna prezentacja wiadomości (`Message Readability Engine`)**:
   - Wiadomości z modułu *Wiadomości* są automatycznie oczyszczane z błędnego kodu HTML, stylów inline i nadmiarowych spacji, a następnie formatowane do przejrzystego **Markdown** (`body_markdown`) oraz czystego tekstu (`body_text`).
   - Zachowywane są informacje o nadawcy (wraz z rolą, np. `(Wychowawca)`), dacie wysłania, załącznikach, listach wypunktowanych, pogrubieniach oraz klikalnych linkach.
3. **Ostatnie wydarzenia szkolne — Oceny, Uwagi i Szczęśliwy Numerek**:
   - **Oceny (`sensor.librus_<dziecko>_ostatnia_ocena`)**: prezentuje ostatnią ocenę w stanie encji (np. `5 (Matematyka)`) oraz pełną historię ostatnich ocen w atrybutach (przedmiot, waga, kategoria, nauczyciel, data, komentarz).
   - **Uwagi i pochwały (`sensor.librus_<dziecko>_uwagi_i_pochwaly`)**: prezentuje liczbę uwag oraz listę ostatnich uwag pozytywnych i negatywnych wraz z treścią i nauczycielem.
   - **Szczęśliwy numerek (`sensor.librus_<dziecko>_szczesliwy_numerek`)**: codzienny szczęśliwy numerek w szkole.
4. **Powiadomienia Push na telefon przez Home Assistant**:
   - Integracja śledzi identyfikatory pobranych wiadomości, ocen i uwag w trwałej pamięci Home Assistant (`Store`), dzięki czemu restart HA nie powoduje ponownego wysyłania starych powiadomień.
   - Gdy pojawi się nowe zdarzenie, integracja emituje dedykowane zdarzenie na szynie **Home Assistant Event Bus**:
     - `librus_new_message`
     - `librus_new_grade`
     - `librus_new_note`
   - W repozytorium znajduje się gotowy **Blueprint automatyzacji** ([`librus_push_notifications.yaml`](blueprints/automation/librus/librus_push_notifications.yaml)) do wysyłania natychmiastowych powiadomień push na aplikację **Home Assistant Companion**.
5. **Konfigurowalny okres synchronizacji**:
   - Częstotliwość odpytywania serwerów Librus można ustawić podczas dodawania konta oraz zmieniać w dowolnym momencie w `Opcjach integracji` (zakres od `5` do `360` minut, domyślnie `30` minut).
   - Dostępny jest również przycisk `button.librus_<dziecko>_synchronizuj_teraz` oraz usługa `librus.refresh` do wymuszenia synchronizacji na żądanie.

---

## 📦 Instalacja

### Opcja A: HACS (Zalecana)
1. Otwórz **HACS** w swoim Home Assistant.
2. Kliknij menu w prawym górnym rogu (`⋮`) -> **Niestandardowe repozytoria (Custom repositories)**.
3. Wklej adres URL tego repozytorium i wybierz kategorię **Integracja (Integration)**.
4. Pobierz **Librus Synergia** i uruchom ponownie Home Assistant.

### Opcja B: Instalacja ręczna
1. Skopiuj katalog `custom_components/librus` do katalogu `<config>/custom_components/librus` w swojej instalacji Home Assistant.
2. (Opcjonalnie) Skopiuj plik `blueprints/automation/librus/librus_push_notifications.yaml` do `<config>/blueprints/automation/librus/`.
3. Uruchom ponownie Home Assistant.

---

## ⚙️ Konfiguracja (1 lub więcej dzieci)

1. Przejdź do **Ustawienia -> Urządzenia oraz usługi -> Dodaj integrację**.
2. Wyszukaj **Librus Synergia**.
3. Podaj:
   - **Login Librus** (np. `1234567u`) oraz **Hasło**,
   - **Imię dziecka / Nazwę wyświetlaną** (opcjonalnie — jeśli puste, zostanie pobrana automatycznie z profilu ucznia),
   - **Okres synchronizacji w minutach** (domyślnie `30` minut),
   - **Liczbę pamiętanych wiadomości/ocen/uwag** (domyślnie `10`).
4. Aby dodać kolejne dziecko, ponownie kliknij **Dodaj integrację -> Librus Synergia** i wprowadź dane drugiego konta.

---

## 🔔 Konfiguracja powiadomień Push

1. Zaimportuj lub skopiuj blueprint [`blueprints/automation/librus/librus_push_notifications.yaml`](blueprints/automation/librus/librus_push_notifications.yaml) do swojego Home Assistant.
2. Utwórz nową automatyzację na podstawie blueprintu **Librus Synergia — Powiadomienia Push (Wiadomości, Oceny, Uwagi)**.
3. Wybierz swój telefon z aplikacją Home Assistant Companion i zapisz automatyzację.

---

## 📊 Przykłady kart na Dashboard (Lovelace)

Gotowe szablony kart Markdown dla czytelnej skrzynki odbiorczej, tabeli ocen oraz listy uwag znajdziesz w pliku:
👉 [**`docs/lovelace_examples.md`**](docs/lovelace_examples.md)

---

## 🧪 Testy jednostkowe

Aby uruchomić testy jednostkowe lokalnie:

```bash
python3 -m unittest discover -s tests -v
```
