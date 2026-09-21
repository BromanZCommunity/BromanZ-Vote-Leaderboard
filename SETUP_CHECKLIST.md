# BromanZ Vote Leaderboard — Setup Checklist

- [ ] Private GitHub repository aangemaakt.
- [ ] Inhoud van de uitgepakte projectmap in de repository-root geüpload.
- [ ] `.github/workflows/update-leaderboard.yml` staat zichtbaar in de repository.
- [ ] Discord-webhook in het juiste leaderboard-kanaal aangemaakt.
- [ ] GitHub Secret `TOP_GAMES_TOKEN` toegevoegd.
- [ ] GitHub Secret `DISCORD_WEBHOOK_URL` toegevoegd.
- [ ] Optioneel Repository Variable `LEADERBOARD_PAGE_SIZE` ingesteld (5–40; standaard 20).
- [ ] GitHub Actions heeft **Read and write permissions**.
- [ ] Actions → Update Vote Leaderboards → Run workflow uitgevoerd.
- [ ] Current Month-board verschijnt in Discord.
- [ ] Previous Month-board verschijnt in Discord.
- [ ] `data/state.json` bevat na de run twee message-ID's.
- [ ] Automatische workflow staat ingeschakeld.

Klaar. Vanaf nu worden dezelfde twee Discord-berichten ieder uur bijgewerkt en bewaart GitHub automatisch de maandstanden.
