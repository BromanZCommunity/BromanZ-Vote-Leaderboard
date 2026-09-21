from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"
STATE_FILE = DATA_DIR / "state.json"

TOP_GAMES_API = "https://api.top-games.net/v1/servers/{token}/players-ranking"
TIMEZONE = ZoneInfo("Europe/Amsterdam")

EMBED_COLOR_CURRENT = 0xB91C1C
EMBED_COLOR_PREVIOUS = 0xD4AF37
MAX_DISCORD_EMBED_DESCRIPTION = 4096
USER_AGENT = "BromanZ-Vote-Leaderboard/1.0"


class LeaderboardError(RuntimeError):
    pass


class DiscordWebhookError(LeaderboardError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Player:
    name: str
    votes: int
    position: int

    def to_dict(self) -> dict[str, Any]:
        return {"playername": self.name, "votes": self.votes, "position": self.position}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Player":
        return cls(
            name=str(data.get("playername", "Unknown")),
            votes=int(data.get("votes", 0) or 0),
            position=int(data.get("position", 0) or 0),
        )


def env(name: str, required: bool = True, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise LeaderboardError(f"Missing required environment variable: {name}")
    return value or ""


def default_state() -> dict[str, Any]:
    return {
        "current_month": None,
        "current_snapshot": [],
        "current_message_ids": [],
        "previous_message_ids": [],
        "current_message_id": None,
        "previous_message_id": None,
        "last_updated": None,
    }


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return default_state()
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LeaderboardError(f"Could not read {STATE_FILE.name}: {exc}") from exc
    merged = default_state()
    merged.update(state)
    return merged


def save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(STATE_FILE)


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def previous_month_key(dt: datetime) -> str:
    first_day = dt.replace(day=1)
    return month_key(first_day - timedelta(days=1))


def month_title(key: str) -> str:
    year, month = key.split("-")
    names = {
        "01": "January", "02": "February", "03": "March", "04": "April",
        "05": "May", "06": "June", "07": "July", "08": "August",
        "09": "September", "10": "October", "11": "November", "12": "December",
    }
    return f"{names[month]} {year}"


def normalize_players(payload: Any) -> list[Player]:
    if isinstance(payload, list):
        raw_players = payload
    elif isinstance(payload, dict) and isinstance(payload.get("players"), list):
        raw_players = payload["players"]
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        raw_players = payload["data"]
    else:
        raise LeaderboardError(
            "Unexpected Top-Games API response. Expected a list, data.players, or data.data."
        )

    players: list[Player] = []
    for index, item in enumerate(raw_players):
        if not isinstance(item, dict):
            continue
        name = str(item.get("playername") or item.get("name") or f"Player {index + 1}").strip()
        name = re.sub(r"\s+", " ", name)[:100] or f"Player {index + 1}"
        try:
            votes = int(item.get("votes", 0) or 0)
        except (TypeError, ValueError):
            votes = 0
        try:
            position = int(item.get("position", index + 1) or index + 1)
        except (TypeError, ValueError):
            position = index + 1
        players.append(Player(name=name, votes=max(votes, 0), position=position))

    players.sort(key=lambda player: (-player.votes, player.name.casefold()))
    for index, player in enumerate(players, start=1):
        player.position = index
    return players


def fetch_top_games(token: str) -> list[Player]:
    try:
        response = requests.get(
            TOP_GAMES_API.format(token=token),
            timeout=30,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
    except requests.RequestException as exc:
        raise LeaderboardError("Could not connect to the Top-Games API.") from exc

    if response.status_code != 200:
        raise LeaderboardError(f"Top-Games API returned HTTP {response.status_code}.")
    try:
        return normalize_players(response.json())
    except ValueError as exc:
        raise LeaderboardError("Top-Games returned invalid JSON.") from exc


def validate_webhook_url(webhook_url: str) -> str:
    parts = urlsplit(webhook_url.strip())
    allowed_hosts = {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}
    if parts.scheme != "https" or parts.hostname not in allowed_hosts:
        raise LeaderboardError("DISCORD_WEBHOOK_URL is not a valid Discord webhook URL.")
    if not re.fullmatch(r"/api(?:/v\d+)?/webhooks/\d+/[^/]+/?", parts.path):
        raise LeaderboardError("DISCORD_WEBHOOK_URL does not contain a valid webhook ID and token.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), parts.query, ""))


def webhook_url_for(webhook_url: str, *, message_id: str | None = None, wait: bool = False) -> str:
    parts = urlsplit(webhook_url)
    path = parts.path if message_id is None else f"{parts.path}/messages/{message_id}"
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if wait:
        query["wait"] = "true"
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def webhook_request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any],
    expected: tuple[int, ...] = (200,),
) -> dict[str, Any]:
    try:
        response = requests.request(
            method,
            url,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise LeaderboardError("Could not connect to Discord.") from exc

    if response.status_code == 429:
        try:
            retry_after = float(response.json().get("retry_after", 1.0))
        except (TypeError, ValueError, AttributeError):
            retry_after = 1.0
        time.sleep(min(retry_after + 0.25, 10.0))
        try:
            response = requests.request(
                method,
                url,
                headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise LeaderboardError("Could not reconnect to Discord.") from exc

    if response.status_code not in expected:
        raise DiscordWebhookError(
            response.status_code,
            f"Discord webhook returned HTTP {response.status_code}.",
        )
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise LeaderboardError("Discord returned invalid JSON.") from exc


def message_payload(embed: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": "BromanZ Vote Leaderboard",
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
    }


def create_message(webhook_url: str, embed: dict[str, Any]) -> str:
    result = webhook_request(
        "POST",
        webhook_url_for(webhook_url, wait=True),
        payload=message_payload(embed),
        expected=(200,),
    )
    message_id = result.get("id")
    if not message_id:
        raise LeaderboardError("Discord created a message but returned no message ID.")
    return str(message_id)


def edit_message(webhook_url: str, message_id: str, embed: dict[str, Any]) -> None:
    webhook_request(
        "PATCH",
        webhook_url_for(webhook_url, message_id=message_id),
        payload=message_payload(embed),
        expected=(200,),
    )


def delete_message(webhook_url: str, message_id: str) -> None:
    webhook_request(
        "DELETE",
        webhook_url_for(webhook_url, message_id=message_id),
        payload={},
        expected=(204,),
    )


def medals(position: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, f"**{position}.**")


def safe_player_name(name: str) -> str:
    name = name.replace("@", "＠")
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>~])", r"\\\1", name)


def ranking_lines(players: list[Player], limit: int) -> list[str]:
    if not players:
        return ["No votes have been recorded yet."]
    lines: list[str] = []
    for player in players[:limit]:
        vote_word = "vote" if player.votes == 1 else "votes"
        lines.append(
            f"{medals(player.position)} **{safe_player_name(player.name)}** — "
            f"**{player.votes}** {vote_word}"
        )
    return lines


def fit_description(lines: list[str], footer_lines: list[str]) -> str:
    suffix = "\n\n" + "\n".join(footer_lines)
    chosen: list[str] = []
    for line in lines:
        candidate = "\n".join(chosen + [line]) + suffix
        if len(candidate) > MAX_DISCORD_EMBED_DESCRIPTION:
            break
        chosen.append(line)
    if not chosen:
        chosen = ["Leaderboard is too large to display."]
    return "\n".join(chosen) + suffix


def player_pages(players: list[Player], page_size: int) -> list[list[Player]]:
    if not players:
        return [[]]
    return [players[index:index + page_size] for index in range(0, len(players), page_size)]


def build_current_embeds(
    players: list[Player], current_month: str, updated: datetime, page_size: int
) -> list[dict[str, Any]]:
    total_votes = sum(player.votes for player in players)
    pages = player_pages(players, page_size)
    embeds: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages, start=1):
        footer_lines = [
            f"🗳️ **Total votes:** {total_votes}",
            f"👥 **All voters:** {len(players)}",
            "🔄 Updated automatically every hour",
            f"🕒 Last update: {updated.strftime('%d-%m-%Y %H:%M')} Europe/Amsterdam",
        ]
        embeds.append({
            "title": "🗳️ BromanZ Vote Leaderboard",
            "description": fit_description(ranking_lines(page, page_size), footer_lines),
            "color": EMBED_COLOR_CURRENT,
            "author": {
                "name": (
                    f"Current Month • {month_title(current_month)} • "
                    f"Page {page_number}/{len(pages)}"
                )
            },
            "footer": {"text": "BromanZ Community • Loot • Explore • Survive"},
            "timestamp": updated.isoformat(),
        })
    return embeds


def build_previous_embeds(
    players: list[Player] | None, previous_month: str, page_size: int
) -> list[dict[str, Any]]:
    if players is None:
        return [{
            "title": "🏆 BromanZ Previous Vote Leaderboard",
            "description": (
                f"No archived ranking is available for {month_title(previous_month)} yet.\n\n"
                "This board will be filled automatically after a month change."
            ),
            "color": EMBED_COLOR_PREVIOUS,
            "footer": {"text": "Final monthly standings are kept for in-game rewards."},
        }]

    total_votes = sum(player.votes for player in players)
    pages = player_pages(players, page_size)
    embeds: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages, start=1):
        footer_lines = [
            f"🗳️ **Final total votes:** {total_votes}",
            f"👥 **All voters:** {len(players)}",
            "🔒 **Final ranking — archived**",
            "🎮 Rewards are handled in-game by the BromanZ staff.",
        ]
        embeds.append({
            "title": "🏆 BromanZ Previous Vote Leaderboard",
            "description": fit_description(ranking_lines(page, page_size), footer_lines),
            "color": EMBED_COLOR_PREVIOUS,
            "author": {
                "name": (
                    f"Final Results • {month_title(previous_month)} • "
                    f"Page {page_number}/{len(pages)}"
                )
            },
            "footer": {"text": "BromanZ Community • Archived monthly ranking"},
        })
    return embeds


