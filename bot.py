import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import asyncio
import datetime
import yt_dlp

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")

# ── Bot Branding ──
BOT_NAME = "Too Music"
BOT_ICON = "https://cdn.discordapp.com/emojis/1060308601587798087.webp"
EMBED_COLOR_PRIMARY = 0x7C3AED     # Vibrant purple
EMBED_COLOR_SUCCESS = 0x10B981     # Emerald green
EMBED_COLOR_WARNING = 0xF59E0B     # Amber
EMBED_COLOR_ERROR = 0xEF4444       # Red
EMBED_COLOR_INFO = 0x3B82F6        # Blue
EMBED_COLOR_QUEUE = 0x8B5CF6       # Purple
EMBED_COLOR_LOOP = 0xEC4899        # Pink

# yt-dlp options for extracting audio
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

# ffmpeg options for streaming audio
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Setup intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ---------- Music Queue Manager ----------

class MusicQueue:
    """Per-guild music queue manager."""

    def __init__(self):
        self.queue: list[dict] = []
        self.current: dict | None = None
        self.loop: bool = False
        self.loop_queue: bool = False

    def add(self, song: dict):
        self.queue.append(song)

    def next(self) -> dict | None:
        if self.loop and self.current:
            return self.current
        if self.loop_queue and self.current:
            self.queue.append(self.current)
        if self.queue:
            self.current = self.queue.pop(0)
            return self.current
        self.current = None
        return None

    def clear(self):
        self.queue.clear()
        self.current = None
        self.loop = False
        self.loop_queue = False


# Per-guild queues
queues: dict[int, MusicQueue] = {}


def get_queue(guild_id: int) -> MusicQueue:
    if guild_id not in queues:
        queues[guild_id] = MusicQueue()
    return queues[guild_id]


# ---------- Helper Functions ----------

