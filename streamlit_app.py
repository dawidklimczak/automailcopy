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

# Lista wszystkich dostępnych zmiennych z opisami
ALL_VARIABLES = {
    "intro": "Wstęp — kontekst i problem odbiorcy",
    "why_created": "Dlaczego powstał ten ebook",
    "contents": "Co znajdziesz w środku (spis treści / kluczowe rozdziały)",
    "problems_solved": "Jakie problemy rozwiązuje (wartość praktyczna)",
    "target_audience": "Dla kogo jest ten ebook (i dla kogo nie)",
    "example": "Fragment lub przykład z ebooka",
    "call_to_action": "Wezwanie do działania, zachęta do pobrania/zakupu",
    "key_benefits": "Lista głównych korzyści z przeczytania e-booka",
    "guarantee": "Obietnica wartości, gwarancja rezultatów",
    "testimonials": "Opinie czytelników, społeczny dowód słuszności",
    "value_summary": "Podsumowanie najważniejszych punktów i korzyści",
    "faq": "Najczęściej zadawane pytania z odpowiedziami",
    "urgency": "Element budujący poczucie pilności decyzji",
    "comparison": "Co wyróżnia ten e-book na tle konkurencji",
    "transformation_story": "Historia transformacji dzięki wiedzy z e-booka",
    "author_credentials": "Kwalifikacje autora (opcjonalne)"
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

# Funkcja do analizy szablonu HTML i znalezienia używanych zmiennych
def extract_variables_from_template(html_template):
    # Wzór do wykrywania zmiennych w formie {!{ nazwa_zmiennej }!}
    pattern = r'\{!\{\s*([a-zA-Z_]+)\s*\}!\}'
    
    # Znajdź wszystkie wystąpienia zmiennych
    matches = re.findall(pattern, html_template)
    
    # Utwórz unikalny zbiór zmiennych (eliminując duplikaty)
    unique_variables = set(matches)
    
    return unique_variables

# Funkcja do dynamicznego tworzenia schematu JSON na podstawie wymaganych zmiennych
def create_dynamic_json_schema(required_variables):
    schema = {
        "type": "object",
        "required": list(required_variables),
        "properties": {}
    }
    
    # Dodanie właściwości dla każdej wymaganej zmiennej
    for var in required_variables:
        if var in ALL_VARIABLES:
            schema["properties"][var] = {
                "type": "string", 
                "description": ALL_VARIABLES[var]
            }
    
    return schema

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
    
    # Podobnie dla sekcji FAQ - jeśli jest listą, konwertuj na prostą listę HTML
    if "faq" in data and isinstance(data["faq"], list):
        html_content = ""
        for item in data["faq"]:
            if isinstance(item, dict) and "pytanie" in item and "odpowiedz" in item:
                html_content += f"<strong>{item['pytanie']}</strong><br>{item['odpowiedz']}<br><br>"
            elif isinstance(item, dict) and "question" in item and "answer" in item:
                html_content += f"<strong>{item['question']}</strong><br>{item['answer']}<br><br>"
        data["faq"] = html_content
    
    # Podobnie dla sekcji key_benefits - jeśli jest listą, konwertuj na prostą listę HTML
    if "key_benefits" in data and isinstance(data["key_benefits"], list):
        html_content = "<ul>"
        for item in data["key_benefits"]:
            if isinstance(item, str):
                html_content += f"<li>{item}</li>"
            elif isinstance(item, dict) and "benefit" in item:
                html_content += f"<li>{item['benefit']}</li>"
        html_content += "</ul>"
        data["key_benefits"] = html_content
    
    # Podobnie dla sekcji testimonials - jeśli jest listą, konwertuj na prosty tekst
    if "testimonials" in data and isinstance(data["testimonials"], list):
        html_content = ""
        for item in data["testimonials"]:
            if isinstance(item, str):
                html_content += f"\"{item}\"<br><br>"
            elif isinstance(item, dict) and "text" in item and "author" in item:
                html_content += f"\"{item['text']}\" - {item['author']}<br><br>"
            elif isinstance(item, dict) and "testimonial" in item:
                html_content += f"\"{item['testimonial']}\"<br><br>"
        data["testimonials"] = html_content
    
    # Upewnienie się, że wszystkie pola są stringami
    for key in data:
        if not isinstance(data[key], str):
            # Konwersja innych typów na string
            if isinstance(data[key], list):
                data[key] = ", ".join(str(item) for item in data[key])
            else:
                data[key] = str(data[key])
    
    # Usunięcie wszelkich niepotrzebnych divów i klas
    for key in data:
        if isinstance(data[key], str):
            # Uproszczenie struktury HTML, usunięcie div z klasami
            data[key] = re.sub(r'<div\s+class="[^"]*">(.*?)</div>', r'\1', data[key], flags=re.DOTALL)
            # Usunięcie pozostałych divów
            data[key] = re.sub(r'<div>(.*?)</div>', r'\1', data[key], flags=re.DOTALL)
            # Usunięcie atrybutów class z innych tagów
            data[key] = re.sub(r'<([a-z]+)\s+class="[^"]*"', r'<\1', data[key])
    
    return data

# Funkcja do generowania sekcji dla kwalifikacji autora
def generate_author_credentials(author_info, model="o4-mini", api_key=None):
    if not author_info or author_info.strip() == "":
        return None
    
    try:
        # Sprawdzenie, czy klucz API OpenAI jest ustawiony
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
            if not api_key:
                return author_info  # Fallback do oryginalnych danych
        
        # Inicjalizacja klienta OpenAI
        client = OpenAI(api_key=api_key)
        
        # Prompt dla AI do przetworzenia informacji o autorze
        prompt = f"""
        Na podstawie poniższych surowych informacji o autorze, stwórz profesjonalny, 
        angażujący i zwięzły biogram podkreślający jego kompetencje, doświadczenie i autorytet. 
        Napisz w trzeciej osobie. Użyj maksymalnie 3-4 zdań.
        
        INFORMACJE O AUTORZE:
        {author_info}
        
        Zwróć tylko przetworzoną treść bez dodatkowych tytułów, wprowadzeń czy formatowań.
        Możesz używać podstawowego formatowania HTML (<strong>, <em>) dla podkreślenia 
        kluczowych informacji.
        """
        
        # Wywołanie API OpenAI
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Jesteś ekspertem w tworzeniu profesjonalnych biogramów autorów."},
                {"role": "user", "content": prompt}
            ]
        )
        
        # Zwrócenie wygenerowanego biogramu
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        # W przypadku błędu, zwróć oryginalne dane
        st.warning(f"Nie udało się przetworzyć informacji o autorze. Używam oryginalnych danych.")
        return author_info

