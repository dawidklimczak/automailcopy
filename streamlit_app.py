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

# Definicja schematu JSON - dodane nowe sekcje
JSON_SCHEMA = {
    "type": "object",
    "required": [
        "intro", "why_created", "contents", "problems_solved", "target_audience", 
        "example", "call_to_action", "key_benefits", "guarantee", "testimonials", 
        "value_summary", "faq", "urgency", "comparison", "transformation_story"
    ],
    "properties": {
        "intro": {"type": "string", "description": "Wstęp — kontekst i problem odbiorcy"},
        "why_created": {"type": "string", "description": "Dlaczego powstał ten ebook"},
        "contents": {"type": "string", "description": "Co znajdziesz w środku (spis treści / kluczowe rozdziały)"},
        "problems_solved": {"type": "string", "description": "Jakie problemy rozwiązuje (wartość praktyczna)"},
        "target_audience": {"type": "string", "description": "Dla kogo jest ten ebook (i dla kogo nie)"},
        "example": {"type": "string", "description": "Fragment lub przykład z ebooka"},
        "call_to_action": {"type": "string", "description": "Wezwanie do działania, zachęta do pobrania/zakupu"},
        "key_benefits": {"type": "string", "description": "Lista głównych korzyści z przeczytania e-booka"},
        "guarantee": {"type": "string", "description": "Obietnica wartości, gwarancja rezultatów"},
        "testimonials": {"type": "string", "description": "Opinie czytelników, społeczny dowód słuszności"},
        "value_summary": {"type": "string", "description": "Podsumowanie najważniejszych punktów i korzyści"},
        "faq": {"type": "string", "description": "Najczęściej zadawane pytania z odpowiedziami"},
        "urgency": {"type": "string", "description": "Element budujący poczucie pilności decyzji"},
        "comparison": {"type": "string", "description": "Co wyróżnia ten e-book na tle konkurencji"},
        "transformation_story": {"type": "string", "description": "Historia transformacji dzięki wiedzy z e-booka"}
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
    
    # Podobnie dla sekcji FAQ - jeśli jest listą, konwertuj na HTML
    if "faq" in data and isinstance(data["faq"], list):
        html_content = "<dl>"
        for item in data["faq"]:
            if isinstance(item, dict) and "pytanie" in item and "odpowiedz" in item:
                html_content += f"<dt><strong>{item['pytanie']}</strong></dt><dd>{item['odpowiedz']}</dd>"
            elif isinstance(item, dict) and "question" in item and "answer" in item:
                html_content += f"<dt><strong>{item['question']}</strong></dt><dd>{item['answer']}</dd>"
        html_content += "</dl>"
        data["faq"] = html_content
    
    # Podobnie dla sekcji key_benefits - jeśli jest listą, konwertuj na HTML
    if "key_benefits" in data and isinstance(data["key_benefits"], list):
        html_content = "<ul>"
        for item in data["key_benefits"]:
            if isinstance(item, str):
                html_content += f"<li>{item}</li>"
            elif isinstance(item, dict) and "benefit" in item:
                html_content += f"<li>{item['benefit']}</li>"
        html_content += "</ul>"
        data["key_benefits"] = html_content
    
    # Podobnie dla sekcji testimonials - jeśli jest listą, konwertuj na HTML
    if "testimonials" in data and isinstance(data["testimonials"], list):
        html_content = "<blockquote>"
        for item in data["testimonials"]:
            if isinstance(item, str):
                html_content += f"<p>\"{item}\"</p>"
            elif isinstance(item, dict) and "text" in item and "author" in item:
                html_content += f"<p>\"{item['text']}\" - <em>{item['author']}</em></p>"
            elif isinstance(item, dict) and "testimonial" in item:
                html_content += f"<p>\"{item['testimonial']}\"</p>"
        html_content += "</blockquote>"
        data["testimonials"] = html_content
    
    # Upewnienie się, że wszystkie pola są stringami
    for key in data:
        if not isinstance(data[key], str):
            # Konwersja innych typów na string
            if isinstance(data[key], list):
                data[key] = ", ".join(str(item) for item in data[key])
            else:
                data[key] = str(data[key])
    
    return data

# Funkcja do generowania sekcji dla kwalifikacji autora, jeśli podano dane
def generate_author_credentials(author_info):
    if not author_info or author_info.strip() == "":
        return None
    
    return f"""<div class="author-credentials">
    {author_info}
    </div>"""

# Funkcja do wywołania API OpenAI
def analyze_pdf_with_openai(pdf_text, persona, author_info="", model="o4-mini", tone="przyjazny", lengths=None):
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
            length_instructions = """
            DŁUGOŚCI SEKCJI:
            """
            for key, value in lengths.items():
                length_instructions += f"- {key}: około {value} znaków\n"
        
        # Informacje o autorze
        author_instructions = ""
        if author_info and author_info.strip():
            author_instructions = f"""
            INFORMACJE O AUTORZE:
            {author_info}
            
            Wykorzystaj powyższe informacje by stworzyć przekonującą sekcję author_credentials.
            """
        
        # Przygotowanie promptu dla OpenAI z naciskiem na wysoki standard marketingowy
        prompt = f"""
        Przeanalizuj poniższy e-book i utwórz wysokiej jakości treści marketingowe dopasowane dla następującej persony:
        
        PERSONA:
        {persona}
        
        TON KOMUNIKACJI:
        {tone_instruction}
        
        {length_instructions}
        
        {author_instructions}
        
        TREŚĆ E-BOOKA:
        {pdf_text}
        
        Zwróć wynik w formacie JSON z następującymi kluczami:
        1. intro - Kontekst i problem odbiorcy. Przedstawienie wyzwania, które rozwiązuje ebook. Nie dodawaj tytułów, tylko samą treść.
        2. why_created - Geneza powstania e-booka, inspiracja, potrzeba. Nie dodawaj tytułów, tylko samą treść.
        3. contents - Spis treści / kluczowe rozdziały. Lista 3–5 ważnych rozdziałów lub modułów z krótkim opisem. Nie dodawaj tytułów, tylko samą treść.
        4. problems_solved - Wartość praktyczna, konkretne umiejętności, efekty, decyzje, które pomoże podjąć. Nie dodawaj tytułów, tylko samą treść.
        5. target_audience - Dla kogo jest ten ebook (i dla kogo nie). Nie dodawaj tytułów, tylko samą treść.
        6. example - Fragment lub przykład z ebooka. Cytat, mini-case — pokazujący styl i wartość. Nie dodawaj tytułów, tylko samą treść.
        7. call_to_action - Przekonujące wezwanie do działania, zachęcające do pobrania/zakupu e-booka. Nie dodawaj tytułów, tylko samą treść.
        8. key_benefits - Lista 3-5 głównych korzyści z przeczytania e-booka (konkretne rezultaty). Nie dodawaj tytułów, tylko samą treść.
        9. guarantee - Obietnica wartości lub gwarancja rezultatów, które czytelnik uzyska. Nie dodawaj tytułów, tylko samą treść.
        10. testimonials - 2-3 fikcyjne, ale realistyczne opinie zadowolonych czytelników w formie cytatów. Nie dodawaj tytułów, tylko samą treść.
        11. value_summary - Zwięzłe podsumowanie najważniejszych wartości i korzyści. Nie dodawaj tytułów, tylko samą treść.
        12. faq - 3-5 najczęściej zadawanych pytań z odpowiedziami, które rozwiewają wątpliwości. Nie dodawaj tytułów, tylko samą treść.
        13. urgency - Element budujący poczucie pilności i ograniczoności oferty. Nie dodawaj tytułów, tylko samą treść.
        14. comparison - Co wyróżnia ten e-book na tle innych materiałów o podobnej tematyce. Nie dodawaj tytułów, tylko samą treść.
        15. transformation_story - Krótka historia transformacji/zmiany, jaką przeszedł hipotetyczny odbiorca dzięki wiedzy z e-booka. Nie dodawaj tytułów, tylko samą treść.
        
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
        
        # Dodaj informacje o autorze, jeśli podane
        if author_info and author_info.strip():
            json_content["author_credentials"] = generate_author_credentials(author_info)
            
        # Walidacja JSON według schematu
        # Usuń author_credentials z listy wymaganych pól jeśli nie podano informacji o autorze
        if not author_info or author_info.strip() == "":
            json_schema_copy = JSON_SCHEMA.copy()
            if "author_credentials" in json_schema_copy.get("required", []):
                json_schema_copy["required"].remove("author_credentials")
            validate(instance=json_content, schema=json_schema_copy)
        else:
            # Dodaj author_credentials do schematu
            json_schema_copy = JSON_SCHEMA.copy()
            json_schema_copy["properties"]["author_credentials"] = {"type": "string", "description": "Kwalifikacje autora"}
            if "author_credentials" not in json_schema_copy.get("required", []):
                json_schema_copy["required"].append("author_credentials")
            validate(instance=json_content, schema=json_schema_copy)
        
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

# Funkcja do grupowania zakładek edycji
def create_tab_groups(json_data):
    # Wszystkie klucze z json_data
    all_keys = list(json_data.keys())
    
    # Definiujemy grupy zakładek
    tab_groups = {
        "Podstawowe informacje": ["intro", "why_created", "contents", "problems_solved", "target_audience", "example"],
        "Korzyści i wartość": ["key_benefits", "guarantee", "value_summary", "comparison"],
        "Elementy perswazyjne": ["call_to_action", "testimonials", "urgency", "transformation_story"],
        "Dodatkowe elementy": ["faq"]
    }
    
    # Dodajemy informacje o autorze, jeśli są dostępne
    if "author_credentials" in all_keys:
        tab_groups["Dodatkowe elementy"].append("author_credentials")
    
    return tab_groups

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
    
    # Zakładki dla ustawień długości
    length_tabs = st.sidebar.tabs(["Podstawowe", "Korzyści", "Perswazja", "Inne"])
    
    with length_tabs[0]:
        # Dodajemy kontrolę długości sekcji dla podstawowych elementów
        st.subheader("Długość sekcji (znaki):")
        intro_length = st.slider("Wstęp", 150, 800, 300)
        why_created_length = st.slider("Dlaczego powstał", 150, 800, 300)
        contents_length = st.slider("Zawartość", 200, 1000, 400)
        problems_solved_length = st.slider("Rozwiązania problemów", 200, 800, 350)
        target_audience_length = st.slider("Grupa docelowa", 150, 800, 300)
        example_length = st.slider("Przykład", 150, 800, 300)
    
    with length_tabs[1]:
        # Dodajemy kontrolę długości sekcji dla elementów korzyści i wartości
        st.subheader("Długość sekcji (znaki):")
        key_benefits_length = st.slider("Kluczowe korzyści", 200, 1000, 400)
        guarantee_length = st.slider("Gwarancja", 150, 800, 300)
        value_summary_length = st.slider("Podsumowanie wartości", 150, 800, 300)
        comparison_length = st.slider("Porównanie", 200, 1000, 400)
    
    with length_tabs[2]:
        # Dodajemy kontrolę długości sekcji dla elementów perswazyjnych
        st.subheader("Długość sekcji (znaki):")
        call_to_action_length = st.slider("Wezwanie do działania", 150, 800, 250)
        testimonials_length = st.slider("Opinie", 300, 1200, 500)
        urgency_length = st.slider("Pilność", 150, 800, 250)
        transformation_length = st.slider("Historia transformacji", 200, 1000, 400)
    
    with length_tabs[3]:
        # Dodajemy kontrolę długości sekcji dla dodatkowych elementów
        st.subheader("Długość sekcji (znaki):")
        faq_length = st.slider("FAQ", 300, 1500, 800)
        author_credentials_length = st.slider("O autorze", 150, 800, 300)
    
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
                "example": example_length,
                "call_to_action": call_to_action_length,
                "key_benefits": key_benefits_length,
                "guarantee": guarantee_length,
                "testimonials": testimonials_length,
                "value_summary": value_summary_length,
                "faq": faq_length,
                "urgency": urgency_length,
                "comparison": comparison_length,
                "transformation_story": transformation_length,
                "author_credentials": author_credentials_length
            }
            json_data = analyze_pdf_with_openai(pdf_text, persona, author_info, model=openai_model, tone=tone, lengths=lengths)
            
            progress_bar.progress(90)
            
            if json_data:
                # Zapisanie danych do sesji
                st.session_state.current_json_data = json_data
                
                progress_text.text("Analiza zakończona pomyślnie!")
                progress_bar.progress(100)
                
                # Wyświetlenie edytora wygenerowanych treści w grupach zakładek
                st.subheader("Edytuj wygenerowane treści:")
                
                # Tworzymy grupy zakładek
                tab_groups = create_tab_groups(json_data)
                group_tabs = st.tabs(list(tab_groups.keys()))
                
                edited_json = {}
                
                # Dla każdej grupy zakładek
                for i, (group_name, keys) in enumerate(tab_groups.items()):
                    with group_tabs[i]:
                        # Tworzymy zakładki dla każdej sekcji w grupie
                        if keys:
                            section_tabs = st.tabs([key.replace("_", " ").title() for key in keys])
                            
                            # Dla każdej sekcji tworzymy edytor
                            for j, key in enumerate(keys):
                                if key in json_data:
                                    with section_tabs[j]:
                                        edited_json[key] = st.text_area(
                                            f"Edytuj treść dla {key.replace('_', ' ').title()}", 
                                            json_data[key], 
                                            height=200
                                        )
                
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
                
                # Wyświetlenie kreacji w przeglądarce jako poprawnie renderowany HTML
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
                dl dt {{
                    font-weight: bold;
                    margin-top: 1em;
                }}
                dl dd {{
                    margin-left: 1em;
                    margin-bottom: 1em;
                }}
                .author-credentials {{
                    background-color: #f5f5f5;
                    padding: 1em;
                    border-radius: 5px;
                    margin: 1em 0;
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
                
                # Wyświetlenie informacji o dostępnych zmiennych
                with st.expander("Dostępne zmienne do użycia w szablonie HTML", expanded=False):
                    st.markdown("Poniżej znajduje się lista wszystkich dostępnych zmiennych, które możesz umieścić w swoim szablonie HTML:")
                    variables_list = ""
                    for key in json_data.keys():
                        variables_list += f"- `{{!{{ {key} }}!}}` - {key.replace('_', ' ').title()}\n"
                    st.markdown(variables_list)
                    
                    st.markdown("""
                    ### Przykład użycia w HTML:
                    ```html
                    <div class="intro">
                        {!{ intro }!}
                    </div>
                    
                    <div class="call-to-action">
                        {!{ call_to_action }!}
                    </div>
                    ```
                    """)
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