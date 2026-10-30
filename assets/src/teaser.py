#!/usr/bin/env python3
"""Render the README teaser with Python 3.9+ and Pillow; no network or ffmpeg.

Usage: python3 assets/src/teaser.py [--font-dir /path/to/fonts]
Story: README.md and docs/what-we-learned.md. Bar heights are schematic.
Original vector artwork; no generated or third-party image assets.
"""
import argparse
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont


W, H, FPS, SECONDS = 1400, 750, 20, 25
NAVY, PANEL, EDGE = '#0b1c2e', '#122a3e', '#29465b'
WHITE, MUTED, GOLD, TEAL = '#f7f3e8', '#aec4d4', '#ffbc38', '#27daca'
CORAL, BLUE, PURPLE = '#ff947b', '#7eb9ec', '#b9a2e8'
COLORS = [TEAL, GOLD, BLUE, PURPLE, CORAL]
STEPS = ['Measure', 'Review', 'Change one thing', 'Re-measure']
STARTS = [3, 7, 11, 17]
FINDINGS = [
    '~150 spawns · ~80k tokens each',
    '450k–560k context, re-sent each turn',
    '~190 calls · grep → read → grep',
    '67 images in main context',
]
FIXES = [
    'Use a dispatch script',
    'Compact at 250k + plan pointer hook',
    'Code-map rule in CLAUDE.md',
    'Add an image-read hook',
]
# Real work stays constant; each intervention changes only its waste segment.
STACKS = [[74, 66, 64, 48, 40], [74, 14, 64, 48, 40],
          [74, 14, 18, 48, 40], [74, 14, 18, 48, 40],
          [74, 14, 18, 12, 40], [74, 14, 18, 12, 10]]


def ease(x):
    x = max(0, min(1, x))
    return x * x * (3 - 2 * x)


