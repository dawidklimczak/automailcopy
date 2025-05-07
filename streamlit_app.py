import streamlit as st
import json
import re
import os
import pypdf
import base64
from openai import OpenAI
from jsonschema import validate, ValidationError

# Konfiguracja strony
st.set_page_config(
    page_title="Generator treści marketingowych dla e-booków",
    layout="wide"
)

# Definicja schematu JSON
JSON_SCHEMA = {
    "type": "object",
    "required": ["intro", "why_created", "contents", "problems_solved", "target_audience", "example"],
    "properties": {
        "intro": {"type": "string", "description": "Wstęp — kontekst i problem odbiorcy"},
        "why_created": {"type": "string", "description": "Dlaczego powstał ten ebook"},
        "contents": {"type": "string", "description": "Co znajdziesz w środku (spis treści / kluczowe rozdziały)"},
        "problems_solved": {"type": "string", "description": "Jakie problemy rozwiązuje (wartość praktyczna)"},
        "target_audience": {"type": "string", "description": "Dla kogo jest ten ebook (i dla kogo nie)"},
        "example": {"type": "string", "description": "Fragment lub przykład z ebooka"}
    }
}

# Funkcja do odczytywania zawartości pliku PDF
def read_pdf(pdf_file):
    pdf_text = ""
    try:
        # Utwórz czytnik PDF z biblioteki pypdf
        pdf_reader = pypdf.PdfReader(pdf_file)
        
        # Odczytaj tekst ze wszystkich stron
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            pdf_text += page.extract_text()
            
        return pdf_text
    except Exception as e:
        st.error(f"Błąd podczas odczytywania pliku PDF: {e}")
        return None

# Funkcja do obsługi specjalnych przypadków formatu danych
def normalize_json_data(data):
    # Sprawdzenie czy contents jest listą i konwersja na string w formacie HTML
    if "contents" in data and isinstance(data["contents"], list):
        html_content = "<ul>"
        for item in data["contents"]:
            if isinstance(item, dict) and "rozdzial" in item and "opis" in item:
                html_content += f"<li><strong>{item['rozdzial']}</strong> - {item['opis']}</li>"
            elif isinstance(item, str):
                html_content += f"<li>{item}</li>"
        html_content += "</ul>"
        data["contents"] = html_content
    
    # Upewnienie się, że wszystkie pola są stringami
    for key in data:
        if not isinstance(data[key], str):
            # Konwersja innych typów na string
            if isinstance(data[key], list):
                data[key] = ", ".join(str(item) for item in data[key])
            else:
                data[key] = str(data[key])
    
    return data

