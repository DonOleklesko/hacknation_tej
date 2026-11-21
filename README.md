# Odwołania2json

Narzędzie, które czyta dokumenty ze spraw odwoławczych do **Krajowej Izby Odwoławczej (KIO)** w formacie PDF i zamienia je na uporządkowany **JSON**. Potem sprawdza, czy dokumenty jednej sprawy są ze sobą zgodne i czy spełniają podstawowe wymogi Prawa zamówień publicznych.

Gdy wykonawca przegra przetarg i chce się odwołać, składa zwykle trzy dokumenty:

| Dokument | Co z niego wyciągamy |
|---|---|
| **Odwołanie do KIO** | data i miejscowość, odwołujący (nazwa, KRS, NIP, REGON), pełnomocnik (imię i nazwisko, kancelaria, e-mail), zamawiający, zaskarżona czynność i jej data, numer postępowania, numer BZP / TED, tytuł zamówienia |
| **Pełnomocnictwo** | mocodawca (nazwa, KRS, NIP, typ), osoby podpisujące, pełnomocnicy i PESEL |
| **Potwierdzenie przelewu** | data operacji, kwota, rachunek nadawcy i odbiorcy, numer transakcji, tytuł przelewu |

Dokument, który nie pasuje do żadnego typu, daje pusty wynik `{}`.

---

## Szybki start (Windows)

### 1. Wymagania
- **Python 3.11+**
- *(opcjonalnie)* **Tesseract OCR**: potrzebny tylko do zeskanowanych PDF-ów bez warstwy tekstowej. Polski model językowy jest już w folderze `tessdata/`.
- *(opcjonalnie)* **Ollama** z modelem `qwen2.5:7b`: lokalny model AI, który uzupełnia pola nieznalezione przez reguły.

### 2. Instalacja

```bash
py -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Uruchomienie

Kliknij dwukrotnie **`uruchom.bat`**. Otworzy się przeglądarka z adresem **http://localhost:8000**.

Możesz też uruchomić serwer ręcznie:

```bash
.venv\Scripts\python.exe -m uvicorn odw.api:app --port 8000
```

Okno z serwerem musi zostać otwarte, dopóki używasz strony (`Ctrl+C` je wyłącza).

### 4. Pierwsza próba
W repozytorium jest **`przyklad_odwolanie.pdf`**: fikcyjne odwołanie, na którym rozpoznają się wszystkie główne pola. Przeciągnij go na stronę albo użyj przycisku **Wgraj PDF**.

> Przy samym odwołaniu walidacja pokaże dwa błędy: brak pełnomocnictwa i brak potwierdzenia przelewu. Tak ma być, bo sprawa jest niekompletna.

---

## Jak korzystać ze strony

- **Dokumenty sprawy**: lista wgranych PDF-ów z rozpoznanym typem i pewnością.
- **Podgląd PDF**: kliknięcie pola z prawej podświetla miejsce w dokumencie, z którego pochodzi wartość.
- **Rozpoznanie i pola**: wszystkie wyciągnięte pola z pewnością. Pola z pewnością poniżej 75% są oznaczone jako *do sprawdzenia*. Filtry: wszystkie / do sprawdzenia / znalezione / brak.
- **Wynikowy JSON**: można go skopiować albo pobrać.
- **Dlaczego taki typ?**: punkty każdej klasy, próg i lista słów kluczowych, które zadziałały, razem z cytatem z dokumentu.
- **Walidacja między dokumentami**: wyniki reguł sprawy, najpierw błędy, potem ostrzeżenia.
- **Pobierz JSON-y (ZIP)**: wszystkie wyniki sprawy w jednym archiwum (`output/sprawa/<plik>.json`).
- **Przełącznik LLM**: włącza uzupełnianie brakujących pól przez model AI. Jest aktywny tylko wtedy, gdy serwer LLM odpowiada.
- **Klasy dokumentów**: podgląd konfiguracji wszystkich typów (pola, metody, opisy).

Strona ma tryb jasny i ciemny, który przełącza się automatycznie według ustawień systemu.

---

## Jak to działa

```
PDF ─► tekst + pozycje słów ─► rozpoznanie typu ─► pola (reguły) ─► [LLM uzupełnia luki] ─► JSON
                                                                                         │
                                         dokumenty całej sprawy ─► walidacja krzyżowa ◄──┘
