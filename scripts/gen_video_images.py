#!/usr/bin/env python3
"""Generate the demo video's visual set with OpenAI images (cached).

  ./jev/bin/python scripts/gen_video_images.py [--force] [--model gpt-image-1] [--quality medium]

Writes work/video/showcase/assets/img_<name>.png. Skips any that already exist unless --force.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zeroops import paths  # noqa: E402

load_dotenv(paths.ENV)
KEY = os.getenv("OPENAI_API") or os.getenv("OPENAI_API_KEY") or ""

STYLE = ("dark cinematic, deep navy background, teal and cyan accents, minimal, clean, "
         "soft volumetric light, high detail, 16:9, no text, no words, no letters, no numbers")

PROMPTS = {
    "hero": "Wide shot of a modern network operations centre at night; rows of monitors glowing teal, a silhouetted operator; ",
    "industry": "Abstract glowing network topology of nodes and links, like a service graph; ",
    "gap": "Isometric illustration of an incident pipeline with five stages and one highlighted decision node; ",
    "jev": "Abstract branching decision paths with one glowing chosen route; ",
    "example": "Isometric technical illustration of a network path: a client, a load balancer and a server pool, with one broken link and a question mark glow; ",
    "evidence": "Abstract data visualisation, rising bars and a smooth probability curve on a grid; ",
    "value": "Isometric illustration of modular building blocks and levers, a small versatile toolkit; ",
    "path": "Isometric illustration of a three-stage roadmap with milestone markers; ",
    "close": "Abstract calm horizon with a fine glowing grid and a single bright line; ",
}


def gen(name: str, model: str, quality: str, force: bool) -> None:
    out = paths.DEMO_ASSETS / f"img_{name}.png"
    if out.exists() and not force:
        print(f"  {name}: exists, skipped")
        return
    body = {"model": model, "prompt": PROMPTS[name] + STYLE, "size": "1536x1024",
            "quality": quality, "n": 1}
    r = httpx.post("https://api.openai.com/v1/images/generations",
                   headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                   json=body, timeout=240)
    if r.status_code != 200:
        print(f"  {name}: ERROR {r.status_code} {r.text[:200]}"); return
    d = r.json()["data"][0]
    out.write_bytes(base64.b64decode(d["b64_json"]))
    print(f"  {name}: wrote {out.name} ({out.stat().st_size//1024} KB)")


def main() -> int:
    if not KEY:
        raise SystemExit("OPENAI_API not set in .env")
    args = sys.argv[1:]
    force = "--force" in args
    model = args[args.index("--model") + 1] if "--model" in args else "gpt-image-1"
    quality = args[args.index("--quality") + 1] if "--quality" in args else "medium"
    paths.DEMO_ASSETS.mkdir(parents=True, exist_ok=True)
    print(f"model={model} quality={quality} -> {paths.rel(paths.DEMO_ASSETS)}")
    for name in PROMPTS:
        gen(name, model, quality, force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