# Funkcja do wywołania API OpenAI
def analyze_pdf_with_openai(pdf_text, persona, model="o4-mini", tone="profesjonalny", lengths=None):
    try:
        # Sprawdzenie, czy klucz API OpenAI jest ustawiony
        api_key = os.environ.get("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
        if not api_key:
            st.error("Brak klucza API OpenAI. Ustaw zmienną środowiskową OPENAI_API_KEY lub dodaj ją do sekretu Streamlit.")
            return None
        
        # Inicjalizacja klienta OpenAI (nowy sposób w wersji >=1.0.0)
        client = OpenAI(api_key=api_key)
        
        # Dostosowanie tonu komunikacji
        tone_instruction = ""
        if tone == "profesjonalny":
            tone_instruction = "Użyj rzeczowego, uprzejmego języka, bez emocjonalnych wyrażeń. Zachowaj profesjonalny ton."
        elif tone == "przyjazny":
            tone_instruction = "Użyj ciepłego, osobistego i otwartego języka. Bądź przyjazny i bezpośredni."
        elif tone == "zabawny":
            tone_instruction = "Użyj lekkiego, żartobliwego języka z elementami humoru. Nie przesadzaj, ale bądź zabawny."
        elif tone == "motywujący":
            tone_instruction = "Użyj inspirującego, podnoszącego na duchu języka. Zachęcaj i motywuj czytelnika."
        elif tone == "poważny":
            tone_instruction = "Użyj formalnego, zdystansowanego i neutralnego języka. Zachowaj powagę i oficjalny ton."
        elif tone == "empatyczny":
            tone_instruction = "Użyj wspierającego języka, który pokazuje zrozumienie dla emocji i potrzeb odbiorcy."
        
        # Dodanie informacji o długościach sekcji, jeśli są dostępne
        length_instructions = ""
        if lengths:
            length_instructions = f"""
            DŁUGOŚCI SEKCJI:
            - Wstęp: około {lengths.get('intro', 300)} znaków
            - Dlaczego powstał ten ebook: około {lengths.get('why_created', 300)} znaków
            - Co znajdziesz w środku: około {lengths.get('contents', 400)} znaków
            - Jakie problemy rozwiązuje: około {lengths.get('problems_solved', 350)} znaków
            - Dla kogo jest ten ebook: około {lengths.get('target_audience', 300)} znaków
            - Fragment lub przykład: około {lengths.get('example', 300)} znaków
            """
        
        # Przygotowanie promptu dla OpenAI z naciskiem na wysoki standard marketingowy
        prompt = f"""
        Przeanalizuj poniższy e-book i utwórz wysokiej jakości treści marketingowe dopasowane dla następującej persony:
        
        PERSONA:
        {persona}
        
        TON KOMUNIKACJI:
        {tone_instruction}
        
        {length_instructions}
        
        TREŚĆ E-BOOKA:
        {pdf_text}
        
        Zwróć wynik w formacie JSON z następującymi kluczami:
        1. intro - Kontekst i problem odbiorcy. Przedstawienie wyzwania, które rozwiązuje ebook. Nie dodawaj tytułów, tylko samą treść.
        2. why_created - Geneza powstania e-booka, inspiracja, potrzeba. Nie dodawaj tytułów, tylko samą treść.
        3. contents - Spis treści / kluczowe rozdziały. Lista 3–5 ważnych rozdziałów lub modułów z krótkim opisem. Nie dodawaj tytułów, tylko samą treść.
        4. problems_solved - Wartość praktyczna, konkretne umiejętności, efekty, decyzje, które pomoże podjąć. Nie dodawaj tytułów, tylko samą treść.
        5. target_audience - Dla kogo jest ten ebook (i dla kogo nie). Nie dodawaj tytułów, tylko samą treść.
        6. example - Fragment lub przykład z ebooka. Cytat, mini-case — pokazujący styl i wartość. Nie dodawaj tytułów, tylko samą treść.
        
        WAŻNE WSKAZÓWKI DLA TWORZENIA TREŚCI:
        - Stwórz treści, które są WYSOCE ANGAŻUJĄCE i PRZEKONUJĄCE marketingowo
        - Używaj języka, który wzbudza emocje i zainteresowanie
        - Zastosuj konkretne, obrazowe przykłady i opisy
        - Wykorzystaj krótkie, dynamiczne zdania naprzemiennie z bardziej złożonymi
        - Podkreśl unikalne korzyści i wartość, wykorzystaj tzw. "unique selling points"
        - Pisz w drugiej osobie (Ty, Twój) aby stworzyć bezpośredni kontakt z czytelnikiem
        - Używaj aktywnych czasowników i unikaj strony biernej
        - NIE DODAWAJ TYTUŁÓW SEKCJI, tylko ich zawartość
        - Dodaj odpowiednie znaczniki HTML dla formatowania (pogrubienie, kursywa, listy)
        - Każda sekcja musi być starannie opracowana i dopasowana do potrzeb persony
        
        Odpowiedź musi być w formacie JSON, używaj znaczników HTML dla formatowania.
        WAŻNE: Zwróć TYLKO obiekt JSON bez dodatkowego tekstu przed lub po.
        """
        
        # Wywołanie API OpenAI (nowy sposób w wersji >=1.0.0)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Jesteś ekspertem w tworzeniu najwyższej klasy treści marketingowych i perswazyjnych. Twoje teksty charakteryzują się wysoką skutecznością, profesjonalizmem i doskonałym dopasowaniem do grupy docelowej."},
                {"role": "user", "content": prompt}
            ]
        )
        
        # Parsowanie odpowiedzi do JSON (nowy sposób w wersji >=1.0.0)
        content = response.choices[0].message.content
        
        # Wydobycie fragmentu JSON z odpowiedzi (na wypadek, gdyby model dodał tekst przed/po JSON)
        json_match = re.search(r'({[\s\S]*})', content)
        if json_match:
            json_content = json.loads(json_match.group(1))
        else:
            json_content = json.loads(content)
        
        # Normalizacja danych JSON przed walidacją
        json_content = normalize_json_data(json_content)
        
        # Dodatkowe sprawdzenie, czy treści nie zawierają tytułów sekcji
        for key in json_content:
            # Usuwamy typowe tytuły sekcji jeśli się pojawią
            value = json_content[key]
            value = re.sub(r'^(Wstęp|Wprowadzenie|Kontekst)[:;-]\s*', '', value, flags=re.IGNORECASE)
            value = re.sub(r'^(Dlaczego|Geneza|Powód)[:;-]\s*', '', value, flags=re.IGNORECASE)
            value = re.sub(r'^(Zawartość|Spis treści|Co znajdziesz)[:;-]\s*', '', value, flags=re.IGNORECASE)
            value = re.sub(r'^(Problemy|Rozwiązania|Korzyści)[:;-]\s*', '', value, flags=re.IGNORECASE)
            value = re.sub(r'^(Dla kogo|Odbiorcy|Grupa docelowa)[:;-]\s*', '', value, flags=re.IGNORECASE)
            value = re.sub(r'^(Przykład|Fragment|Cytat)[:;-]\s*', '', value, flags=re.IGNORECASE)
            json_content[key] = value
            
        # Walidacja JSON według schematu
        validate(instance=json_content, schema=JSON_SCHEMA)
        return json_content
    
    except json.JSONDecodeError as e:
        st.error(f"Błąd parsowania JSON: {e}")
        st.code(content)  # Wyświetl surową odpowiedź, aby pomóc w diagnostyce
        return None
    except ValidationError as e:
        st.error(f"Błąd walidacji JSON: {e}")
        return None
    except Exception as e:
        st.error(f"Błąd podczas analizy z OpenAI: {e}")
        return None

