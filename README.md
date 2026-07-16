# savvy-media

Standalone image & video creation from your terminal. One file, **zero
dependencies** — pure Python 3 standard library. No API keys, no pip installs.

| Mode | Images | Videos |
|------|--------|--------|
| **Online** (default) | AI-generated from your text prompt (free Pollinations API) | AI keyframes cross-faded into an MP4 (needs `ffmpeg`) |
| **Offline** (`--offline`) | Procedural generative art seeded by your prompt | Looping animation — MP4 via `ffmpeg`, or a pure-Python GIF if you don't have `ffmpeg` at all |

## Install

Put the single script anywhere on your `PATH`:

```bash
git clone https://github.com/AllPro123/Savvy.git
cd Savvy
chmod +x savvy-media
sudo cp savvy-media /usr/local/bin/   # or: ln -s "$PWD/savvy-media" ~/.local/bin/
```

Or just run it in place: `./savvy-media ...` (or `python3 savvy-media ...`).

Requires Python 3.8+. `ffmpeg` is optional and only needed for MP4 output.

## Usage

### Images

```bash
# AI image from a prompt (saved as <prompt-slug>.jpg)
savvy-media image "a fox in a snowy forest, watercolor"

# custom size, output path, reproducible seed
savvy-media image "cyberpunk city at night" -W 1920 -H 1080 -o city.jpg --seed 42

# no internet? seeded generative art instead (PNG)
savvy-media image "abstract ocean waves" --offline
```

### Videos

```bash
# AI video: keyframes cross-faded into an MP4 (requires ffmpeg)
savvy-media video "drifting nebula clouds" --duration 8 --keyframes 6

# offline looping animation; auto-falls back to GIF without ffmpeg
savvy-media video "lava lamp" --offline

# force a GIF explicitly
savvy-media video "aurora borealis" --offline -o aurora.gif --fps 12
```

### Options

```
image/video  prompt          what to create (required)
             -o, --output    output file (default: derived from the prompt)
             -W, --width     pixels (image default 1024, video default 960)
             -H, --height    pixels (image default 1024, video default 540)
             --seed N        reproducible results
             --model NAME    AI model in online mode: flux (default) or turbo
             --offline       no-internet procedural mode

video only   --duration S    length in seconds (default 6)
             --fps N         frames per second (default 12)
             --keyframes N   AI keyframes to crossfade (default 5)
             --fade S        crossfade length in seconds (default 1)
```

## How it works

- **Online images** hit the free, key-less Pollinations image API with
  retries and exponential backoff.
- **Online videos** generate several AI keyframes (same prompt, sequential
  seeds) and stitch them with ffmpeg `xfade` cross-fades.
- **Offline mode** renders a multi-oscillator plasma field whose frequencies,
  motion, and 256-color palette are all derived deterministically from a
  SHA-256 hash of your prompt (and `--seed`), so the same prompt always
  recreates the same art. Animations are phase-periodic, so GIFs loop
  seamlessly.
- The PNG writer, animated-GIF writer, and GIF LZW compressor are all
  implemented in the script itself with only the standard library.