```

1. **Tekst** (`odw/extract.py`): `pdfplumber` czyta tekst razem ze współrzędnymi słów. Strona z mniej niż 30 znakami jest traktowana jako skan i trafia do OCR (Tesseract, język polski).
2. **Rozpoznanie typu** (`odw/classify.py`): każda klasa ma słowa kluczowe z wagami. Wagi mogą być ujemne, np. „sygn. akt” wskazuje na wyrok, a nie na odwołanie. Wygrywa klasa z największą liczbą punktów, o ile przekroczy swój próg. Pewność to `punkty zwycięzcy / (zwycięzca + drugi)`. Poniżej 70% wynik jest *niepewny* i przy włączonym LLM to model podejmuje decyzję.
3. **Pola** (`odw/engine.py`): każde pole ma jedną z metod:
   - `regex`: wzorce próbowane po kolei; pierwsze trafienie wygrywa. Pewność wynosi 95%, 88% lub 80% zależnie od numeru wzorca.
   - `rules`: uporządkowane reguły słów kluczowych dające wartość, np. powód odwołania 1–12.
   - `lookup`: wartość ze słownika na podstawie innego pola, np. opis czynności.
   - `llm`: pole zostawione dla modelu AI.

   Wzorce można zawęzić do **sekcji** dokumentu, np. tylko blok „Odwołujący”, żeby NIP zamawiającego nie pomylił się z NIP-em odwołującego. Wartości przechodzą przez **normalizatory** (`odw/normalize.py`: daty, kwoty, rachunki, BZP, TED) i **walidatory** (`odw/validators.py`: sumy kontrolne NIP, REGON, PESEL, IBAN). Walidator nigdy nie odrzuca wartości, tylko obniża pewność i dodaje ostrzeżenie.
4. **LLM** (`odw/llm.py`, opcjonalnie): dostaje *tylko* pola, których reguły nie znalazły. Wszystkie pola idą w jednym zapytaniu na dokument. Odpowiedź jest walidowana schematem Pydantic. Wartość, której nie ma w tekście dokumentu, dostaje niską pewność, co chroni przed halucynacjami. Błąd LLM nie psuje wyniku z reguł.
5. **Walidacja sprawy** (`odw/crosscheck.py`): reguły z `config/case_checks.yaml` porównują dokumenty między sobą.

---

## Walidacja sprawy

Reguły są w pliku `config/case_checks.yaml`, więc nowa reguła to nowy wpis w YAML-u, bez zmian w kodzie.

**Zgodność danych między dokumentami:**
- pełnomocnik z odwołania występuje w pełnomocnictwie,
- KRS, NIP i nazwa odwołującego zgadzają się z mocodawcą,
- numer postępowania i nazwisko pełnomocnika są w tytule przelewu.

**Reguły merytoryczne (Prawo zamówień publicznych):**

| Reguła | Gdy się nie zgadza |
|---|---|
| Termin wniesienia odwołania (art. 515 Pzp, domyślnie 10 dni). Gdy koniec terminu wypada w sobotę, niedzielę albo święto, przesuwa się na najbliższy dzień roboczy (art. 509 ust. 2). | błąd |
| Kwota wpisu: 7 500 / 10 000 / 15 000 / 20 000 zł | ostrzeżenie |
| Opłata skarbowa od pełnomocnictwa: 17 zł | ostrzeżenie |
| Wpis wpłacony na rachunek UZP | pominięta, dopóki nie uzupełnisz numeru rachunku |
| Jest pełnomocnictwo, gdy odwołanie wnosi pełnomocnik | błąd |
| Jest potwierdzenie przelewu wpisu | błąd |

**Operatory reguł:**

| Operator | Działanie |
|---|---|
| `equals` | wartości identyczne (bez różnicy wielkości liter i spacji) |
| `in` | wartość z lewej jest wśród wartości z prawej |
| `contained_in` | wartość z lewej jest fragmentem wartości z prawej |
| `days_between` | liczba dni między dwiema datami mieści się w terminie `max_days` (z uwzględnieniem świąt) |
| `one_of` | wartość z któregokolwiek dokumentu danego typu jest na liście `values` (`compare: amount \| account \| text`) |
| `exists` | w sprawie jest wymagany dokument |

**Klucze wspólne:**
- `when`: reguła uruchamia się tylko wtedy, gdy w sprawie jest dany dokument albo pole ma wartość.
- `severity`: `blad` (domyślnie) albo `ostrzezenie`.

Brak dokumentu lub danych zawsze daje status `pominieto`, nigdy błąd programu.

> ⚖️ **Do weryfikacji:** liczby w regułach (terminy, kwoty wpisu) zostały wpisane według stanu przepisów i warto je potwierdzić z prawnikiem. Termin zależy od wartości zamówienia i sposobu przekazania informacji, a program przyjmuje wariant 10-dniowy. Numer rachunku UZP trzeba wpisać ręcznie w `values: []` przy regule „Wpis wpłacony na rachunek UZP”.

---

## Dodawanie nowego typu dokumentu

Każdy typ to jeden plik w `config/classes/`, np. `przelew.yaml`:

```yaml
name: przelew
title: Potwierdzenie przelewu
recognition:
  min_score: 5                       # próg punktów
  keywords:
    - {pattern: 'potwierdzenie\s+przelewu', weight: 3}
    - {pattern: 'kwota', weight: 1}
