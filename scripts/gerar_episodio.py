#!/usr/bin/env python3
"""
Daily Patch — Gerador de episódio via Chatterbox TTS (local)

Uso:
    cd <project-root>
    source .venv-chatterbox/bin/activate
    python scripts/gerar_episodio.py episodes/YYYY-MM-DD-epN/guiao.json

Resume support: segmentos já gerados (WAV > 1KB) são reutilizados.
"""

import json
import os
import sys
import time
import subprocess
import shutil
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════

PROJECT_DIR = Path(__file__).resolve().parent.parent
VOZES_CONFIG = PROJECT_DIR / "config" / "vozes_chatterbox.json"
PRONUNCIA_CONFIG = PROJECT_DIR / "config" / "pronuncia.json"
SFX_DIR = PROJECT_DIR / "assets" / "sfx"
VOICE_REFS_DIR = PROJECT_DIR / "assets" / "voice_refs"

PACE_PAUSES = {
    "normal": 0.2,
    "fast": 0.05,
    "interrupt": 0.0,
}

SAMPLE_RATE = 44100  # para silêncio e output final
OUTPUT_FORMAT = "mp3"  # flac, mp3, wav
OUTPUT_BITRATE = "320k"
COMPACT_MAX_MB = 18  # gera versão compacta se MP3 > este tamanho
OUTPUT_CHANNELS = 2  # 1=mono, 2=estéreo


def load_model():
    """Carrega o modelo Chatterbox Multilingual na GPU."""
    print("═" * 60)
    print("Carregando modelo Chatterbox Multilingual...")
    print("═" * 60)
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    print(f"PyTorch {torch.__version__}")
    print(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    print("Modelo carregado!\n")
    return model


def generate_silence(seconds, output_path):
    """Gera ficheiro de silêncio com duração especificada."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
            "-t", str(seconds),
            "-c:a", "pcm_s16le",
            output_path,
        ],
        capture_output=True,
    )


def apply_speed(input_path, output_path, speed):
    """Aplica atempo para acelerar/desacelerar sem alterar pitch."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-af", f"atempo={speed}",
            output_path,
        ],
        capture_output=True,
    )


def apply_mumble(input_path, output_path):
    """Aplica filtro lowpass + volume reduzido para resmungo."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-af", "lowpass=f=400,volume=0.6",
            output_path,
        ],
        capture_output=True,
    )


def convert_to_wav(input_path, output_path):
    """Converte qualquer áudio para WAV mono 44100Hz (para concat)."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-c:a", "pcm_s16le",
            output_path,
        ],
        capture_output=True,
    )


def is_cached(path):
    """Verifica se o segmento já foi gerado (resume support)."""
    return os.path.exists(path) and os.path.getsize(path) > 1000


import re

def load_pronuncia():
    """Carrega dicionário fonético de config/pronuncia.json."""
    if not PRONUNCIA_CONFIG.exists():
        return {}
    with open(PRONUNCIA_CONFIG) as f:
        data = json.load(f)
    return data.get("replacements", {})