# Funkcja do wywołania API OpenAI dla wymaganych zmiennych
def analyze_pdf_with_openai(pdf_text, persona, required_variables, author_info="", model="o4-mini", tone="przyjazny", lengths=None):
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
            length_instructions = "DŁUGOŚCI SEKCJI:\n"
            for var in required_variables:
                if var in lengths:
                    length_instructions += f"- {var}: około {lengths.get(var)} znaków\n"
        
        # Informacje o autorze
        author_instructions = ""
        if "author_credentials" in required_variables and author_info and author_info.strip():
            author_instructions = f"""
            INFORMACJE O AUTORZE:
            {author_info}
            
            Wykorzystaj powyższe informacje by stworzyć przekonującą sekcję author_credentials.
            """
        
        # Przygotowanie listy wymaganych zmiennych z opisami
        variables_instructions = "WYMAGANE ZMIENNE:\n"
        for var in required_variables:
            if var in ALL_VARIABLES:
                variables_instructions += f"{var} - {ALL_VARIABLES[var]}\n"
        
        # Przygotowanie promptu dla OpenAI koncentrując się tylko na wymaganych zmiennych
        prompt = f"""
        Przeanalizuj poniższy e-book i utwórz wysokiej jakości treści marketingowe dopasowane dla następującej persony.
        UWAGA: Generuj TYLKO treści dla wymaganych zmiennych wymienionych poniżej - nie dodawaj innych zmiennych.
        
        PERSONA:
        {persona}
        
        TON KOMUNIKACJI:
        {tone_instruction}
        
        {variables_instructions}
        
        {length_instructions}
        
        {author_instructions}
        
        TREŚĆ E-BOOKA:
        {pdf_text}
        
        Zwróć wynik w formacie JSON zawierający TYLKO poniższe wymagane klucze:
        """
        
        # Dodaj opis każdej wymaganej zmiennej
        for i, var in enumerate(required_variables, 1):
            if var in ALL_VARIABLES:
                prompt += f"\n{i}. {var} - {ALL_VARIABLES[var]}. Nie dodawaj tytułów, tylko samą treść."
        
        prompt += """
        
        WAŻNE WSKAZÓWKI DLA TWORZENIA TREŚCI:
        - Stwórz treści, które są WYSOCE ANGAŻUJĄCE i PRZEKONUJĄCE marketingowo
        - Używaj języka, który wzbudza emocje i zainteresowanie
        - Zastosuj konkretne, obrazowe przykłady i opisy
        - Wykorzystaj krótkie, dynamiczne zdania naprzemiennie z bardziej złożonymi
        - Podkreśl unikalne korzyści i wartość, wykorzystaj tzw. "unique selling points"
        - Pisz w drugiej osobie (Ty, Twój) aby stworzyć bezpośredni kontakt z czytelnikiem
        - Używaj aktywnych czasowników i unikaj strony biernej
        - NIE DODAWAJ TYTUŁÓW SEKCJI, tylko ich zawartość
        - UŻYWAJ TYLKO PODSTAWOWEGO FORMATOWANIA HTML - wyłącznie <strong>, <em>, <br>, <li> dla list oraz <ul> dla list punktowanych
        - NIE DODAWAJ znaczników <div>, <span>, <p>, <blockquote>, <dl>, atrybutów 'class', 'id' lub jakichkolwiek innych elementów formatowania
        - Każda sekcja musi być starannie opracowana i dopasowana do potrzeb persony
        
        Odpowiedź musi być w formacie JSON, używaj minimalnego formatowania HTML.
        WAŻNE: Zwróć TYLKO obiekt JSON bez dodatkowego tekstu przed lub po.
        """
        
        # Wywołanie API OpenAI
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Jesteś ekspertem w tworzeniu najwyższej klasy treści marketingowych i perswazyjnych. Twoje teksty charakteryzują się wysoką skutecznością, profesjonalizmem i doskonałym dopasowaniem do grupy docelowej."},
                {"role": "user", "content": prompt}
            ]
        )
        
        # Parsowanie odpowiedzi do JSON
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
        title_patterns = {
            "intro": r'^(Wstęp|Wprowadzenie|Kontekst)[:;-]\s*',
            "why_created": r'^(Dlaczego|Geneza|Powód)[:;-]\s*',
            "contents": r'^(Zawartość|Spis treści|Co znajdziesz)[:;-]\s*',
            "problems_solved": r'^(Problemy|Rozwiązania|Korzyści)[:;-]\s*',
            "target_audience": r'^(Dla kogo|Odbiorcy|Grupa docelowa)[:;-]\s*',
            "example": r'^(Przykład|Fragment|Cytat)[:;-]\s*',
            "call_to_action": r'^(Wezwanie|CTA|Działaj|Zrób)[:;-]\s*',
            "key_benefits": r'^(Korzyści|Zalety|Benefity)[:;-]\s*',
            "guarantee": r'^(Gwarancja|Obietnica|Zapewnienie)[:;-]\s*',
            "testimonials": r'^(Opinie|Rekomendacje|Co mówią)[:;-]\s*',
            "value_summary": r'^(Podsumowanie|Wartość|W skrócie)[:;-]\s*',
            "faq": r'^(FAQ|Pytania|Q&A)[:;-]\s*',
            "urgency": r'^(Pilne|Ogranicz|Nie czekaj)[:;-]\s*',
            "comparison": r'^(Porównanie|Wyróżnienie|Co nas wyróżnia)[:;-]\s*',
            "transformation_story": r'^(Historia|Transformacja|Zmiana|Case study)[:;-]\s*'
        }
        
        for key, pattern in title_patterns.items():
            if key in json_content:
                value = json_content[key]
                json_content[key] = re.sub(pattern, '', value, flags=re.IGNORECASE)
        
        # Walidacja JSON według dynamicznie utworzonego schematu
        json_schema = create_dynamic_json_schema(required_variables)
        validate(instance=json_content, schema=json_schema)
        
        # Jeśli potrzebny jest author_credentials, a nie został wygenerowany
        if "author_credentials" in required_variables and "author_credentials" not in json_content and author_info:
            json_content["author_credentials"] = generate_author_credentials(author_info, model=model, api_key=api_key)
        
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
    
    if "required_variables" not in st.session_state:
        st.session_state.required_variables = set()

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
        index=1,  # Domyślny ton: przyjazny
        help="Wybierz preferowany ton komunikacji dla generowanych treści."
    )
    
    # Dokumentacja zmiennych w panelu bocznym
    with st.sidebar.expander("📚 Dokumentacja dostępnych zmiennych", expanded=False):
        st.markdown("""
        ### Podstawowe zmienne

        | Zmienna | Opis |
        |---------|------|
        | `intro` | Wstęp, kontekst problemu |
        | `why_created` | Powód powstania e-booka |
        | `contents` | Spis treści/rozdziały |
        | `problems_solved` | Rozwiązywane problemy |
        | `target_audience` | Dla kogo jest e-book |
        | `example` | Fragment z e-booka |

        ### Elementy marketingowe

        | Zmienna | Opis |
        |---------|------|
        | `call_to_action` | Wezwanie do działania |
        | `key_benefits` | Główne korzyści |
        | `guarantee` | Obietnica/gwarancja |
        | `testimonials` | Opinie czytelników |
        | `value_summary` | Podsumowanie wartości |
        | `faq` | Pytania i odpowiedzi |
        | `urgency` | Element pilności |
        | `comparison` | Porównanie z konkurencją |
        | `transformation_story` | Historia transformacji |
        | `author_credentials` | O autorze (opcjonalne) |
        
        #### Użycie w szablonie HTML:
        ```html
        <div class="intro">
          {!{ intro }!}
        </div>
        ```
        """)
        
        st.markdown("💡 **Wskazówka:** Zmienne zawierają tylko podstawowe formatowanie HTML (bold, italic, listy).")
    
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
        
        # Nowe pole na informacje o autorze
        author_info = st.text_area("Informacje o autorze (opcjonalne)", 
                                  height=150,
                                  help="Podaj informacje o autorze, takie jak wykształcenie, doświadczenie, osiągnięcia, które zwiększą wiarygodność materiału.")
        
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
            progress_bar.progress(20)
            progress_text.text("Analizowanie szablonu HTML i identyfikacja wymaganych zmiennych...")
            
            # Analiza szablonu HTML i identyfikacja używanych zmiennych
            required_variables = extract_variables_from_template(html_template)
            
            # Dodaj author_credentials jeśli podano informacje o autorze
            if author_info and author_info.strip():
                required_variables.add("author_credentials")
            
            # Zapisz listę wymaganych zmiennych w sesji
            st.session_state.required_variables = required_variables
            
            # Sprawdź, czy są jakieś zidentyfikowane zmienne
            if not required_variables:
                st.error("Nie znaleziono żadnych zmiennych w szablonie HTML. Upewnij się, że używasz poprawnego formatu {!{ nazwa_zmiennej }!}")
                progress_bar.empty()
                return
            
            # Wyświetl znalezione zmienne
            progress_bar.progress(30)
            progress_text.text(f"Znaleziono {len(required_variables)} zmiennych w szablonie: {', '.join(required_variables)}")
            
            # Przygotowanie panelu do ustawienia długości zmiennych
            st.subheader("Dostosuj długość dla każdej zmiennej:")
            
            # Podziel zmienne na grupy po 4
            variable_groups = [list(required_variables)[i:i+4] for i in range(0, len(required_variables), 4)]
            
            # Stwórz zakładki dla każdej grupy
            if len(variable_groups) > 1:
                tab_names = [f"Grupa {i+1}" for i in range(len(variable_groups))]
                length_tabs = st.tabs(tab_names)
            else:
                length_tabs = [st]  # Jeśli jest tylko jedna grupa, używamy głównego obszaru
            
            # Dla każdej zakładki/grupy
            lengths = {}
            for i, group in enumerate(variable_groups):
                with length_tabs[i] if len(variable_groups) > 1 else length_tabs[0]:
                    # Dla każdej zmiennej w grupie
                    for var in group:
                        # Określ domyślną długość w zależności od typu zmiennej
                        default_length = 300
                        if var in ["contents", "faq", "testimonials"]:
                            default_length = 600
                        elif var in ["key_benefits", "problems_solved"]:
                            default_length = 400
                        
                        # Stwórz suwak do ustawienia długości
                        lengths[var] = st.slider(
                            f"{var.replace('_', ' ').title()}", 
                            min_value=100, 
                            max_value=1000, 
                            value=default_length,
                            help=f"Dostosuj długość dla zmiennej {var}"
                        )
            
            # Generuj treści
            generate_button = st.button("Generuj treści")
            
            if generate_button:
                progress_bar.progress(40)
                progress_text.text("Generowanie treści dla wybranych zmiennych...")
                
                # Informacja o długości tekstu
                token_estimate = len(pdf_text) / 4  # Przybliżona liczba tokenów (4 znaki na token)
                if token_estimate > 100000:
                    st.warning(f"Uwaga: Tekst zawiera około {int(token_estimate)} tokenów, co może przekroczyć limit kontekstu wybranego modelu.")
                
                # Analiza PDF i uzyskanie treści marketingowych tylko dla wymaganych zmiennych
                json_data = analyze_pdf_with_openai(
                    pdf_text, 
                    persona, 
                    required_variables, 
                    author_info, 
                    model=openai_model, 
                    tone=tone, 
                    lengths=lengths
                )
                
                progress_bar.progress(90)
                
                if json_data:
                    # Zapisanie danych do sesji
                    st.session_state.current_json_data = json_data
                    
                    progress_text.text("Generowanie zakończone pomyślnie!")
                    progress_bar.progress(100)
                    
                    # Wyświetlenie edytora wygenerowanych treści
                    st.subheader("Edytuj wygenerowane treści:")
                    
                    # Podziel zmienne na grupy dla lepszej organizacji
                    variable_groups = {
                        "Podstawowe informacje": ["intro", "why_created", "contents", "problems_solved", "target_audience", "example"],
                        "Korzyści i wartość": ["key_benefits", "guarantee", "value_summary", "comparison"],
                        "Elementy perswazyjne": ["call_to_action", "testimonials", "urgency", "transformation_story"],
                        "Dodatkowe elementy": ["faq", "author_credentials"]
                    }
                    
                    # Utworzenie zakładek dla grup
                    group_names = []
                    for group_name, vars_in_group in variable_groups.items():
                        # Sprawdź, czy grupa zawiera jakiekolwiek wymagane zmienne
                        if any(var in required_variables for var in vars_in_group):
                            group_names.append(group_name)
                    
                    group_tabs = st.tabs(group_names)
                    
                    # Dla każdej grupy
                    edited_json = {}
                    tab_index = 0
                    
                    for group_name, vars_in_group in variable_groups.items():
                        # Jeśli grupa zawiera wymagane zmienne
                        group_vars = [var for var in vars_in_group if var in required_variables]
                        if group_vars:
                            with group_tabs[tab_index]:
                                # Dla każdej zmiennej w grupie
                                for var in group_vars:
                                    if var in json_data:
                                        edited_json[var] = st.text_area(
                                            f"{var.replace('_', ' ').title()}", 
                                            json_data[var], 
                                            height=200
                                        )
                            tab_index += 1
                    
                    # Zastosowanie zmian
                    apply_changes = st.button("Zastosuj zmiany")
                    if apply_changes:
                        # Upewnij się, że wszystkie klucze są zachowane
                        for key in json_data:
                            if key not in edited_json:
                                edited_json[key] = json_data[key]
                        
                        json_data = edited_json
                        st.session_state.current_json_data = json_data
                        st.success("Zmiany zostały zastosowane!")
                    
                    # Podstawienie wartości w kreacji mailowej
                    final_html = replace_variables_in_html(html_template, json_data)
                    st.session_state.current_html = final_html
                    
                    # Podgląd kreacji
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
                    h1, h2, h3, h4, h5, h6 {{
                        color: #2c3e50;
                        margin-top: 1.5em;
                        margin-bottom: 0.5em;
                    }}
                    p {{
                        margin-bottom: 1em;
                    }}
                    ul, ol {{
                        margin-bottom: 1em;
                        padding-left: 2em;
                    }}
                    blockquote {{
                        border-left: 4px solid #ddd;
                        padding: 0.5em 1em;
                        margin: 1em 0;
                        background-color: #f9f9f9;
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
        st.warning("Proszę wypełnić wszystkie wymagane pola formularza i dodać plik PDF.")
        
    # Informacja o przykładowym szablonie
    with st.expander("Przykładowy szablon HTML", expanded=False):
        st.code("""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>E-book - marketing</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 0; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .logo { text-align: center; margin-bottom: 30px; }
        .header { text-align: center; padding: 30px 0; background-color: #f5f5f5; }
        .content { padding: 20px 0; }
        .section { margin-bottom: 30px; }
        h1 { color: #2c3e50; }
        h2 { color: #3498db; border-bottom: 1px solid #eee; padding-bottom: 10px; }
        .cta { background-color: #3498db; color: white; padding: 15px 25px; text-align: center; 
               display: block; margin: 30px auto; width: 200px; text-decoration: none; 
               border-radius: 5px; font-weight: bold; }
        .testimonials { background-color: #f9f9f9; padding: 20px; border-radius: 5px; font-style: italic; }
        .urgency { color: #e74c3c; font-weight: bold; text-align: center; margin: 20px 0; }
        .benefits li { margin-bottom: 10px; }
        .faq dt { font-weight: bold; margin-top: 15px; }
        .faq dd { margin-left: 0; margin-bottom: 15px; }
        .footer { text-align: center; padding: 20px; background-color: #2c3e50; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            Logo
        </div>
        
        <div class="header">
            <h1>Odkryj Nasz Najnowszy E-book!</h1>
            <p>{!{ intro }!}</p>
        </div>
        
        <div class="content">
            <div class="section">
                <h2>Dlaczego stworzyliśmy ten e-book?</h2>
                <p>{!{ why_created }!}</p>
            </div>
            
            <div class="section">
                <h2>Co znajdziesz w środku?</h2>
                <div>{!{ contents }!}</div>
            </div>
            
            <div class="section">
                <h2>Rozwiązane problemy</h2>
                <p>{!{ problems_solved }!}</p>
            </div>
            
            <div class="section">
                <h2>Dla kogo jest ten e-book?</h2>
                <p>{!{ target_audience }!}</p>
            </div>
            
            <div class="section">
                <h2>Fragment z e-booka</h2>
                <blockquote>{!{ example }!}</blockquote>
            </div>
            
            <div class="section">
                <h2>Kluczowe korzyści</h2>
                <div class="benefits">{!{ key_benefits }!}</div>
            </div>
            
            <div class="section">
                <h2>Nasza gwarancja</h2>
                <p>{!{ guarantee }!}</p>
            </div>
            
            <div class="section">
                <h2>Co mówią czytelnicy</h2>
                <div class="testimonials">{!{ testimonials }!}</div>
            </div>
            
            <div class="section">
                <h2>Historia transformacji</h2>
                <p>{!{ transformation_story }!}</p>
            </div>
            
            <div class="section">
                <h2>Dlaczego nasz e-book jest wyjątkowy</h2>
                <p>{!{ comparison }!}</p>
            </div>
            
            <div class="section">
                <h2>Najczęściej zadawane pytania</h2>
                <div class="faq">{!{ faq }!}</div>
            </div>
            
            <div class="section">
                <h2>Podsumowanie wartości</h2>
                <p>{!{ value_summary }!}</p>
            </div>
            
            <div class="urgency">
                {!{ urgency }!}
            </div>
            
            <a href="#" class="cta">
                {!{ call_to_action }!}
            </a>
            
            <div class="section">
                <h2>O autorze</h2>
                <div>{!{ author_credentials }!}</div>
            </div>
        </div>
        
        <div class="footer">
            <p>&copy; 2025 Nazwa Firmy. Wszelkie prawa zastrzeżone.</p>
        </div>
    </div>
</body>
</html>""", language="html")

if __name__ == "__main__":
    main()