# Funkcja do podstawiania wartości z JSON w kreacji mailowej
def replace_variables_in_html(html_content, json_data):
    # Wzór do wykrywania zmiennych w formie {!{ nazwa_zmiennej }!}
    pattern = r'\{!\{\s*([a-zA-Z_]+)\s*\}!\}'
    
    def replacer(match):
        var_name = match.group(1)
        if var_name in json_data:
            return json_data[var_name]
        else:
            return f"[Zmienna {var_name} nie znaleziona]"
    
    # Zastąpienie wszystkich zmiennych w HTML
    result = re.sub(pattern, replacer, html_content)
    return result

# Funkcja do kopiowania kodu do schowka
def get_copy_button_html(text):
    encoded_text = base64.b64encode(text.encode()).decode()
    return f"""
    <script>
    function copyToClipboard() {{
        const textarea = document.createElement('textarea');
        textarea.value = atob("{encoded_text}");
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        document.getElementById('copy-status').innerHTML = 'Skopiowano!';
        setTimeout(() => {{
            document.getElementById('copy-status').innerHTML = '';
        }}, 2000);
    }}
    </script>
    <button onclick="copyToClipboard()">Kopiuj do schowka</button>
    <span id="copy-status" style="margin-left: 10px;"></span>
    """

# Inicjalizacja sesji
def init_session_state():
    if "current_json_data" not in st.session_state:
        st.session_state.current_json_data = None
    
    if "current_html" not in st.session_state:
        st.session_state.current_html = None

