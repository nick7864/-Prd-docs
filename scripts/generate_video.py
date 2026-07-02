#!/usr/bin/env python3
"""Generate a demo video for YouTube submission using PIL slides + macOS TTS + ffmpeg.

Creates a ~4:30 video with 6 segments covering:
1. Problem Statement
2. Architecture Overview
3. Policy Gate Demo (prd-003 reject)
4. Completeness + Clarity Demo (prd-001 pass, prd-002 needs_clarification)
5. Risk Demo (prd-005 findings)
6. Key Concepts + Build

Output: assets/demo_video.mp4 (1920x1080, H.264, AAC)
"""
from __future__ import annotations

import imageio_ffmpeg
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1920, 1080
BG = "#0f0f23"
ACCENT = "#e94560"
WHITE = "#ffffff"
GRAY = "#a0a0b8"
TMP = Path(tempfile.mkdtemp(prefix="video_"))


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for p in ["/System/Library/Fonts/Helvetica.ttc"]:
        try:
            return ImageFont.truetype(p, size, index=1 if bold else 0)
        except Exception:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def text_centered(draw, text, y, f, fill=WHITE):
    tw = draw.textlength(text, font=f)
    draw.text(((W - tw) / 2, y), text, fill=fill, font=f)


def make_slide(title: str, bullets: list[str], subtitle: str = "") -> Path:
    """Create a professional slide image."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    draw.rectangle([0, H - 6, W, H], fill=ACCENT)

    text_centered(draw, title, 100, font(64, bold=True), WHITE)
    if subtitle:
        text_centered(draw, subtitle, 185, font(32), GRAY)

    f_body = font(34)
    f_bold = font(34, bold=True)
    y = 300
    for bullet in bullets:
        draw.text((250, y), "\u2022", fill=ACCENT, font=f_bold)
        draw.text((300, y), bullet, fill=WHITE, font=f_body)
        y += 65

    path = TMP / f"slide_{title[:10].replace(' ', '_')}.png"
    img.save(path, "PNG")
    return path


def make_segment(slide_path: Path, narration: str, voice: str = "Samantha") -> Path:
    """Create a video segment from a slide image + TTS narration."""
    segment_num = len(list(TMP.glob("segment_*.mp4"))) + 1
    audio = TMP / f"audio_{segment_num}.aiff"
    segment = TMP / f"segment_{segment_num}.mp4"

    # Generate TTS audio
    subprocess.run(["say", "-v", voice, "-o", str(audio), narration], check=True, capture_output=True)

    # Get audio duration
    result = subprocess.run(
        [FFMPEG, "-i", str(audio)], capture_output=True, text=True
    )
    duration = 5.0
    for line in result.stderr.split("\n"):
        if "Duration" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

    # Create video: loop image for duration of audio
    subprocess.run(
        [
            FFMPEG, "-y",
            "-loop", "1", "-i", str(slide_path),
            "-i", str(audio),
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-t", str(duration + 0.5),
            "-shortest",
            str(segment),
        ],
        capture_output=True, check=True,
    )
    return segment


def concat_segments(segments: list[Path], output: Path) -> None:
    """Concatenate video segments into final video."""
    list_file = TMP / "concat_list.txt"
    list_file.write_text(
        "\n".join(f"file '{s.absolute()}'" for s in segments)
    )
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output),
        ],
        capture_output=True, check=True,
    )


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------

# NOTE: The API key in the Policy Gate segment (AIzaSyDabc123...) is a FAKE test
# fixture shown for educational purposes. NOT a real credential.
SEGMENTS = [
    {
        "title": "PRD Triage Agent",
        "subtitle": "Multi-agent PRD intake checkup for software teams",
        "bullets": [
            "PRDs arrive missing acceptance criteria, vague terms, risks",
            "Engineers discover problems during implementation — too late",
            "Static linters can't judge if a PRD is executable",
            "Solution: 4 AI agents analyze the PRD in parallel, before engineering begins",
        ],
        "narration": (
            "When a product manager hands a PRD to engineering, the team often discovers "
            "problems only during implementation: missing acceptance criteria, vague requirements, "
            "architecture conflicts, and compliance risks. By then, it's too late. "
            "Static linters catch formatting issues, but they can't judge whether a PRD is "
            "actually executable. That requires understanding context, comparing against "
            "history, and evaluating trade-offs — exactly what AI agents excel at. "
            "I built PRD Triage Agent: a multi-agent system that catches these issues "
            "before engineering begins."
        ),
    },
    {
        "title": "Architecture",
        "subtitle": "ADK 2.0 Parallel Pipeline",
        "bullets": [
            "Document MCP Server reads the PRD via 4 standard tools",
            "Policy Gate rejects PRDs with API keys, emails, or secrets",
            "4 specialist agents run in PARALLEL: Completeness, Clarity, Architecture, Risk",
            "Synthesis merges findings + deterministic critical-risk veto",
            "HITL gate pauses for PM clarification, then resumes",
        ],
        "narration": (
            "The pipeline has five stages. First, a Document MCP Server reads the PRD. "
            "Then a Policy Gate rejects any PRD containing API keys or personal information. "
            "Next, four specialist agents run in parallel using Google ADK: "
            "a Completeness Checker, a Clarity Checker, an Architecture Fit Assessor, "
            "and a Risk and Compliance Checker. "
            "A Synthesis Agent merges their findings, with a deterministic veto that forces "
            "a pause if any risk is critical. Finally, a Human-in-the-Loop gate asks the PM "
            "clarifying questions before the pipeline continues."
        ),
    },
    {
        "title": "Policy Gate Demo",
        "subtitle": "prd-003: PRD with embedded API key",
        "bullets": [
            'PRD contains: AIzaSyDabc123def456ghi789jkl012mno345pqr',
            "Policy gate: 10 regex rules in human-reviewable YAML",
            "Result: REJECTED before any agent reads the PRD",
            "Violation: google_api_key at line 40",
        ],
        "narration": (
            "The policy gate runs first, before any agent reads the PRD. "
            "Here's what happens when a PRD contains an embedded Google API key. "
            "The regex scanner detects the AIza prefix pattern at line forty, "
            "and the PRD is immediately rejected. "
            "No specialist agent processes it. The rejection is logged in the audit trail "
            "with the exact pattern and line number."
        ),
    },
    {
        "title": "Completeness + Clarity Demo",
        "subtitle": "prd-001 (pass) vs prd-002 (needs_clarification)",
        "bullets": [
            "prd-001 Dark Mode: completeness=100, 1 clarity item → PASS",
            "prd-002 Wishlist: completeness=60, missing acceptance_criteria → NEEDS_CLARIFICATION",
            "prd-004 Search: 6 vague terms ('fast', 'scalable', 'user-friendly') → flagged",
            "Each vague term generates a specific clarifying question for the PM",
        ],
        "narration": (
            "The Completeness Checker correctly differentiates PRDs. "
            "A complete PRD scores 100 and passes. "
            "A PRD missing acceptance criteria scores 60 and is flagged. "
            "The Clarity Checker identifies vague terms like fast, scalable, and user-friendly. "
            "For each vague term, it generates a specific clarifying question addressed to the PM. "
            "For example: Define target p95 latency in milliseconds. "
            "This ensures engineers start with measurable requirements, not vague wishes."
        ),
    },
    {
        "title": "Risk Assessment Demo",
        "subtitle": "prd-005: Inventory Sync — 5 risk findings",
        "bullets": [
            "HIGH: No encryption for Shopify API keys at rest",
            "MEDIUM: No rate limiting on webhook endpoint (DoS risk)",
            "MEDIUM: Reconciliation job could hit Shopify API limits",
            "MEDIUM: Race condition in conflict detection",
            "LOW: 90-day audit retention too short for disputes",
        ],
        "narration": (
            "The Risk and Compliance Checker evaluates security, GDPR, PCI-DSS, and "
            "performance risks. For a real-time inventory sync feature, it found five issues: "
            "unencrypted API keys at rest, missing rate limiting on the webhook endpoint, "
            "potential API limit exhaustion from the reconciliation job, a race condition "
            "in conflict detection, and audit retention that's too short for dispute resolution. "
            "Any critical finding triggers the deterministic veto, forcing the pipeline to pause."
        ),
    },
    {
        "title": "Deployability Demo",
        "subtitle": "Live public endpoint — no Docker needed",
        "bullets": [
            "Public URL: trycloudflare.com (cloudflared tunnel)",
            "GET /health returns {status: ok, service: prd-triage-agent}",
            "POST /triage with prd-003 returns verdict: reject (policy gate)",
            "FastAPI + uvicorn + Dockerfile ready for Cloud Run",
        ],
        "narration": (
            "The agent is deployed as a public endpoint. "
            "Right now, you can send a health check and get a live response. "
            "When I submit the API-key-contaminated PRD through the public endpoint, "
            "the policy gate rejects it instantly — before any agent processes it. "
            "The FastAPI server runs behind a cloudflared tunnel, "
            "and the Dockerfile is ready for Google Cloud Run deployment."
        ),
    },
    {
        "title": "Antigravity Integration",
        "subtitle": "Custom Skill + MCP server configured",
        "bullets": [
            "prd-analysis Skill deployed to ~/.gemini/config/skills/",
            "Document MCP server registered in mcp_config.json",
            "Skill triggers triage pipeline directly from Antigravity IDE",
            "Level 3 procedural skill with explicit trigger conditions",
        ],
        "narration": (
            "The project integrates with Google Antigravity through two mechanisms. "
            "First, a custom prd-analysis Skill is deployed to Antigravity's skills directory, "
            "so users can trigger the triage pipeline by asking Antigravity to analyze a PRD. "
            "Second, the Document MCP server is registered in Antigravity's MCP config, "
            "making the four document tools available to any Antigravity agent. "
            "This is a Level 3 procedural skill with explicit trigger conditions and step-by-step execution."
        ),
    },
    {
        "title": "6 Key Concepts + Build",
        "subtitle": "Google x Kaggle AI Agents Capstone 2026",
        "bullets": [
            "ADK: ParallelAgent fan-out + SequentialAgent pipeline",
            "MCP: Custom Document MCP server (4 tools, stdio)",
            "Antigravity: IDE development + custom Skill trigger",
            "Security: Policy gate + HITL + critical-risk veto",
            "Deployability: FastAPI + Cloud Run + cloudflared tunnel",
            "Skills: prd-analysis Level 3 procedural Skill",
        ],
        "narration": (
            "The project demonstrates all six Google AI agent Key Concepts. "
            "ADK for multi-agent orchestration with parallel and sequential workflows. "
            "MCP for the document server. "
            "Antigravity for development and skill execution. "
            "Security with policy gates and human-in-the-loop checkpoints. "
            "Deployability via FastAPI and Cloud Run. "
            "And Skills with a custom prd-analysis procedural skill. "
            "Built with Spec-Driven Development using Spectra: "
            "thirty tasks tracked, one hundred twenty-one tests passing, "
            "and a live public endpoint. "
            "Thank you for watching."
        ),
    },
]


def main():
    print(f"Output dir: {TMP}")
    print(f"ffmpeg: {FFMPEG}")
    print()

    segments = []
    for i, seg in enumerate(SEGMENTS):
        print(f"[{i+1}/{len(SEGMENTS)}] {seg['title']}...")
        slide = make_slide(seg["title"], seg["bullets"], seg.get("subtitle", ""))
        mp4 = make_segment(slide, seg["narration"])
        segments.append(mp4)

        # Check duration
        result = subprocess.run([FFMPEG, "-i", str(mp4)], capture_output=True, text=True)
        for line in result.stderr.split("\n"):
            if "Duration" in line:
                dur = line.split("Duration:")[1].split(",")[0].strip()
                print(f"       Duration: {dur}")
                break

    print(f"\nConcatenating {len(segments)} segments...")
    output = Path("assets/demo_video.mp4")
    output.parent.mkdir(exist_ok=True)
    concat_segments(segments, output)

    # Get final duration
    result = subprocess.run([FFMPEG, "-i", str(output)], capture_output=True, text=True)
    for line in result.stderr.split("\n"):
        if "Duration" in line:
            dur = line.split("Duration:")[1].split(",")[0].strip()
            size_mb = os.path.getsize(output) / (1024 * 1024)
            print(f"\n✅ Video saved: {output}")
            print(f"   Duration: {dur}")
            print(f"   Size: {size_mb:.1f} MB")
            print(f"   Resolution: {W}x{H}")
            break


if __name__ == "__main__":
    main()
