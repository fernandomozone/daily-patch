#!/usr/bin/env python3
"""
Daily Patch — Validação fonética TTS via Whisper

Compara texto original vs transcrição Whisper do áudio gerado.
Usa WER (Word Error Rate) por segmento para detectar problemas de pronúncia.

Uso:
    cd <project-root>
    source .venv-chatterbox/bin/activate
    python scripts/validar_tts.py episodes/2026-03-09-ep7/guiao.json [--max-seg N]
"""

import json
import sys
import re
import unicodedata
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PRONUNCIA_CONFIG = PROJECT_DIR / "config" / "pronuncia.json"

WER_THRESHOLD = 0.15
MAX_TENTATIVAS = 3


def load_pronuncia():
    """Carrega dicionário fonético."""
    if not PRONUNCIA_CONFIG.exists():
        return {}
    with open(PRONUNCIA_CONFIG) as f:
        data = json.load(f)
    return data.get("replacements", {})


def pronuncia_inversa(pronuncia):
    """Cria mapa inverso: fonética → original, para normalizar comparação."""
    return {v.lower(): k.lower() for k, v in pronuncia.items()}


def normalizar_texto(text, pronuncia_inv=None):
    """Normaliza texto para comparação justa.

    - Lowercase
    - Remove pontuação
    - Reverte hints fonéticos para forma original (para comparar com Whisper)
    - Normaliza espaços
    """
    text = text.lower().strip()

    # Reverter hints fonéticos: "I.A." → "ia", "Kuber nétis" → "kubernetes"
    if pronuncia_inv:
        for fonetica, original in pronuncia_inv.items():
            text = text.replace(fonetica, original)

    # Remover acentos para comparação (Whisper pode ou não acentuar)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")

    # Remover pontuação
    text = re.sub(r'[^\w\s]', ' ', text)

    # Normalizar espaços
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/validar_tts.py <guiao.json> [--max-seg N]")
        sys.exit(1)

    guiao_path = Path(sys.argv[1])
    if not guiao_path.is_absolute():
        guiao_path = PROJECT_DIR / guiao_path

    # Parse --max-seg
    max_seg = None
    if "--max-seg" in sys.argv:
        idx = sys.argv.index("--max-seg")
        max_seg = int(sys.argv[idx + 1])

    episode_dir = guiao_path.parent
    segments_dir = episode_dir / "segments"

    with open(guiao_path) as f:
        guiao = json.load(f)

    pronuncia = load_pronuncia()
    pronuncia_inv = pronuncia_inversa(pronuncia)

    segments = guiao["segments"]
    if max_seg:
        segments = segments[:max_seg]

    # Filtrar só segmentos com texto (TTS)
    tts_segments = []
    for i, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if text:
            wav_path = segments_dir / f"seg_{i:03d}.wav"
            if wav_path.exists():
                tts_segments.append((i, seg, wav_path))

    if not tts_segments:
        print("Nenhum segmento TTS com áudio encontrado.")
        sys.exit(0)

    print(f"Segmentos TTS a validar: {len(tts_segments)}")
    print(f"Dicionário fonético: {len(pronuncia)} regras")
    print(f"WER threshold: {WER_THRESHOLD}")
    print("=" * 60)

    # Carregar Whisper
    # large-v3 não cabe na RTX 2070 (7.6GB) — usar medium
    print("Carregando Whisper medium...")
    import whisper
    whisper_model = whisper.load_model("medium", device="cuda")
    print("Whisper carregado!")
    print("=" * 60)

    from jiwer import wer, process_words

    resultados = []
    problemas = []

    for idx, (seg_num, seg, wav_path) in enumerate(tts_segments):
        speaker = seg["speaker"]
        texto_original = seg["text"].strip()

        # Transcrever com Whisper
        result = whisper_model.transcribe(
            str(wav_path),
            language="pt",
            task="transcribe",
        )
        transcricao = result["text"].strip()

        # Normalizar ambos para comparação
        texto_norm = normalizar_texto(texto_original, pronuncia_inv)
        trans_norm = normalizar_texto(transcricao)

        # Calcular WER
        seg_wer = wer(texto_norm, trans_norm)

        # Detalhes por palavra
        pw = process_words(texto_norm, trans_norm)

        status = "OK" if seg_wer <= WER_THRESHOLD else "FALHOU"

        print(f"\n[{seg_num:03d}] {speaker} — WER: {seg_wer:.2%} [{status}]")
        print(f"  Original:    {texto_original[:80]}")
        print(f"  Whisper:     {transcricao[:80]}")

        if seg_wer > WER_THRESHOLD:
            # Identificar palavras com erro
            palavras_erro = []
            for chunk in pw.alignments[0]:
                if chunk.type != "equal":
                    ref_words = texto_norm.split()[chunk.ref_start_idx:chunk.ref_end_idx]
                    hyp_words = trans_norm.split()[chunk.hyp_start_idx:chunk.hyp_end_idx]
                    palavras_erro.append({
                        "tipo": chunk.type,
                        "original": " ".join(ref_words),
                        "whisper": " ".join(hyp_words),
                    })

            print(f"  Erros:")
            for e in palavras_erro:
                print(f"    {e['tipo']}: \"{e['original']}\" → \"{e['whisper']}\"")

            problemas.append({
                "segmento": seg_num,
                "speaker": speaker,
                "wer": round(seg_wer, 4),
                "texto_original": texto_original,
                "transcricao": transcricao,
                "erros": palavras_erro,
            })

        resultados.append({
            "segmento": seg_num,
            "speaker": speaker,
            "wer": round(seg_wer, 4),
            "status": status,
        })

    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)

    total = len(resultados)
    ok = sum(1 for r in resultados if r["status"] == "OK")
    falhou = total - ok
    avg_wer = sum(r["wer"] for r in resultados) / total if total else 0

    print(f"Total: {total} segmentos")
    print(f"OK: {ok} ({ok/total:.0%})")
    print(f"Falharam: {falhou} ({falhou/total:.0%})")
    print(f"WER médio: {avg_wer:.2%}")

    if problemas:
        print(f"\nSegmentos com problemas:")
        for p in problemas:
            print(f"  [{p['segmento']:03d}] {p['speaker']} — WER {p['wer']:.2%}")
            for e in p["erros"]:
                print(f"    {e['tipo']}: \"{e['original']}\" → \"{e['whisper']}\"")

    # Salvar log
    log_path = episode_dir / "validacao_tts.json"
    with open(log_path, "w") as f:
        json.dump({
            "wer_threshold": WER_THRESHOLD,
            "total_segmentos": total,
            "ok": ok,
            "falharam": falhou,
            "wer_medio": round(avg_wer, 4),
            "resultados": resultados,
            "problemas": problemas,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nLog salvo em: {log_path}")


if __name__ == "__main__":
    main()