# Główna aplikacja Streamlit
def main():
    st.title("Generator treści marketingowych dla e-booków")
    
    # Inicjalizacja stanu sesji
    init_session_state()
    
    # Obsługa klucza API w Streamlit Cloud
    api_key = os.environ.get("OPENAI_API_KEY")
    
    # Jeśli nie ma klucza w zmiennych środowiskowych, sprawdź w sekretach Streamlit
    if not api_key and hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    
    # Jeśli nadal nie ma klucza, dodaj pole do jego wprowadzenia
    if not api_key:
        api_key = st.sidebar.text_input("Klucz API OpenAI", type="password")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
    
    # Konfiguracja modelu OpenAI
    st.sidebar.header("Konfiguracja")
    openai_model = st.sidebar.selectbox(
        "Model OpenAI",
        ["o4-mini", "gpt-4", "gpt-3.5-turbo"],
        index=0,
        help="Wybierz model OpenAI"
    )
    
    tone = st.sidebar.selectbox(
        "Ton komunikacji",
        ["profesjonalny", "przyjazny", "zabawny", "motywujący", "poważny", "empatyczny"],
        index=1,
        help="Wybierz preferowany ton komunikacji dla generowanych treści."
    )
    
    # Dodajemy kontrolę długości sekcji
    st.sidebar.subheader("Długość sekcji (liczba znaków):")
    intro_length = st.sidebar.slider("Wstęp", 150, 800, 300)
    why_created_length = st.sidebar.slider("Dlaczego powstał", 150, 800, 300)
    contents_length = st.sidebar.slider("Zawartość", 200, 1000, 400)
    problems_solved_length = st.sidebar.slider("Rozwiązania problemów", 200, 800, 350)
    target_audience_length = st.sidebar.slider("Grupa docelowa", 150, 800, 300)
    example_length = st.sidebar.slider("Przykład", 150, 800, 300)
    
    st.sidebar.markdown("""
    **Opis tonów komunikacji:**
    - **Profesjonalny** – rzeczowy, uprzejmy, bez emocjonalnych wyrażeń
    - **Przyjazny** – ciepły, osobisty, otwarty
    - **Zabawny** – z humorem, żartobliwy
    - **Motywujący** – podnoszący na duchu, zachęcający
    - **Poważny** – zdystansowany, neutralny, formalny
    - **Empatyczny** – wspierający, rozumiejący emocje odbiorcy
    """)
    
    with st.form("input_form"):
        # Upload pliku PDF
        uploaded_file = st.file_uploader("Wybierz plik PDF z e-bookiem", type="pdf")
        
        # Pole na opis persony
        persona = st.text_area("Persona (opis grupy docelowej)", 
                               height=150,
                               help="Opisz grupę docelową, dla której ma być przygotowana treść marketingowa.")
        
        # Pole na kod HTML kreacji mailowej
        html_template = st.text_area("Kreacja mailowa (kod HTML z zmiennymi w formacie {!{ nazwa_zmiennej }!})", 
                                    height=300,
                                    help="Wprowadź kod HTML kreacji mailowej z zmiennymi w formacie {!{ nazwa_zmiennej }!}")
        
        # Przycisk do analizy
        submit_button = st.form_submit_button("Analizuj i generuj treść")
    
    if submit_button and uploaded_file is not None and persona and html_template:
        # Inicjalizacja informacji o postępie
        progress_text = st.empty()
        progress_text.text("Odczytywanie pliku PDF...")
        progress_bar = st.progress(0)
        
        # Odczytanie zawartości PDF
        pdf_text = read_pdf(uploaded_file)
        
        if pdf_text:
            progress_bar.progress(25)
            progress_text.text("Analiza treści i generowanie wyników...")
            
            # Informacja o długości tekstu
            token_estimate = len(pdf_text) / 4  # Przybliżona liczba tokenów (4 znaki na token)
            if token_estimate > 100000:
                st.warning(f"Uwaga: Tekst zawiera około {int(token_estimate)} tokenów, co może przekroczyć limit kontekstu wybranego modelu.")
            
            # Analiza PDF i uzyskanie treści marketingowych
            lengths = {
                "intro": intro_length,
                "why_created": why_created_length,
                "contents": contents_length,
                "problems_solved": problems_solved_length,
                "target_audience": target_audience_length,
                "example": example_length
            }
            json_data = analyze_pdf_with_openai(pdf_text, persona, model=openai_model, tone=tone, lengths=lengths)
            
            progress_bar.progress(90)
            
            if json_data:
                # Zapisanie danych do sesji
                st.session_state.current_json_data = json_data
                
                progress_text.text("Analiza zakończona pomyślnie!")
                progress_bar.progress(100)
                
                # Wyświetlenie edytora wygenerowanych treści
                st.subheader("Edytuj wygenerowane treści:")
                edited_json = {}
                
                # Zakładki dla każdej sekcji
                edit_tabs = st.tabs(["Wstęp", "Dlaczego powstał", "Zawartość", "Rozwiązane problemy", "Grupa docelowa", "Przykład"])
                
                with edit_tabs[0]:
                    edited_json["intro"] = st.text_area("Wstęp — kontekst i problem odbiorcy", 
                                                      json_data["intro"], 
                                                      height=200,
                                                      help="Edytuj treść wstępu")
                
                with edit_tabs[1]:
                    edited_json["why_created"] = st.text_area("Dlaczego powstał ten ebook", 
                                                            json_data["why_created"], 
                                                            height=200,
                                                            help="Edytuj informacje o genezie powstania e-booka")
                
                with edit_tabs[2]:
                    edited_json["contents"] = st.text_area("Co znajdziesz w środku (spis treści / kluczowe rozdziały)", 
                                                         json_data["contents"], 
                                                         height=200,
                                                         help="Edytuj informacje o zawartości e-booka")
                
                with edit_tabs[3]:
                    edited_json["problems_solved"] = st.text_area("Jakie problemy rozwiązuje (wartość praktyczna)", 
                                                                json_data["problems_solved"], 
                                                                height=200,
                                                                help="Edytuj informacje o rozwiązywanych problemach")
                
                with edit_tabs[4]:
                    edited_json["target_audience"] = st.text_area("Dla kogo jest ten ebook (i dla kogo nie)", 
                                                                json_data["target_audience"], 
                                                                height=200,
                                                                help="Edytuj informacje o grupie docelowej")
                
                with edit_tabs[5]:
                    edited_json["example"] = st.text_area("Fragment lub przykład z ebooka", 
                                                        json_data["example"], 
                                                        height=200,
                                                        help="Edytuj przykład z e-booka")
                
                # Zastosowanie zmian
                apply_changes = st.button("Zastosuj zmiany")
                if apply_changes:
                    json_data = edited_json
                    st.session_state.current_json_data = json_data
                    st.success("Zmiany zostały zastosowane!")
                
                # Podstawienie wartości w kreacji mailowej
                final_html = replace_variables_in_html(html_template, json_data)
                st.session_state.current_html = final_html
                
                # Spróbujmy jeszcze jedną metodę - użyjmy komponentu HTML w bardziej bezpośredni sposób
                st.subheader("Podgląd kreacji:")
                
                # Przygotowanie HTML z CSS
                html_with_style = f"""
                <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    margin: 20px;
                    max-width: 800px;
                }}
                </style>
                {final_html}
                """
                
                # Używamy st.components.v1.html
                st.components.v1.html(html_with_style, height=600, scrolling=True)
                
                # Wyświetlenie końcowej kreacji (kod HTML)
                with st.expander("Pokaż kod HTML", expanded=False):
                    st.code(final_html, language="html")
                
                # Przycisk do kopiowania kodu
                st.subheader("Kopiuj kod do schowka:")
                st.markdown(get_copy_button_html(final_html), unsafe_allow_html=True)
            else:
                progress_text.text("Wystąpił błąd podczas analizy.")
                progress_bar.empty()
    
    elif submit_button:
        st.warning("Proszę wypełnić wszystkie pola formularza i dodać plik PDF.")

if __name__ == "__main__":
    main()