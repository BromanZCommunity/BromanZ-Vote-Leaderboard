# BromanZ Vote Leaderboard

Automatisch Discord vote-leaderboard voor **BromanZ Community**, gebaseerd op de officiële Top-Games voter-ranking API.

Het project draait ieder uur via **GitHub Actions**. Je hebt dus geen VPS, betaalde hosting of computer nodig die continu aanstaat.

## Wat het project doet

- Leest ieder uur de actuele Top-Games ranking.
- Beheert één vast Discord-bericht voor **Current Month**.
- Beheert één vast Discord-bericht voor **Previous Month**.
- Maakt beide berichten automatisch bij de eerste run.
- Wijzigt daarna steeds dezelfde twee berichten; het kanaal wordt niet volgespamd.
- Bewaart de laatste volledige snapshot in `data/state.json`.
- Archiveert de eindstand bij een maandwissel in `data/history/YYYY-MM.json`.
- Maakt een verwijderd leaderboardbericht automatisch opnieuw aan.
- Ondersteunt maximaal 50 zichtbare voters.
- Bevat bewust nog geen in-game rewards.

## Gebruikte Top-Games API

```text
GET https://api.top-games.net/v1/servers/TOKEN/players-ranking
```

De token staat nooit in de code. GitHub bewaart hem als Repository Secret.

## Installatie

### 1. Maak een GitHub repository

Maak op GitHub een nieuwe private repository, bijvoorbeeld:

```text
BromanZ-Vote-Leaderboard
```

Pak het ZIP-bestand uit en upload **de inhoud van de map**. De repository-root moet er zo uitzien:

```text
.github/workflows/update-leaderboard.yml
data/history/.gitkeep
data/state.json
tests/test_leaderboard.py
.gitignore
README.md
SETUP_CHECKLIST.md
requirements.txt
vote_leaderboard.py
```

Upload dus niet alleen het ZIP-bestand en voorkom een extra maplaag.

### 2. Maak een Discord-webhook

Open in Discord het kanaal waarin de boards moeten komen:

1. **Edit Channel**.
2. **Integrations**.
3. **Webhooks**.
4. **New Webhook**.
5. Geef hem bijvoorbeeld de naam `BromanZ Vote Leaderboard`.
6. Controleer of het juiste kanaal is geselecteerd.
7. Kies **Copy Webhook URL**.

Behandel de webhook-URL als een wachtwoord. Plaats hem nooit in de code, Discord-chat of een openbaar GitHub-bestand.

### 3. Voeg GitHub Secrets toe

Open de repository en ga naar:

```text
Settings → Secrets and variables → Actions → Secrets
```

Maak exact deze twee Repository Secrets:

| Secret | Waarde |
|---|---|
| `TOP_GAMES_TOKEN` | De API/server-token uit het Top-Games beheerpaneel |
| `DISCORD_WEBHOOK_URL` | De volledige gekopieerde Discord-webhook-URL |

Je hoeft geen Discord bot, bot-token, channel-ID of message-ID aan te maken.

### 4. Stel optioneel het aantal spelers in

Standaard toont elk board maximaal 20 spelers. Voor een andere limiet ga je naar:

```text
Settings → Secrets and variables → Actions → Variables
```

Maak de Repository Variable:

```text
LEADERBOARD_LIMIT
```

Gebruik een waarde van 1 t/m 50.

### 5. Geef GitHub Actions schrijfrechten

Open:

```text
Settings → Actions → General → Workflow permissions
```

Selecteer **Read and write permissions** en sla dit op. Dit is nodig om `data/state.json` en de maandarchieven automatisch terug te schrijven.

### 6. Start de eerste test

Open:

```text
Actions → Update Vote Leaderboards → Run workflow
```

Na een succesvolle eerste run verschijnen twee berichten in het Discord-kanaal. De message-ID's worden automatisch opgeslagen in `data/state.json`.

## Automatische planning

De workflow draait:

- ieder uur rond minuut 7;
- dagelijks nogmaals om 23:57 in de tijdzone `Europe/Amsterdam`.

De extra run vlak voor middernacht bewaart een zo laat mogelijke maand-snapshot. GitHub geeft aan dat geplande workflows bij drukte vertraagd kunnen worden. De gearchiveerde eindstand is daarom de laatste succesvolle Top-Games-snapshot vóór de reset, niet een garantie tot op de seconde.

## Discord-uitvoer

Het eerste bericht toont de huidige maand, bijvoorbeeld:

```text
🗳️ BromanZ Vote Leaderboard
Current Month • September 2026

🥇 PlayerOne — 42 votes
🥈 PlayerTwo — 35 votes
🥉 PlayerThree — 31 votes

🗳️ Total votes: 108
🔄 Updated automatically every hour
```

Het tweede bericht toont de definitieve vorige maand. Voor de eerste maandwissel meldt het dat er nog geen archief beschikbaar is.

## Data en maandwissel

`data/state.json` bevat:

- de actieve maand;
- de laatste volledige ranking;
- de twee Discord message-ID's;
- het tijdstip van de laatste succesvolle update.

Bij de eerste run in een nieuwe maand wordt de laatst bewaarde snapshot van de oude maand eerst opgeslagen als:

```text
data/history/2026-09.json
```

Daarna wordt de nieuwe actuele ranking opgehaald. Alleen het archief van de echte vorige kalendermaand wordt op het Previous Month-board getoond.

## Problemen oplossen

Open een mislukte run via **GitHub → Actions** en bekijk de stap `Update Discord vote leaderboards`.

Veel voorkomende meldingen:

| Melding | Waarschijnlijke oorzaak |
|---|---|
| Missing `TOP_GAMES_TOKEN` | Secret ontbreekt of heeft een andere naam |
| Missing `DISCORD_WEBHOOK_URL` | Webhook-secret ontbreekt |
| Top-Games HTTP 401/403 | Token klopt niet of heeft geen toegang |
| Discord HTTP 401 | Webhook-URL of webhook-token klopt niet meer |
| Discord HTTP 404 | De webhook zelf is verwijderd; maak een nieuwe en vervang het Secret |

Als alleen één leaderboardbericht handmatig uit Discord is verwijderd, maakt de workflow dat bericht tijdens de volgende run opnieuw aan.

## Lokaal testen

Voor ontwikkelaars:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Voor een echte lokale run moeten `TOP_GAMES_TOKEN` en `DISCORD_WEBHOOK_URL` als omgevingsvariabelen beschikbaar zijn.

## Veiligheid

- Commit nooit je Top-Games-token of Discord-webhook.
- Deel de tokens niet in screenshots of supportberichten.
- Reset/verwijder de Discord-webhook als de URL ooit openbaar is geworden.
- De code print geen volledige API- of webhook-URL bij netwerkfouten.

## Later uit te breiden

De bewaarde maandarchieven kunnen later worden gebruikt voor:

- in-game rewards;
- Top 3- of Top 10-export;
- Hall of Fame;
- maandwinnaar-announcements;
- statistieken op de BromanZ-website.