def apply_pronuncia(text, replacements):
    """Aplica substituições fonéticas respeitando fronteiras de palavra."""
    for sigla, fonetica in replacements.items():
        text = re.sub(r'\b' + re.escape(sigla) + r'\b', fonetica, text)
    return text


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/gerar_episodio.py <caminho_guiao.json>")
        sys.exit(1)

    guiao_path = Path(sys.argv[1])
    if not guiao_path.is_absolute():
        guiao_path = PROJECT_DIR / guiao_path

    episode_dir = guiao_path.parent
    segments_dir = episode_dir / "segments"
    segments_dir.mkdir(exist_ok=True)

    # ── Carregar guião e config de vozes ──
    with open(guiao_path) as f:
        guiao = json.load(f)

    with open(VOZES_CONFIG) as f:
        vozes = json.load(f)

    segments = guiao["segments"]
    language_id = vozes.get("language_id", "pt")
    characters = vozes["characters"]
    pronuncia = load_pronuncia()
    if pronuncia:
        print(f"Dicionário fonético: {len(pronuncia)} regras")

    print(f"Episódio: {guiao.get('title', '?')}")
    print(f"Data: {guiao.get('date', '?')}")
    print(f"Segmentos: {len(segments)}")

    # ── Estimativa de duração ──
    DUR_PER_CHAR = 0.049
    DUR_OVERHEAD = 1.46
    MIN_DURATION = 570  # 9:30

    tts_segs = [s for s in segments if s.get("text", "").strip()]
    total_chars = sum(len(s["text"].strip()) for s in tts_segs)
    est_tts = sum(
        (DUR_PER_CHAR * len(s["text"].strip()) + DUR_OVERHEAD)
        / characters.get(s["speaker"], {}).get("speed", 1.0)
        for s in tts_segs
    )
    est_pauses = sum(s.get("pause_before", 0) + s.get("pause_after", 0) for s in segments)
    pace_map = {"normal": 0.2, "fast": 0.05, "interrupt": 0.0}
    est_pace = sum(pace_map.get(s.get("pace", "normal"), 0.2) for s in segments if s.get("text", "").strip() or s.get("sfx"))
    est_total = est_tts + est_pauses + est_pace + 7  # +7s SFX

    est_min = int(est_total // 60)
    est_sec = int(est_total % 60)
    print(f"Chars TTS: {total_chars} | Duração estimada: {est_min}:{est_sec:02d}")

    if est_total < MIN_DURATION:
        deficit = MIN_DURATION - est_total
        chars_needed = int(deficit * 1.1 / DUR_PER_CHAR)  # 1.1 = avg speed factor
        print(f"⚠ AVISO: Estimativa ({est_min}:{est_sec:02d}) abaixo do mínimo 9:30!")
        print(f"  Faltam ~{int(deficit)}s → adicionar ~{chars_needed} caracteres ao guião")
        resp = input("  Continuar mesmo assim? (s/N): ").strip().lower()
        if resp != "s":
            print("Abortado.")
            sys.exit(0)

    print()

    # ── Carregar modelo ──
    model = load_model()
    import torchaudio as ta

    # ── Pré-carregar conditionals por personagem ──
    # Vamos gerar segmento a segmento, trocando conditionals quando o speaker muda
    current_speaker = None
    concat_files = []
    total_tts = sum(1 for s in segments if s.get("text", "").strip())
    tts_done = 0
    start_time = time.time()

    for i, seg in enumerate(segments):
        speaker = seg["speaker"]
        text = seg.get("text", "").strip()
        if text and pronuncia:
            text = apply_pronuncia(text, pronuncia)
        sfx = seg.get("sfx")
        pace = seg.get("pace", "normal")
        pause_before = seg.get("pause_before", 0)
        pause_after = seg.get("pause_after", 0)
        filt = seg.get("filter")
        pace_pause = PACE_PAUSES.get(pace, 0.4)

        tag = f"[{i:03d}/{len(segments)-1:03d}]"

        # ── a) pause_before ──
        if pause_before and pause_before > 0:
            pause_path = str(segments_dir / f"seg_{i:03d}_pause_before.wav")
            if not is_cached(pause_path):
                generate_silence(pause_before, pause_path)
            concat_files.append(pause_path)

        # ── b) SFX ──
        if sfx:
            sfx_src = SFX_DIR / f"{sfx}.mp3"
            sfx_wav = str(segments_dir / f"seg_{i:03d}_sfx.wav")
            if not is_cached(sfx_wav):
                if sfx_src.exists():
                    convert_to_wav(str(sfx_src), sfx_wav)
                    print(f"{tag} SFX: {sfx}")
                else:
                    print(f"{tag} ⚠ SFX não encontrado: {sfx_src}")
            else:
                print(f"{tag} SFX: {sfx} (cached)")
            if os.path.exists(sfx_wav):
                concat_files.append(sfx_wav)

        # ── c) TTS (texto) ──
        if text:
            tts_done += 1
            raw_path = str(segments_dir / f"seg_{i:03d}_raw.wav")
            final_path = str(segments_dir / f"seg_{i:03d}.wav")

            if is_cached(final_path):
                print(f"{tag} {speaker}: cached")
                concat_files.append(final_path)
            else:
                # Trocar conditionals se speaker mudou
                if speaker != current_speaker:
                    char_cfg = characters.get(speaker)
                    if char_cfg is None:
                        print(f"{tag} ⚠ Speaker '{speaker}' não encontrado em vozes_chatterbox.json, usando BYTE")
                        char_cfg = characters["BYTE"]

                    ref_path = str(PROJECT_DIR / char_cfg["ref"])
                    exagg = char_cfg.get("exaggeration", 0.5)
                    print(f"{tag} Carregando voz: {speaker} (ref: {os.path.basename(ref_path)})")
                    model.prepare_conditionals(ref_path, exaggeration=exagg)
                    current_speaker = speaker

                char_cfg = characters.get(speaker, characters["BYTE"])
                cfg_w = char_cfg.get("cfg_weight", 0.5)
                temp = char_cfg.get("temperature", 0.8)
                speed = char_cfg.get("speed", 1.0)

                # Gerar TTS
                t0 = time.time()
                wav = model.generate(
                    text=text,
                    language_id=language_id,
                    cfg_weight=cfg_w,
                    temperature=temp,
                )
                elapsed = time.time() - t0

                # Salvar raw
                ta.save(raw_path, wav, model.sr)

                # Aplicar speed se != 1.0
                if abs(speed - 1.0) > 0.01:
                    speed_path = str(segments_dir / f"seg_{i:03d}_speed.wav")
                    apply_speed(raw_path, speed_path, speed)
                    working = speed_path
                else:
                    working = raw_path

                # Aplicar mumble se filter == "mumble"
                if filt == "mumble":
                    mumble_path = str(segments_dir / f"seg_{i:03d}_mumble.wav")
                    apply_mumble(working, mumble_path)
                    working = mumble_path

                # Converter para formato uniforme e salvar como final
                convert_to_wav(working, final_path)

                # ETA
                avg = (time.time() - start_time) / tts_done
                remaining = (total_tts - tts_done) * avg
                eta_min = int(remaining // 60)
                eta_sec = int(remaining % 60)

                print(f"{tag} {speaker}: \"{text[:60]}...\" ({elapsed:.1f}s) ETA: {eta_min}m{eta_sec:02d}s")
                concat_files.append(final_path)

        # ── d) pause_after ──
        if pause_after and pause_after > 0:
            pause_path = str(segments_dir / f"seg_{i:03d}_pause_after.wav")
            if not is_cached(pause_path):
                generate_silence(pause_after, pause_path)
            concat_files.append(pause_path)

        # ── e) Pausa entre segmentos (pace) ──
        # Só adiciona se houve TTS ou SFX neste segmento (não duplicar com pausas explícitas)
        if (text or sfx) and pace_pause > 0 and i < len(segments) - 1:
            pace_path = str(segments_dir / f"seg_{i:03d}_pace.wav")
            if not is_cached(pace_path):
                generate_silence(pace_pause, pace_path)
            concat_files.append(pace_path)

    # ═══════════════════════════════════════════════════════════════
    # CONCATENAR (com trim silence + crossfade + room tone)
    # ═══════════════════════════════════════════════════════════════
    from pydub import AudioSegment
    from pydub.silence import detect_leading_silence

    print()
    print("═" * 60)
    print(f"Concatenando {len(concat_files)} ficheiros (com crossfade)...")
    print("═" * 60)

    CROSSFADE_MS = 50   # 50ms crossfade entre segmentos
    FADE_MS = 30        # 30ms fade-in/fade-out em cada segmento TTS
    SILENCE_THRESH = -55  # dBFS — só corta silêncio puro

    def trim_silence(seg, threshold=SILENCE_THRESH):
        """Remove silêncio puro no início e fim do segmento."""
        start_trim = detect_leading_silence(seg, silence_threshold=threshold, chunk_size=10)
        end_trim = detect_leading_silence(seg.reverse(), silence_threshold=threshold, chunk_size=10)
        if start_trim + end_trim >= len(seg):
            return seg
        return seg[start_trim:len(seg) - end_trim]

    result_audio = AudioSegment.empty()
    for idx, path in enumerate(concat_files):
        seg = AudioSegment.from_wav(path)
        basename = os.path.basename(path)
        is_pause = "_pause_" in basename or "_pace." in basename
        is_tts = not is_pause and "_sfx" not in basename

        # Trim + fade só em segmentos TTS
        if is_tts and len(seg) > FADE_MS * 2:
            seg = trim_silence(seg)
            seg = seg.fade_in(FADE_MS).fade_out(FADE_MS)

        if len(result_audio) == 0 or len(seg) == 0:
            result_audio += seg
        else:
            cf = min(CROSSFADE_MS, len(result_audio), len(seg))
            if cf > 0 and not is_pause:
                result_audio = result_audio.append(seg, crossfade=cf)
            else:
                result_audio += seg

        if (idx + 1) % 50 == 0:
            print(f"  {idx + 1}/{len(concat_files)} segmentos processados...")

    print(f"  {len(concat_files)}/{len(concat_files)} segmentos processados.")

    # Room tone removido — não melhora a qualidade

    # Exportar WAV intermediário
    intermediate_wav = str(segments_dir / "concat_full.wav")
    result_audio.export(intermediate_wav, format="wav")

    # Normalizar e converter para MP3 final
    output_file = str(episode_dir / "episode.mp3")
    print(f"Aplicando loudnorm e convertendo para MP3 {OUTPUT_BITRATE} estéreo...")

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", intermediate_wav,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", str(SAMPLE_RATE),
        "-ac", str(OUTPUT_CHANNELS),
        "-b:a", OUTPUT_BITRATE,
        output_file,
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERRO ffmpeg: {result.stderr[-500:]}")
        sys.exit(1)

    # ── Info final ──
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration,size",
         "-of", "json", output_file],
        capture_output=True, text=True,
    )
    info = json.loads(probe.stdout).get("format", {})
    duration = float(info.get("duration", 0))
    size_mb = int(info.get("size", 0)) / (1024 * 1024)

    # ── Versão compacta (<18MB) ──
    compact_file = str(episode_dir / "episode_compact.mp3")
    if size_mb > COMPACT_MAX_MB:
        target_bitrate = int((COMPACT_MAX_MB * 8 * 1024) / duration)
        compact_bitrate = f"{min(target_bitrate, 256)}k"
        print(f"Criando versão compacta ({compact_bitrate})...")
        compact_cmd = [
            "ffmpeg", "-y", "-i", output_file,
            "-b:a", compact_bitrate, "-ac", str(OUTPUT_CHANNELS),
            compact_file,
        ]
        subprocess.run(compact_cmd, capture_output=True, text=True)
        compact_size = os.path.getsize(compact_file) / (1024 * 1024)
    else:
        shutil.copy2(output_file, compact_file)
        compact_size = size_mb

    total_time = time.time() - start_time

    print()
    print("═" * 60)
    print(f"EPISÓDIO GERADO!")
    print(f"  MP3:      {output_file} ({size_mb:.1f} MB)")
    print(f"  Compact:  {compact_file} ({compact_size:.1f} MB)")
    print(f"  Duração:  {int(duration//60)}:{int(duration%60):02d}")
    print(f"  Tempo:    {int(total_time//60)}m{int(total_time%60):02d}s")
    print(f"  Segmentos TTS: {tts_done}")
    print("═" * 60)


if __name__ == "__main__":
    main()