def make_embed(
    title: str = "",
    description: str = "",
    color: int = EMBED_COLOR_PRIMARY,
    thumbnail: str = "",
    image: str = "",
    footer_extra: str = "",
) -> discord.Embed:
    """Create a branded embed with consistent styling."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    footer_text = f"{BOT_NAME} Premium"
    if footer_extra:
        footer_text = f"{footer_extra}  •  {footer_text}"
    embed.set_footer(text=footer_text, icon_url=BOT_ICON)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    return embed


def make_progress_bar(current: int = 0, total: int = 10, length: int = 12) -> str:
    """Create a visual progress bar."""
    if total <= 0:
        return "🔴 LIVE"
    filled = int(length * (current / total)) if current > 0 else 0
    bar = "▬" * filled + "🔘" + "▬" * (length - filled - 1)
    return bar


def search_song(query: str) -> dict | None:
    """Search YouTube and return song info dict."""
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            if query.startswith(("http://", "https://")):
                info = ydl.extract_info(query, download=False)
            else:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if "entries" in info and info["entries"]:
                    info = info["entries"][0]
                else:
                    return None

            return {
                "title": info.get("title", "Unknown"),
                "url": info.get("url"),
                "webpage_url": info.get("webpage_url", query),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "channel": info.get("uploader", info.get("channel", "Unknown")),
                "view_count": info.get("view_count", 0),
            }
        except Exception:
            return None


def format_duration(seconds: int) -> str:
    """Format seconds to MM:SS or HH:MM:SS."""
    if seconds <= 0:
        return "🔴 LIVE"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_views(count: int) -> str:
    """Format view count to readable string."""
    if count <= 0:
        return "N/A"
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def play_next(guild: discord.Guild):
    """Play the next song in the queue (callback for after playback)."""
    music_queue = get_queue(guild.id)
    voice_client = guild.voice_client

    if not voice_client or not voice_client.is_connected():
        music_queue.clear()
        return

    song = music_queue.next()
    if song is None:
        return

    source = discord.FFmpegPCMAudio(song["url"], executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
    source = discord.PCMVolumeTransformer(source, volume=0.5)

    def after_playing(error):
        if error:
            print(f"Player error: {error}")
        play_next(guild)

    voice_client.play(source, after=after_playing)


# ---------- Bot Events ----------

@bot.event
async def on_ready():
    """Sync slash commands to all guilds when bot is ready."""
    try:
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} command(s) to: {guild.name}", flush=True)
        print(f"Bot online: {bot.user} (ID: {bot.user.id})", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Gagal sync commands: {e}", flush=True)


# ---------- Slash Commands ----------

@bot.tree.command(name="tjoin", description="Bot join ke voice channel kamu")
async def tjoin(interaction: discord.Interaction):
    """Join the user's current voice channel."""
    if not interaction.user.voice:
        embed = make_embed(
            description="**Masuk ke Voice Channel dulu!**\nKamu harus berada di VC sebelum menggunakan command ini.",
            color=EMBED_COLOR_ERROR,
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    channel = interaction.user.voice.channel

    if interaction.guild.voice_client:
        if interaction.guild.voice_client.channel == channel:
            embed = make_embed(
                description=f"**Sudah berada di {channel.name}!**\nBot sudah terhubung ke channel ini.",
                color=EMBED_COLOR_WARNING,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.guild.voice_client.move_to(channel)
        embed = make_embed(
            title="🔄 Pindah Channel",
            description=f"Berpindah ke **{channel.name}**",
            color=EMBED_COLOR_INFO,
            footer_extra=f"Channel: {channel.name}",
        )
        return await interaction.response.send_message(embed=embed)

    try:
        await channel.connect()
        embed = make_embed(
            title="🔊 Connected",
            description=(
                f"Berhasil terhubung ke **{channel.name}**!\n\n"
                f"Gunakan `/tplay` untuk mulai memutar musik."
            ),
            color=EMBED_COLOR_SUCCESS,
            footer_extra=f"Channel: {channel.name}",
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = make_embed(
            description=f"**Gagal terhubung!**\n```{e}```",
            color=EMBED_COLOR_ERROR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="tplay", description="Play lagu dari YouTube (URL atau search)")
@app_commands.describe(query="URL YouTube atau kata kunci pencarian")
async def tplay(interaction: discord.Interaction, query: str):
    """Play a song from YouTube by URL or search query."""
    if not interaction.user.voice:
        embed = make_embed(
            description="**Masuk ke Voice Channel dulu!**\nKamu harus berada di VC sebelum memutar musik.",
            color=EMBED_COLOR_ERROR,
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    # Defer FIRST — Discord only gives 3 seconds to respond
    await interaction.response.defer()

    channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    # Auto-join if not connected
    if not voice_client or not voice_client.is_connected():
        try:
            voice_client = await channel.connect()
        except Exception as e:
            embed = make_embed(
                description=f"**Gagal join VC!**\n```{e}```",
                color=EMBED_COLOR_ERROR,
            )
            return await interaction.followup.send(embed=embed)
    elif voice_client.channel != channel:
        await voice_client.move_to(channel)

    # Search for the song in a thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    song = await loop.run_in_executor(None, search_song, query)

    if not song:
        embed = make_embed(
            title="🔍 Tidak Ditemukan",
            description=f"Tidak dapat menemukan lagu untuk:\n> *{query}*\n\nCoba gunakan kata kunci yang berbeda!",
            color=EMBED_COLOR_ERROR,
        )
        return await interaction.followup.send(embed=embed)

    music_queue = get_queue(interaction.guild.id)
    music_queue.add(song)

    duration = format_duration(song["duration"])
    views = format_views(song.get("view_count", 0))

    # If nothing is playing, start playback
    if not voice_client.is_playing() and not voice_client.is_paused():
        next_song = music_queue.next()
        if next_song:
            source = discord.FFmpegPCMAudio(
                next_song["url"], executable=FFMPEG_PATH, **FFMPEG_OPTIONS
            )
            source = discord.PCMVolumeTransformer(source, volume=0.5)

            def after_playing(error):
                if error:
                    print(f"Player error: {error}")
                play_next(interaction.guild)

            voice_client.play(source, after=after_playing)

            # Build rich "Now Playing" embed
            progress = make_progress_bar(0, next_song["duration"])
            loop_status = ""
            if music_queue.loop:
                loop_status = "  •  🔂 Loop Lagu"
            elif music_queue.loop_queue:
                loop_status = "  •  🔁 Loop Antrian"

            embed = make_embed(
                title="🎵  Now Playing",
                description=(
                    f"**[{next_song['title']}]({next_song['webpage_url']})**\n\n"
                    f"{progress}\n"
                    f"`0:00` / `{duration}`{loop_status}"
                ),
                color=EMBED_COLOR_SUCCESS,
                footer_extra=f"Requested by {interaction.user.display_name}",
            )
            embed.add_field(name="🎤 Artist", value=next_song.get("channel", "Unknown"), inline=True)
            embed.add_field(name="⏱️ Durasi", value=f"`{duration}`", inline=True)
            embed.add_field(name="👁️ Views", value=f"`{views}`", inline=True)

            if next_song["thumbnail"]:
                embed.set_image(url=next_song["thumbnail"])

            if music_queue.queue:
                embed.add_field(
                    name="📋 Up Next",
                    value=f"**{music_queue.queue[0]['title']}** dan {len(music_queue.queue)} lainnya" if len(music_queue.queue) > 1
                    else f"**{music_queue.queue[0]['title']}**",
                    inline=False,
                )

            await interaction.followup.send(embed=embed)
    else:
        # Add to queue — show queued embed
        position = len(music_queue.queue)

        embed = make_embed(
            title="📋  Added to Queue",
            description=(
                f"**[{song['title']}]({song['webpage_url']})**\n\n"
                f"```yml\n"
                f"Position  : #{position}\n"
                f"Duration  : {duration}\n"
                f"Artist    : {song.get('channel', 'Unknown')}\n"
                f"Views     : {views}\n"
                f"```"
            ),
            color=EMBED_COLOR_INFO,
            footer_extra=f"Requested by {interaction.user.display_name}",
        )
        if song["thumbnail"]:
            embed.set_thumbnail(url=song["thumbnail"])

        await interaction.followup.send(embed=embed)


@bot.tree.command(name="tskip", description="Skip lagu yang sedang diputar")
async def tskip(interaction: discord.Interaction):
    """Skip the currently playing song."""
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_playing():
        embed = make_embed(
            description="**Tidak ada lagu yang sedang diputar!**\nGunakan `/tplay` untuk memutar lagu.",
            color=EMBED_COLOR_ERROR,
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    music_queue = get_queue(interaction.guild.id)
    was_looping = music_queue.loop
    music_queue.loop = False

    current = music_queue.current
    title = current["title"] if current else "Unknown"
    thumbnail = current.get("thumbnail", "") if current else ""

    voice_client.stop()  # This triggers the after callback -> play_next

    if was_looping:
        music_queue.loop = False

    # Build skip embed
    next_song = music_queue.queue[0] if music_queue.queue else None

    embed = make_embed(
        title="⏭️  Skipped",
        description=f"**{title}**",
        color=EMBED_COLOR_WARNING,
        footer_extra=f"Skipped by {interaction.user.display_name}",
    )
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    if next_song:
        next_dur = format_duration(next_song["duration"])
        embed.add_field(
            name="⏭️ Up Next",
            value=f"**{next_song['title']}** `[{next_dur}]`",
            inline=False,
        )
    else:
        embed.add_field(
            name="📋 Queue",
            value="*Antrian kosong — tambah lagu dengan `/tplay`*",
            inline=False,
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tstop", description="Stop musik dan hapus antrian")
async def tstop(interaction: discord.Interaction):
    """Stop playing music and clear the queue."""
    voice_client = interaction.guild.voice_client

    if not voice_client:
        embed = make_embed(
            description="**Bot tidak sedang di Voice Channel!**",
            color=EMBED_COLOR_ERROR,
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    music_queue = get_queue(interaction.guild.id)
    cleared_count = len(music_queue.queue) + (1 if music_queue.current else 0)
    music_queue.clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    embed = make_embed(
        title="⏹️  Stopped",
        description=(
            "Musik dihentikan dan antrian dihapus.\n\n"
            f"```yml\n"
            f"Lagu dihapus  : {cleared_count}\n"
            f"Status        : Stopped\n"
            f"```\n"
            f"Gunakan `/tplay` untuk memutar lagu baru!"
        ),
        color=EMBED_COLOR_ERROR,
        footer_extra=f"Stopped by {interaction.user.display_name}",
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tloop", description="Toggle loop lagu / antrian / off")
@app_commands.describe(mode="Pilih mode loop")
@app_commands.choices(mode=[
    app_commands.Choice(name="🔂 Lagu (loop lagu saat ini)", value="song"),
    app_commands.Choice(name="🔁 Antrian (loop semua antrian)", value="queue"),
    app_commands.Choice(name="❌ Off (matikan loop)", value="off"),
])
async def tloop(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    """Toggle loop mode."""
    music_queue = get_queue(interaction.guild.id)
    current_title = music_queue.current["title"] if music_queue.current else None

    if mode.value == "song":
        music_queue.loop = True
        music_queue.loop_queue = False
        embed = make_embed(
            title="🔂  Loop Lagu",
            description=(
                f"Loop lagu **diaktifkan**!\n\n"
                f"{'> 🎵 **' + current_title + '** akan diputar berulang.' if current_title else '> Lagu berikutnya akan diputar berulang.'}"
            ),
            color=EMBED_COLOR_LOOP,
        )
    elif mode.value == "queue":
        music_queue.loop = False
        music_queue.loop_queue = True
        queue_len = len(music_queue.queue) + (1 if music_queue.current else 0)
        embed = make_embed(
            title="🔁  Loop Antrian",
            description=(
                f"Loop antrian **diaktifkan**!\n\n"
                f"> 📋 **{queue_len} lagu** akan diputar berulang."
            ),
            color=EMBED_COLOR_LOOP,
        )
    else:
        music_queue.loop = False
        music_queue.loop_queue = False
        embed = make_embed(
            title="▶️  Loop Off",
            description="Loop **dimatikan**!\n\n> Musik akan berhenti setelah antrian habis.",
            color=EMBED_COLOR_WARNING,
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tqueue", description="Lihat antrian lagu saat ini")
async def tqueue(interaction: discord.Interaction):
    """Show the current music queue."""
    music_queue = get_queue(interaction.guild.id)

    if not music_queue.current and not music_queue.queue:
        embed = make_embed(
            title="📋  Queue",
            description=(
                "Antrian kosong!\n\n"
                "> Gunakan `/tplay <judul lagu>` untuk menambah lagu."
            ),
            color=EMBED_COLOR_QUEUE,
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    # Calculate total duration
    total_seconds = sum(s.get("duration", 0) for s in music_queue.queue)
    if music_queue.current:
        total_seconds += music_queue.current.get("duration", 0)
    total_duration = format_duration(total_seconds)

    # Loop status
    loop_text = "Off"
    if music_queue.loop:
        loop_text = "🔂 Lagu"
    elif music_queue.loop_queue:
        loop_text = "🔁 Antrian"

    embed = make_embed(
        title="📋  Music Queue",
        color=EMBED_COLOR_QUEUE,
        footer_extra=f"{len(music_queue.queue) + (1 if music_queue.current else 0)} lagu  •  {total_duration} total",
    )

    # Currently playing
    if music_queue.current:
        current = music_queue.current
        dur = format_duration(current["duration"])
        progress = make_progress_bar(0, current["duration"])

        embed.description = (
            f"**__Sedang Diputar:__**\n"
            f"🎵 **[{current['title']}]({current['webpage_url']})**\n"
            f"└ 🎤 {current.get('channel', 'Unknown')}  •  `{dur}`\n"
            f"{progress}\n\n"
        )
        if current.get("thumbnail"):
            embed.set_thumbnail(url=current["thumbnail"])

    # Queue list
    if music_queue.queue:
        queue_lines = []
        for i, song in enumerate(music_queue.queue[:10], 1):
            dur = format_duration(song["duration"])
            queue_lines.append(
                f"`{i:02d}.` **[{song['title']}]({song['webpage_url']})**\n"
                f"     └ 🎤 {song.get('channel', 'Unknown')}  •  `{dur}`"
            )

        queue_text = "\n".join(queue_lines)
        if len(music_queue.queue) > 10:
            remaining = len(music_queue.queue) - 10
            queue_text += f"\n\n*... dan **{remaining}** lagu lainnya*"

        embed.add_field(name="__Up Next:__", value=queue_text, inline=False)

    # Info bar
    embed.add_field(
        name="\u200b",
        value=f"```yml\nLoop: {loop_text}  |  Antrian: {len(music_queue.queue)} lagu  |  Total: {total_duration}```",
        inline=False,
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tleave", description="Bot keluar dari voice channel")
async def tleave(interaction: discord.Interaction):
    """Leave the current voice channel and clear queue."""
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        embed = make_embed(
            description="**Bot tidak sedang di Voice Channel!**",
            color=EMBED_COLOR_ERROR,
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    music_queue = get_queue(interaction.guild.id)
    cleared_count = len(music_queue.queue) + (1 if music_queue.current else 0)
    music_queue.clear()

    channel_name = voice_client.channel.name
    await voice_client.disconnect()

    embed = make_embed(
        title="👋  Disconnected",
        description=(
            f"Keluar dari **{channel_name}**\n\n"
            f"```yml\n"
            f"Antrian dihapus : {cleared_count} lagu\n"
            f"Status          : Disconnected\n"
            f"```\n"
            f"Sampai jumpa! Gunakan `/tjoin` untuk konek lagi."
        ),
        color=EMBED_COLOR_WARNING,
        footer_extra=f"Disconnected by {interaction.user.display_name}",
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tnowplaying", description="Info lagu yang sedang diputar")
async def tnowplaying(interaction: discord.Interaction):
    """Show detailed info about the currently playing song."""
    music_queue = get_queue(interaction.guild.id)
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_playing() or not music_queue.current:
        embed = make_embed(
            description="**Tidak ada lagu yang sedang diputar!**\nGunakan `/tplay` untuk memutar lagu.",
            color=EMBED_COLOR_ERROR,
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    song = music_queue.current
    duration = format_duration(song["duration"])
    views = format_views(song.get("view_count", 0))
    progress = make_progress_bar(0, song["duration"])

    loop_status = "Off"
    if music_queue.loop:
        loop_status = "🔂 Lagu"
    elif music_queue.loop_queue:
        loop_status = "🔁 Antrian"

    embed = make_embed(
        title="🎵  Now Playing",
        description=(
            f"**[{song['title']}]({song['webpage_url']})**\n\n"
            f"{progress}\n"
            f"`0:00` / `{duration}`"
        ),
        color=EMBED_COLOR_PRIMARY,
    )
    embed.add_field(name="🎤 Artist", value=song.get("channel", "Unknown"), inline=True)
    embed.add_field(name="⏱️ Durasi", value=f"`{duration}`", inline=True)
    embed.add_field(name="👁️ Views", value=f"`{views}`", inline=True)
    embed.add_field(name="🔁 Loop", value=loop_status, inline=True)
    embed.add_field(name="📋 Queue", value=f"`{len(music_queue.queue)} lagu`", inline=True)
    embed.add_field(name="🔊 Volume", value="`50%`", inline=True)

    if song["thumbnail"]:
        embed.set_image(url=song["thumbnail"])

    await interaction.response.send_message(embed=embed)


# ---------- Run Bot ----------

if not TOKEN:
    print("ERROR: DISCORD_TOKEN tidak ditemukan di file .env!")
    print("Pastikan file .env berisi: DISCORD_TOKEN=token_kamu")
    exit(1)

bot.run(TOKEN)
