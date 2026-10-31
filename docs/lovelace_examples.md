# Przykłady kart Lovelace (Dashboard Home Assistant)

Integracja **Librus Synergia** przygotowuje przychodzące wiadomości w czytelnej formie **Markdown** (oczyszczonej z błędnego HTML-a, stylów inline i nadmiarowych białych znaków) oraz przechowuje listy ostatnich ocen i uwag w atrybutach encji.

Poniżej znajdują się gotowe do skopiowania konfiguracje kart Lovelace dla każdego dziecka (zamień `<dziecko>` na identyfikator swojego dziecka, np. `jan_kowalski`).

---

## 1. Czytelna karta ostatniej wiadomości (Markdown Card)

Wyświetla pełną treść ostatniej wiadomości wraz z nadawcą, datą, tematem, informacją o załącznikach oraz sformatowanymi akapitami i klikalnymi linkami.

```yaml
type: markdown
title: 📩 Ostatnia wiadomość z Librusa
content: >
  {% set msg_sensor = 'sensor.librus_jan_kowalski_ostatnia_wiadomosc' %}
  {% set md = state_attr(msg_sensor, 'body_markdown') %}
  {% if md %}
  {{ md }}
  {% else %}
  *Brak wiadomości do wyświetlenia.*
  {% endif %}
```

---

## 2. Skrzynka odbiorcza — Lista ostatnich wiadomości (Rozwijane sekcje `<details>`)

Pozwala przeglądać wszystkie ostatnie wiadomości bezpośrednio na pulpicie Home Assistant, z wyróżnieniem nieprzeczytanych wiadomości (`🟢 NOWA`).

```yaml
type: markdown
title: 📬 Skrzynka odbiorcza Librus — Jan
content: >
  {% set inbox_sensor = 'sensor.librus_jan_kowalski_nieprzeczytane_wiadomosci' %}
  {% set messages = state_attr(inbox_sensor, 'recent_messages') or [] %}
  **Nieprzeczytane:** {{ states(inbox_sensor) }}

  ---
  {% for msg in messages %}
  <details {% if loop.first %}open{% endif %}>
    <summary>
      {% if msg.unread %}🟢 <b>[NOWA]</b>{% else %}✉️{% endif %}
      <b>{{ msg.subject }}</b> — <i>{{ msg.sender }}</i> ({{ msg.sent_at }})
      {% if msg.has_attachments %}📎{% endif %}
    </summary>

  {{ msg.body_markdown }}

  </details>
  <hr>
  {% else %}
  *Brak odebranych wiadomości.*
  {% endfor %}
```

---

## 3. Ostatnie oceny (Tabela Markdown)

Prezentuje ostatnie oceny z podziałem na przedmiot, wartość, wagę, kategorię, nauczyciela i komentarz.

```yaml
type: markdown
title: 🎓 Ostatnie oceny — Jan
content: >
  {% set grade_sensor = 'sensor.librus_jan_kowalski_ostatnia_ocena' %}
  {% set grades = state_attr(grade_sensor, 'recent_grades') or [] %}
  {% if grades %}
  | Data | Przedmiot | Ocena | Waga | Kategoria / Komentarz |
  | :--- | :--- | :---: | :---: | :--- |
  {% for g in grades -%}
  | {{ g.date }} | **{{ g.subject }}** | `{{ g.grade }}` | {{ g.weight or '-' }} | {{ g.category }}{% if g.comment %} — *{{ g.comment }}*{% endif %} |
  {% endfor %}
  {% else %}
  *Brak zarejestrowanych ocen.*
  {% endif %}
```

---

## 4. Uwagi i pochwały (Lista)

Wyświetla uwagi pozytywne i negatywne wraz z pełną treścią oraz imieniem nauczyciela.

```yaml
type: markdown
title: 📝 Uwagi i pochwały — Jan
content: >
  {% set notes_sensor = 'sensor.librus_jan_kowalski_uwagi_i_pochwaly' %}
  {% set notes = state_attr(notes_sensor, 'recent_notes') or [] %}
  👍 Pozytywne: **{{ state_attr(notes_sensor, 'positive_count') | default(0) }}** |
  ⚠️ Negatywne: **{{ state_attr(notes_sensor, 'negative_count') | default(0) }}**

  ---
  {% for n in notes %}
  - **{{ n.date }}** — {% if n.positive == true %}🟢 **Pochwała**{% elif n.positive == false %}🔴 **Uwaga**{% else %}ℹ️ **{{ n.type }}**{% endif %} ({{ n.teacher }}):
    > {{ n.content }}
  {% else %}
  *Brak uwag w dzienniku.*
  {% endfor %}
```