def archive_snapshot(month: str, snapshot: list[dict[str, Any]], archived_at: datetime) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{month}.json"
    payload = {
        "month": month,
        "title": month_title(month),
        "archived_at": archived_at.isoformat(),
        "players": snapshot,
        "total_votes": sum(int(player.get("votes", 0) or 0) for player in snapshot),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_archive(month: str) -> list[Player] | None:
    path = HISTORY_DIR / f"{month}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LeaderboardError(f"Could not read archive {path.name}: {exc}") from exc
    return [Player.from_dict(player) for player in data.get("players", []) if isinstance(player, dict)]


def sync_message_pages(
    state: dict[str, Any],
    state_key: str,
    legacy_state_key: str,
    webhook_url: str,
    embeds: list[dict[str, Any]],
) -> None:
    message_ids = [str(value) for value in state.get(state_key, []) if value]
    legacy_message_id = state.get(legacy_state_key)
    if not message_ids and legacy_message_id:
        message_ids = [str(legacy_message_id)]

    active_ids: list[str] = []
    for index, embed in enumerate(embeds):
        message_id = message_ids[index] if index < len(message_ids) else None
        if message_id:
            try:
                edit_message(webhook_url, message_id, embed)
                active_ids.append(message_id)
                continue
            except DiscordWebhookError as exc:
                if exc.status_code != 404:
                    raise
                print(f"Stored Discord message {message_id} no longer exists; creating a replacement.")
        active_ids.append(create_message(webhook_url, embed))

    for message_id in message_ids[len(embeds):]:
        try:
            delete_message(webhook_url, message_id)
        except DiscordWebhookError as exc:
            if exc.status_code != 404:
                raise

    state[state_key] = active_ids
    state[legacy_state_key] = active_ids[0] if active_ids else None
    save_state(state)
    print(f"Synchronized {len(active_ids)} Discord page(s) for {state_key}.")


def run() -> None:
    top_games_token = env("TOP_GAMES_TOKEN")
    discord_webhook_url = validate_webhook_url(env("DISCORD_WEBHOOK_URL"))
    try:
        leaderboard_page_size = int(env("LEADERBOARD_PAGE_SIZE", required=False, default="20"))
    except ValueError as exc:
        raise LeaderboardError("LEADERBOARD_PAGE_SIZE must be a number.") from exc
    leaderboard_page_size = max(5, min(leaderboard_page_size, 40))

    now = datetime.now(TIMEZONE)
    this_month = month_key(now)
    previous_month = previous_month_key(now)
    state = load_state()

    stored_month = state.get("current_month")
    stored_snapshot = state.get("current_snapshot") or []
    if stored_month and stored_month != this_month and stored_snapshot:
        archive_path = archive_snapshot(str(stored_month), stored_snapshot, now)
        print(f"Archived the last {stored_month} snapshot to {archive_path.relative_to(BASE_DIR)}")

    players = fetch_top_games(top_games_token)
    print(f"Fetched {len(players)} voters from Top-Games.")

    previous_players = load_archive(previous_month)
    current_embeds = build_current_embeds(players, this_month, now, leaderboard_page_size)
    previous_embeds = build_previous_embeds(previous_players, previous_month, leaderboard_page_size)

    sync_message_pages(
        state, "current_message_ids", "current_message_id", discord_webhook_url, current_embeds
    )
    sync_message_pages(
        state, "previous_message_ids", "previous_message_id", discord_webhook_url, previous_embeds
    )

    state["current_month"] = this_month
    state["current_snapshot"] = [player.to_dict() for player in players]
    state["last_updated"] = now.isoformat()
    save_state(state)
    print("Discord leaderboards updated successfully.")


if __name__ == "__main__":
    try:
        run()
    except LeaderboardError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