output:                              # szkielet wynikowego JSON-a
  przelew_bankowy: {kwota: null, tytul: null}
fields:
  - name: kwota
    path: przelew_bankowy.kwota
    type: number
    method: regex
    normalize: [amount]
    validators: [amount_positive]
    patterns:
      - 'Kwota[\s.:]*(<<AMOUNT>>)'
```

Wspólne fragmenty wyrażeń regularnych (`<<DATE>>`, `<<AMOUNT>>`, `<<ACCOUNT>>`, `<<PERSON>>`, `<<EMAIL>>`, `<<ROLE>>`) są zdefiniowane w `config/macros.yaml`. Program wczytuje nowy plik automatycznie, bez zmian w kodzie.

---

## Konfiguracja (`.env`)

Skopiuj `.env.example` jako `.env` i zmień potrzebne wartości:

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `LLM_ENABLED` | `0` | `1` = LLM uzupełnia brakujące pola |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | adres API zgodnego z OpenAI (Ollama, vLLM…) |
| `LLM_MODEL` | `qwen2.5:7b` | nazwa modelu |
| `LLM_API_KEY` | `ollama` | klucz API |
| `LLM_TIMEOUT` | `60` | limit czasu zapytania (s) |
| `TESSERACT_CMD` | wykrywany | ścieżka do `tesseract.exe`, jeśli nie ma go w PATH |
| `TESSDATA_PREFIX` | `tessdata/` | folder z modelami językowymi OCR |
| `OCR_LANG` | `pol` | język OCR |

---

## Testy i ocena jakości

**Testy jednostkowe** (normalizatory, walidatory, pola, LLM, walidacja sprawy):

```bash
.venv\Scripts\python.exe -m pytest -q
```

**Ocena na danych UZP** wymaga folderu `dane-uzp/dane/` położonego **obok** folderu projektu. W środku są foldery `przyklad_*/` z trzema PDF-ami i oczekiwanymi JSON-ami oraz folder `negatywne/`.

```bash
.venv\Scripts\python.exe -m odw.evaluate --errors 2
```

```bash
.venv\Scripts\python.exe -m odw.eval_classify
```

- `odw.evaluate` liczy precyzję, czułość i F1 ogólnie, dla każdego typu i dla każdego pola. Wynik zapisuje do `reports/ostatni_eval.json`. Opcje: `--only <typ>`, `--errors N`, `--llm`.
- `odw.eval_classify` sprawdza samo rozpoznawanie typów.

Skróty do obu poleceń to `test_f1.bat` i `test_klasyfikacji.bat`.

Ostatni wynik na danych treningowych: **196/196** dokumentów rozpoznanych poprawnie, **F1 = 1.0**. Wzorce były pisane na tych samych danych, więc to górna granica. Prawdziwą jakość pokaże dopiero osobny zbiór testowy.

Gdy folder `dane-uzp` istnieje, lista **Wczytaj przykład z danych UZP** na stronie pokazuje gotowe komplety i dokumenty negatywne.

---

## API

| Metoda | Adres | Opis |
|---|---|---|
| `GET` | `/api/status` | stan LLM (włączony, osiągalny, model) |
| `GET` | `/api/classes` | lista typów dokumentów z polami |
| `POST` | `/api/process?llm=false` | przetwarza wgrany PDF (`multipart/form-data`, pole `file`) |
| `POST` | `/api/crosscheck` | walidacja sprawy; body: `[{name, class_name, json}]` |
| `GET` | `/api/samples` | lista przykładów z `dane-uzp` |
| `GET` | `/api/process-sample?id=…` | przetwarza przykład z `dane-uzp` |
| `GET` | `/api/sample-pdf?id=…` | zwraca PDF przykładu |

Interaktywna dokumentacja API: **http://localhost:8000/docs**.

---

## Struktura projektu

```
odwolania2json/
├── odw/                     kod
│   ├── api.py               serwer FastAPI (strona + API)
│   ├── pipeline.py          cały proces dla jednego PDF
│   ├── extract.py           tekst z PDF + OCR
│   ├── classify.py          rozpoznanie typu dokumentu
│   ├── engine.py            wyciąganie pól według YAML
│   ├── normalize.py         normalizatory wartości
│   ├── validators.py        sumy kontrolne
│   ├── locate.py            pozycja wartości w PDF (podświetlanie)
│   ├── llm.py               uzupełnianie pól przez LLM
│   ├── crosscheck.py        walidacja sprawy + kalendarz świąt
│   ├── classes.py           wczytywanie klas z YAML
│   ├── settings.py          ustawienia z .env
│   ├── evaluate.py          ocena F1
│   └── eval_classify.py     ocena klasyfikacji
├── config/
│   ├── classes/             typy dokumentów (odwolanie, pelnomocnictwo, przelew)
│   ├── case_checks.yaml     reguły walidacji sprawy
│   └── macros.yaml          wspólne fragmenty regexów
├── web/                     strona (HTML + pdf.js)
├── tests/                   testy jednostkowe
├── tessdata/                polski model OCR
├── reports/                 wyniki ocen
├── przyklad_odwolanie.pdf   przykładowy dokument do testów
├── uruchom.bat              start strony
├── test_f1.bat              ocena F1 + testy
└── test_klasyfikacji.bat    ocena klasyfikacji
```

---

## Plany

- **Kreator nowej klasy**: wgrywasz kilka PDF-ów nowego typu, a LLM proponuje plik YAML do zatwierdzenia.
- **Baza przykładów**: poprawki zapisane przez człowieka, używane jako przykłady dla LLM.
- Ręczna korekta pól na stronie.
- Przetwarzanie całego folderu z linii komend.

---

## Uwagi

- Dane w zbiorze UZP są **syntetyczne**, więc część numerów (NIP, PESEL, rachunki) ma błędne sumy kontrolne. Dlatego walidatory tylko ostrzegają, a nie odrzucają wartości.
- Strona pobiera czcionki i ikony z Google Fonts. Bez internetu działa dalej, tylko z czcionką systemową i bez ikon.
- Wszystkie dane w `przyklad_odwolanie.pdf` są fikcyjne.