class Renderer:
    def __init__(self, font_dir=None):
        roots = ([Path(font_dir)] if font_dir else []) + [
            Path('/System/Library/Fonts'), Path('/Library/Fonts'),
            Path('/usr/share/fonts'), Path.home() / '.fonts']
        files = [p for root in roots if root.is_dir() for p in sorted(root.rglob('*'))
                 if p.suffix.lower() in {'.ttf', '.otf', '.ttc'}]

        def pick(names):
            for root in roots:
                for name in names:
                    for p in files:
                        if root in p.parents and name.lower() == p.name.lower():
                            return str(p)
            return None

        self.regular = pick(['Arial.ttf', 'DejaVuSans.ttf', 'LiberationSans-Regular.ttf'])
        self.bold = pick(['Arial Bold.ttf', 'DejaVuSans-Bold.ttf', 'LiberationSans-Bold.ttf'])
        self.mono = pick(['Menlo.ttc', 'DejaVuSansMono.ttf', 'LiberationMono-Regular.ttf'])
        self.cjk = pick(['Hiragino Sans GB.ttc', 'Arial Unicode.ttf', 'NotoSansCJK-Regular.ttc'])
        self.regular = self.regular or next((str(p) for p in files), None)
        if not self.regular:
            raise SystemExit('No scalable font found. Pass --font-dir with TTF/OTF fonts.')

    @lru_cache(maxsize=128)
    def font(self, size, kind='regular'):
        return ImageFont.truetype(getattr(self, kind) or self.regular, size)

    def text(self, xy, text, size=26, color=WHITE, kind='regular', anchor='lt'):
        self.d.text(xy, text, font=self.font(size, kind), fill=color, anchor=anchor)

    def box(self, rect, fill=PANEL, outline=EDGE, radius=18, width=1):
        self.d.rounded_rectangle(rect, radius, fill, outline, width)

    def base(self):
        self.im = Image.new('RGB', (W, H), '#071321')
        self.d = ImageDraw.Draw(self.im)
        self.box((10, 10, 1390, 740), NAVY, EDGE, 32)
        self.d.line((60, 128, 1340, 128), fill=EDGE, width=2)

    def brand(self, subtitle='continuous improvement for AI coding agents'):
        self.text((60, 43), 'Agent', 44, WHITE, 'bold')
        self.text((197, 43), 'Kaizen', 44, GOLD, 'bold')
        if self.cjk:
            self.text((360, 48), '改善', 32, TEAL, 'cjk')
        self.text((60, 96), subtitle, 26, MUTED)

    def steps(self, active=None, y=148):
        for i, label in enumerate(STEPS):
            x = 60 + i * 328
            self.box((x, y, x + 296, y + 51), PANEL,
                     TEAL if active == i else EDGE, 15, 2)
            self.text((x + 148, y + 14), label, 26,
                      TEAL if active == i else WHITE, 'bold', 'mt')
            if i < 3:
                self.text((x + 312, y + 12), '→', 26, GOLD, anchor='mt')

    def stamp(self, x, y, label, age=1):
        color = CORAL if label == 'REVERT' else TEAL
        bounce = math.sin(min(age, 1) * math.pi * 3) * 8 * (1 - min(age, 1))
        y = round(y - bounce)
        self.box((x, y, x + 104, y + 36), NAVY, color, 8, 2)
        self.text((x + 52, y + 7), label, 22, color, 'bold', 'mt')

    def chart(self, progress):
        self.box((914, 218, 1340, 580))
        self.text((938, 239), 'Weekly usage', 26, WHITE, 'bold')
        self.text((1316, 242), 'schematic', 22, MUTED, anchor='rt')
        self.d.line((940, 462, 1316, 462), fill=EDGE, width=2)
        for i, stack in enumerate(STACKS):
            if i > math.ceil(progress):
                continue
            amount = 1 if i <= progress else ease(progress - i + 1)
            if amount <= 0:
                continue
            x, y = 948 + i * 61, 461
            for height, color in zip(stack, COLORS):
                h = height * .54 * amount
                self.d.rectangle((x, y - h, x + 35, y), fill=color)
                y -= h
            if i == 3 and progress >= 3:
                self.text((x + 17, y - 30), '↔', 26, CORAL, anchor='mt')
        legends = [('Real work', TEAL), ('Spawns', GOLD),
                   ('Context', BLUE), ('Grep loops', PURPLE), ('Images', CORAL)]
        for i, (label, color) in enumerate(legends):
            x, y = 938 + (i % 2) * 194, 480 + (i // 2) * 30
            self.d.rounded_rectangle((x, y + 3, x + 25, y + 21), 3, fill=color)
            self.text((x + 35, y), label, 22, MUTED)

    def ledger(self, cycle, local, still=False):
        self.box((60, 218, 890, 580))
        self.text((84, 231), 'LEDGER', 26, GOLD, 'bold')
        self.text((866, 234), 'change → result → verdict', 22, MUTED, anchor='rt')
        failed = still or cycle > 2 or (cycle == 2 and local >= 2.2)
        retried = still or cycle > 2 or (cycle == 2 and local >= 3.7)
        # Keep the failed attempt and its retry as separate, permanent rows.
        rows = [(0, 0), (1, 1), (2, 2), (2, 3), (3, 4)]
        for source, slot in rows:
            y = 265 + slot * 64
            if slot:
                self.d.line((84, y - 6, 866, y - 6), fill=EDGE)
            if slot == 3:
                if not retried:
                    continue
                finding, fix = 'Retry code-map rule', 'Move into agents’ own context'
                entry_age = local - 3.7 if cycle == 2 else 1
            else:
                if source > cycle or (source == cycle and local < 1.4 and not still):
                    continue
                finding, fix = FINDINGS[source], FIXES[source]
                entry_age = local - 1.4 if source == cycle else 1
                if source == 2 and failed:
                    finding, fix = '5 codemap calls vs ~137 greps', 'Rule in CLAUDE.md: barely used'
            offset = 20 * (1 - ease(entry_age / .35)) if not still else 0
            self.d.rounded_rectangle((84, y, 89, y + 46), 2, COLORS[source + 1])
            self.text((102 + offset, y), finding, 26, WHITE, 'bold')
            self.text((102 + offset, y + 26), fix, 26, MUTED)
            if source == 2 and slot == 2 and failed:
                end = 102 + self.d.textlength(fix, font=self.font(26))
                self.d.line((102, y + 40, end, y + 40), fill=CORAL, width=2)
                age = local - 2.2 if cycle == 2 and not still else 1
                self.stamp(758, y + 5, 'REVERT', age)
            elif slot == 3:
                if still or cycle > 2 or local >= 5.0:
                    self.stamp(758, y + 5, 'KEEP', local - 5.0 if cycle == 2 and not still else 1)
            elif source < cycle or still or local >= 2.9:
                self.stamp(758, y + 5, 'KEEP', local - 2.9 if source == cycle and not still else 1)

    def detail(self, heading, line1, line2, color=TEAL):
        self.box((60, 598, 1340, 718), PANEL, color, 18, 2)
        self.text((84, 611), heading, 22, color, 'bold')
        self.text((84, 641), line1, 28, WHITE, 'bold')
        self.text((84, 679), line2, 26, MUTED)

    def dashboard(self, t, still=False):
        cycle = max(i for i, start in enumerate(STARTS) if t >= start)
        local = t - STARTS[cycle]
        self.brand()
        self.box((970, 49, 1340, 99), PANEL, TEAL, 14)
        self.text((1155, 63), 'token-audit · 0 tokens', 26, TEAL, 'mono', 'mt')
        phase = 0 if local < .7 else 1 if local < 1.4 else 2 if local < 2.4 else 3
        if cycle == 2 and local >= 2.2:
            phase = 2 if 3.7 <= local < 5.0 else 3
        self.steps(None if still else phase)
        self.ledger(cycle, local, still)
        progress = cycle + ease((local - 2.4) / .5)
        if cycle == 2:
            progress = 2 + ease((local - 2.2) / .4) + ease((local - 5.0) / .5)
        elif cycle == 3:
            progress += 1
        self.chart(5 if still else progress)
        if still:
            self.detail('START THE LOOP',
                        '/plugin install agent-kaizen@agent-kaizen-tools',
                        'Measure. Change one thing. Keep what pays, revert what doesn’t.', GOLD)
        elif cycle == 2 and local >= 2.2:
            if local < 3.7:
                self.detail('RE-MEASURE · REVERT', 'Barely used: 5 codemap calls vs ~137 greps.',
                            'The agents didn’t load CLAUDE.md. The first attempt didn’t pay off.', CORAL)
            elif local < 5.0:
                self.detail('RETRY · CHANGE ONE THING', 'Move the rule into the agents’ own context.',
                            'Keep the failed attempt in the ledger. Check the retry in the next audit.', GOLD)
            else:
                self.detail('RE-MEASURE · KEEP THE RETRY', 'The rule now reaches the agents doing the work.',
                            'The ledger keeps both attempts, so the result has a history.')
        elif phase == 0:
            self.detail('MEASURE · EVERY FEW DAYS', 'A script reads your Claude Code / Codex session logs.',
                        'Zero tokens to audit. Claude reviews the findings against the ledger.')
        elif phase == 1:
            self.detail('REVIEW · FIND ONE SOURCE OF WASTE', FINDINGS[cycle],
                        'Compare with the ledger. Choose one change.', GOLD)
        elif phase == 2:
            self.detail('CHANGE ONE THING · WRITE IT DOWN', FIXES[cycle],
                        'Record the reason and expected effect. Wait for the next audit.', GOLD)
        else:
            self.detail('RE-MEASURE', 'The next audit checks whether the change paid off.',
                        'Keep what helps. Revert or retry what doesn’t.')

    def title(self, t):
        self.text((70, 57), 'SMALL CHANGES. MEASURED.', 23, TEAL, 'bold')
        self.text((70, 205), 'Agent', 88, WHITE, 'bold')
        self.text((350, 205), 'Kaizen', 88, GOLD, 'bold')
        if self.cjk:
            self.text((74, 318), '改善', 48, TEAL, 'cjk')
        self.text((70, 407), 'continuous improvement', 35, WHITE)
        self.text((70, 454), 'for AI coding agents', 35, MUTED)
        cx, cy, r = 1060, 345, 159
        self.d.arc((cx-r, cy-r, cx+r, cy+r), 35, 335, fill=GOLD, width=13)
        theta = math.radians(35 + 300 * ease(min(t, 1.8) / 1.8))
        x, y = cx + r * math.cos(theta), cy + r * math.sin(theta)
        self.d.ellipse((x-14, y-14, x+14, y+14), fill=TEAL)
        self.box((942, 280, 1178, 410), PANEL, TEAL, 18, 2)
        self.text((1060, 299), '>_ LEDGER', 28, TEAL, 'mono', 'mt')
        for i, width in enumerate([150, 111, 132]):
            self.d.rounded_rectangle((968, 347+i*17, 968+width, 352+i*17), 2,
                                     GOLD if i == 1 else MUTED)
        self.text((1060, 539), 'Learn from your own logs.', 26, MUTED, anchor='mt')
        self.steps(y=626)

    def end(self):
        self.brand()
        self.text((700, 207), 'Measure. Change one thing.', 54, WHITE, 'bold', 'mt')
        self.text((700, 285), 'Keep what pays,', 54, TEAL, 'bold', 'mt')
        self.text((700, 358), 'revert what doesn’t.', 54, GOLD, 'bold', 'mt')
        self.box((220, 477, 1180, 559), PANEL, TEAL, 18, 2)
        self.text((700, 502), '/plugin install agent-kaizen@agent-kaizen-tools',
                  29, WHITE, 'mono', 'mt')
        self.text((700, 617), 'Your sessions → your ledger → your next improvement', 27, MUTED, anchor='mt')

    def frame(self, t, still=False):
        self.base()
        if still:
            self.dashboard(20.9, True)
        elif t < 3:
            self.title(t)
        elif t < 21:
            self.dashboard(t)
        else:
            self.end()
        return self.im


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font-dir', help='Preferred directory of scalable fonts')
    args = parser.parse_args()
    renderer = Renderer(args.font_dir)
    output = Path(__file__).resolve().parents[1]
    still = renderer.frame(0, still=True)
    still.save(output / 'teaser.png', optimize=True)
    # One palette for all frames. Sample transitions as well as the held cards.
    samples = [renderer.frame(t / 2).resize((280, 150)) for t in range(50)]
    atlas = Image.new('RGB', (280 * 10, 150 * 5))
    for i, sample in enumerate(samples):
        atlas.paste(sample, ((i % 10) * 280, (i // 10) * 150))
    adaptive = atlas.quantize(colors=112, method=Image.Quantize.MEDIANCUT)
    # Reserve the ink colors so small coral/blue regions retain their identity.
    inks = [NAVY, PANEL, EDGE, WHITE, MUTED, GOLD, TEAL, CORAL, BLUE, PURPLE, '#071321']
    rgb = [v for color in inks for v in ImageColor.getrgb(color)]
    rgb += adaptive.getpalette()[:112 * 3]
    rgb += list(ImageColor.getrgb(NAVY)) * (256 - len(rgb) // 3)
    palette = Image.new('P', (1, 1))
    palette.putpalette(rgb)
    frames, durations, previous = [], [], None
    for tick in range(FPS * SECONDS):
        frame = renderer.frame(tick / FPS).quantize(palette=palette, dither=Image.Dither.NONE)
        if previous is not None and ImageChops.difference(frame, previous).getbbox() is None:
            durations[-1] += 1000 // FPS
        else:
            frames.append(frame)
            durations.append(1000 // FPS)
            previous = frame
    frames[0].save(output / 'teaser.gif', save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=False, disposal=1)
    for name, limit in [('teaser.gif', 3_000_000), ('teaser.png', 400_000)]:
        size = (output / name).stat().st_size
        print(f'{name}: {size:,} bytes')
        if size > limit:
            raise SystemExit(f'{name} exceeds {limit:,} byte budget')
    print(f'{W}×{H}, {SECONDS}s, {len(frames)} unique frames; shared palette, infinite loop')


if __name__ == '__main__':
    main()
