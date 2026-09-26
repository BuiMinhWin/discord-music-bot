# 🎵 Discord Music Bot


## ✨ Tinh nang

| Lenh | Mo ta |
|------|-------|
| `/play <query>` | Phat nhac tu URL hoac tim kiem YouTube |
| `/search <query>` | Tim kiem va chon bai tu ket qua |
| `/playlist <url>` | Them ca playlist YouTube |
| `/pause` / `/resume` | Tam dung / Tiep tuc |
| `/skip` | Bo qua bai hien tai |
| `/stop` | Dung phat va roi voice channel |
| `/queue` | Xem danh sach cho |
| `/nowplaying` | Thong tin bai dang phat |
| `/volume <0-100>` | Chinh am luong |
| `/loop` | Lap lai (Off / Single / Queue) |
| `/shuffle` | Xao tron queue |
| `/remove <pos>` | Xoa bai khoi queue |
| `/move <from> <to>` | Di chuyen bai trong queue |
| `/clear` | Xoa toan bo queue |
| `/lyrics [query]` | Tim loi bai hat |
| `/help` | Hien thi tat ca lenh |
| `/ping` | Kiem tra do tre |

## 📋 Yeu cau

- **Python 3.10+**
- **FFmpeg** (phai co trong PATH)
- **Discord Bot Token**

## 🚀 Huong dan cai dat

### Buoc 1: Cai FFmpeg

#### Windows (dung Chocolatey):
```bash
choco install ffmpeg
```

#### Hoac download thu cong:
1. Truy cap https://www.gyan.dev/ffmpeg/builds/
2. Tai ban "ffmpeg-release-essentials.zip"
3. Giai nen va them thu muc `bin` vao PATH

Kiem tra FFmpeg da cai:
```bash
ffmpeg -version
```

### Buoc 2: Tao Discord Bot

1. Truy cap [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** -> dat ten bot
3. Vao tab **Bot**:
   - Click **Reset Token** -> copy token
   - Bat **MESSAGE CONTENT INTENT**
   - Bat **SERVER MEMBERS INTENT** (optional)
4. Vao tab **OAuth2 > URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Connect`, `Speak`, `Use Voice Activity`
5. Copy URL va mo trong browser de invite bot vao server

### Buoc 3: Setup project

```bash
# Clone hoac vao thu muc project
cd discord-music-bot

# Tao virtual environment
python -m venv venv

# Kich hoat venv
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Cai dependencies
pip install -r requirements.txt
```

### Buoc 4: Cau hinh

```bash
# Copy file .env mau
copy .env.example .env

# Mo file .env va dien bot token
# DISCORD_TOKEN=your_actual_token_here
```

### Buoc 5: Chay bot

```bash
python bot.py
```

Khi thay dong `Discord Music Bot is online!` la bot da san sang!

## 📁 Cau truc project

```
discord-music-bot/
├── bot.py              # Entry point chinh
├── config.py           # Cau hinh bot
├── requirements.txt    # Dependencies
├── .env.example        # Template bien moi truong
├── .env                # Bien moi truong (KHONG COMMIT!)
├── .gitignore
├── cogs/
│   ├── __init__.py
│   └── music.py        # Tat ca music commands
└── utils/
    ├── __init__.py
    ├── music_queue.py   # He thong queue
    └── lyrics.py        # Tim loi bai hat
```

## 🔧 Xu ly loi thuong gap

### Bot khong phat nhac
- Kiem tra FFmpeg da cai va co trong PATH
- Chay `ffmpeg -version` de kiem tra

### Bot khong vao voice channel
- Kiem tra bot co quyen `Connect` va `Speak`
- Kiem tra ban dang o trong voice channel

### Slash commands khong hien
- Doi 1-2 phut sau khi invite bot (Discord can thoi gian dong bo)
- Thu kick va invite lai bot

### Loi "Opus not loaded"
- Windows: Thuong tu load, neu khong thi download opus.dll
- Linux: `sudo apt install libopus0`

## 📝 License

MIT License - tu do su dung va chinh sua.
