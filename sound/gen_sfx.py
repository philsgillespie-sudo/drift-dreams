"""Procedural sound-effect generator for the drifting game.

Usage:
    python sound/gen_sfx.py [out_dir]

Writes mono 44.1 kHz Ogg Vorbis files to assets/audio/sfx by default.
Needs numpy and soundfile (pip install numpy soundfile); the game itself
doesn't. Every sound is seeded, so re-running gives identical output; tweak
the parameters in a make_* function and re-run to iterate.

Files ending in _loop are seamless loops. pygame can't pitch-shift, so the
engine is a ladder of loops named engine_<rpm>_loop, each synthesised at
that RPM; sound/engine.py crossfades between the two either side of the
current revs.
"""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
TAU = 2 * np.pi
ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets" / "audio" / "sfx"


# ---------------------------------------------------------------- helpers

def samples(dur):
    return int(round(dur * SR))


def secs(n):
    return np.arange(n) / SR


def lowpass(fc, order=2):
    return lambda f: 1 / np.sqrt(1 + (f / fc) ** (2 * order))


def highpass(fc, order=2):
    return lambda f: 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** (2 * order))


def bandpass(lo, hi, order=2):
    lp, hp = lowpass(hi, order), highpass(lo, order)
    return lambda f: lp(f) * hp(f)


def resonance(fc, q):
    return lambda f: 1 / np.sqrt(1 + (q * (f / fc - fc / np.maximum(f, 1e-3))) ** 2)


def filt(x, *responses, loop=False):
    """Zero-phase FFT filter. Loops are filtered circularly so they stay
    seamless; one-shots are padded so the tail doesn't wrap onto the start."""
    pad = 0 if loop else SR // 2
    y = np.concatenate([x, np.zeros(pad)])
    f = np.fft.rfftfreq(len(y), 1 / SR)
    h = np.ones_like(f)
    for r in responses:
        h = h * r(f)
    return np.fft.irfft(np.fft.rfft(y) * h, n=len(y))[:len(x)]


def unit(x):
    return x / (np.max(np.abs(x)) + 1e-12)


def fade(x, fade_in=0.002, fade_out=0.01):
    x = x.copy()
    a, b = samples(fade_in), samples(fade_out)
    if a:
        x[:a] *= np.linspace(0, 1, a)
    if b:
        x[-b:] *= np.linspace(1, 0, b)
    return x


def place(buf, x, at):
    i = samples(at)
    end = min(len(buf), i + len(x))
    if end > i:
        buf[i:end] += x[:end - i]


def noise(rng, n):
    return rng.standard_normal(n)


def slow_mod(rng, n, cutoff):
    """Smooth random control signal in [-1, 1] that loops over n samples."""
    return unit(filt(noise(rng, n), lowpass(cutoff, 4), loop=True))


def sweep_phase(freq):
    return TAU * np.cumsum(freq) / SR


def looped_phase(freq):
    """Phase for a time-varying frequency, nudged so it completes a whole
    number of cycles over the buffer and the loop point is click-free."""
    cycles = np.sum(freq) / SR
    freq = freq * (round(cycles) / cycles)
    return TAU * np.concatenate([[0.0], np.cumsum(freq)[:-1]]) / SR


def osc(phase, base_hz, kind="square", max_hz=12000):
    """Band-limited oscillator built from harmonics of `phase`."""
    out = np.zeros_like(phase)
    for h in range(1, int(max_hz // base_hz) + 1):
        if kind == "sine":
            a = 1.0 if h == 1 else 0.0
        elif kind == "saw":
            a = 1 / h
        elif kind == "square":
            a = 1 / h if h % 2 else 0.0
        elif kind == "triangle":
            a = (-1) ** ((h - 1) // 2) / h ** 2 if h % 2 else 0.0
        if a:
            out += a * np.sin(h * phase)
    return out


def note(hz, dur, kind="square", attack=0.005, decay=0.2, sustain=0.6, release=0.08, vibrato=0.0):
    t = secs(samples(dur + release))
    depth = vibrato * np.clip((t - 0.15) / 0.25, 0, 1)  # vibrato fades in
    phase = sweep_phase(hz * (1 + depth * np.sin(TAU * 5.5 * t)))
    env = np.where(t < attack, t / attack, sustain + (1 - sustain) * np.exp(-(t - attack) / decay))
    env *= np.clip(1 - (t - dur) / release, 0, 1)
    return osc(phase, hz, kind) * env


def modes(rng, t, partials, detune=0.02):
    """Sum of decaying sine modes: (hz, decay_s, amp) - metal, plastic, etc."""
    out = np.zeros_like(t)
    for hz, decay, amp in partials:
        hz *= 1 + detune * rng.standard_normal()
        out += amp * np.sin(TAU * hz * t + rng.uniform(0, TAU)) * np.exp(-t / decay)
    return out


def debris(rng, n, count, start, spread, hz_range, amp):
    """Scattered small pings, e.g. bits of bodywork landing after a crash."""
    out = np.zeros(n)
    t = secs(samples(0.04))
    for _ in range(count):
        at = start + rng.exponential(spread)
        if samples(at) >= n:
            continue
        ping = (np.sin(TAU * rng.uniform(*hz_range) * t) * np.exp(-t / rng.uniform(0.004, 0.015))
                + 0.5 * noise(rng, len(t)) * np.exp(-t / 0.002))
        place(out, amp * np.exp(-(at - start) / (spread * 1.5)) * rng.uniform(0.3, 1) * ping, at)
    return out


def reverb(rng, x, decay=0.35, wet=0.2, length=1.2):
    """Cheap convolution reverb with a decaying-noise impulse response."""
    t = secs(samples(length))
    ir = filt(noise(rng, len(t)) * np.exp(-t / decay), lowpass(5000))
    m = len(x) + len(t) - 1
    y = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[:len(x)]
    return x + wet * unit(y) * np.max(np.abs(x))


# ----------------------------------------------------------------- engine

def make_engine_loop(rpm, brightness, seed, seconds=2.0):
    """Big 4-cylinder as a train of exhaust pulses (2 firings per rev), with
    low body resonances, a sub-octave rumble and a lumpy idle for grunt, plus
    a blatty rasp from a holed muffler leaking on every pulse."""
    rng = np.random.default_rng(seed)
    period = int(round(SR / (rpm / 30)))
    count = max(4, int(round(seconds * SR / period / 4)) * 4)
    n = period * count
    plen = period * 3
    tp = secs(plen)
    decay = period / SR * 0.45
    body = (np.sin(TAU * 85 * tp) + 0.6 * np.sin(TAU * 210 * tp + 1.0)
            + 0.25 * brightness * np.sin(TAU * 520 * tp + 2.0))
    onset = 1 - np.exp(-tp / 0.0006)
    cylinders = [1.0, 0.7, 0.92, 0.62]  # uneven cylinders give the lope
    out = np.zeros(n)
    leak_env = np.zeros(n)
    leak_decay = 1 - np.exp(-tp / 0.0003)
    for i in range(count):
        burst = 0.4 * filt(noise(rng, plen), lowpass(1200)) * np.exp(-tp / (decay * 0.5))
        pulse = (body * np.exp(-tp / decay) + burst) * onset
        amp = cylinders[i % 4] * (1 + 0.1 * rng.standard_normal())
        jitter = int(rng.integers(-(period // 20), period // 20 + 1))
        idx = (i * period + jitter + np.arange(plen)) % n
        np.add.at(out, idx, amp * pulse)
        # the leak spits on each pulse, unevenly - some pulses barely, some loud
        spit = amp * rng.uniform(0.4, 1.3) * np.exp(-tp / (period / SR * 0.3)) * leak_decay
        np.add.at(leak_env, idx, spit)

    # holed muffler: raspy noise with a couple of blatty resonances, gated by the pulses
    rasp = filt(noise(rng, n), bandpass(220, 3200), loop=True)
    rasp = unit(rasp + 0.8 * filt(rasp, resonance(480, 2.5), loop=True)
                + 0.5 * filt(rasp, resonance(1150, 3), loop=True))
    leak = rasp * unit(leak_env)

    # half-firing-rate rumble; count is a multiple of 4, so it loops cleanly
    t = secs(n)
    fire_hz = SR / period
    sub = np.sin(TAU * fire_hz / 2 * t) + 0.5 * np.sin(TAU * fire_hz / 4 * t + 0.7)
    pulse_env = np.clip(unit(filt(np.abs(out), lowpass(rpm / 20), loop=True)), 0, 1)
    hiss = unit(filt(noise(rng, n), bandpass(1200, 4500), loop=True)) * (0.4 + 0.6 * pulse_env)
    out = unit(out) + 0.35 * sub * (0.5 + 0.5 * pulse_env) + 0.03 * brightness * hiss
    out = filt(out, highpass(25), lowpass(600 + 1400 * brightness), loop=True)
    out = unit(out) + 0.5 * leak  # after the lowpass so the rasp survives
    # lopsided clipping adds even harmonics: a buzzier, blattier distortion
    out = np.tanh(3.5 * unit(out) + 0.35) - np.tanh(0.35)
    return out - out.mean()


def engine_rpm(rpm):
    """Actual RPM after rounding the firing period to whole samples."""
    return 30 * SR / int(round(SR / (rpm / 30)))


# ------------------------------------------------------------------ tyres

def squeal_voice(rng, n, base_hz, wobble):
    f = base_hz * (1 + wobble * slow_mod(rng, n, 5) + 0.012 * slow_mod(rng, n, 35))
    ph = looped_phase(f)
    tone = np.sin(ph) + 0.4 * np.sin(2 * ph + 0.5) + 0.15 * np.sin(3 * ph + 1.1)
    return tone * (0.7 + 0.3 * slow_mod(rng, n, 9))


def make_tire_screech_loop(seed=11, seconds=2.0):
    rng = np.random.default_rng(seed)
    n = samples(seconds)
    tonal = squeal_voice(rng, n, 1180, 0.05) + 0.6 * squeal_voice(rng, n, 1530, 0.06)
    hiss = (unit(filt(noise(rng, n), resonance(1180, 6), loop=True))
            + 0.6 * unit(filt(noise(rng, n), resonance(2400, 5), loop=True)))
    broad = unit(filt(noise(rng, n), bandpass(600, 7000), loop=True))
    x = 0.55 * unit(tonal) + 0.35 * unit(hiss) + 0.18 * broad
    x *= 0.85 + 0.15 * slow_mod(rng, n, 3)
    return filt(x, highpass(350), lowpass(8000), loop=True)


# ---------------------------------------------------------------- impacts

def make_crash_heavy(seed=21):
    rng = np.random.default_rng(seed)
    n = samples(1.8)
    t = secs(n)
    thump = np.sin(sweep_phase(38 + 95 * np.exp(-t / 0.045))) * np.exp(-t / 0.16) * (1 - np.exp(-t / 0.002))
    burst = unit(filt(noise(rng, n), bandpass(150, 5000))) * np.exp(-t / 0.07)
    rough = unit(np.abs(filt(noise(rng, n), lowpass(60))))
    crumple = np.zeros(n)
    place(crumple, unit(filt(noise(rng, n), bandpass(900, 7000))) * rough * np.exp(-t / 0.3), 0.02)
    metal = modes(rng, t, [(523, .45, 1), (1187, .35, .7), (1744, .28, .55),
                           (2391, .2, .4), (3307, .15, .3), (4410, .1, .2)])
    rattle = debris(rng, n, 30, 0.08, 0.25, (1800, 6500), 0.5)
    x = thump + 0.8 * burst + 0.45 * crumple + 0.35 * unit(metal) + rattle
    return fade(np.tanh(1.8 * unit(x)), 0.0005, 0.15)


def make_crash_light(seed=22):
    rng = np.random.default_rng(seed)
    n = samples(0.7)
    t = secs(n)
    thump = np.sin(sweep_phase(60 + 70 * np.exp(-t / 0.03))) * np.exp(-t / 0.07) * (1 - np.exp(-t / 0.002))
    burst = unit(filt(noise(rng, n), bandpass(300, 6000))) * np.exp(-t / 0.03)
    metal = modes(rng, t, [(610, .18, 1), (1420, .12, .6), (2270, .08, .4)])
    rattle = debris(rng, n, 8, 0.05, 0.1, (2000, 6000), 0.3)
    x = 0.8 * thump + 0.6 * burst + 0.3 * unit(metal) + rattle
    return fade(np.tanh(1.4 * unit(x)), 0.0005, 0.08)


def bonk(rng, t, base, gain):
    """Hollow plastic hit (traffic cone)."""
    drop = 1 - 0.06 * (1 - np.exp(-t / 0.03))
    out = np.zeros_like(t)
    for ratio, decay, amp in [(1.0, .09, 1), (2.68, .05, .5), (4.55, .03, .3)]:
        out += amp * np.sin(sweep_phase(base * ratio * drop)) * np.exp(-t / decay)
    click = filt(noise(rng, len(t)), highpass(2500)) * np.exp(-t / 0.0025)
    return gain * (out + 0.4 * unit(click))


def make_cone_hit(seed=23):
    rng = np.random.default_rng(seed)
    buf = np.zeros(samples(0.6))
    t = secs(samples(0.25))
    for at, base, gain in [(0, 360, 1), (0.16, 395, 0.45), (0.29, 380, 0.22)]:  # hit, then bounces
        place(buf, bonk(rng, t, base, gain), at)
    return fade(buf)


def make_tyre_barrier_hit(seed=24):
    rng = np.random.default_rng(seed)
    n = samples(0.7)
    t = secs(n)
    thud = np.sin(sweep_phase(48 + 40 * np.exp(-t / 0.03))) * np.exp(-t / 0.12) * (1 - np.exp(-t / 0.003))
    boing = 0.5 * np.sin(sweep_phase(150 * (1 + 0.08 * np.sin(TAU * 9 * t)))) * np.exp(-t / 0.09)
    muff = 0.6 * unit(filt(noise(rng, n), lowpass(700, 4))) * np.exp(-t / 0.05)
    hit = thud + boing + muff
    buf = hit.copy()
    place(buf, 0.35 * hit, 0.17)  # rubber rebound
    return fade(buf)


# ---------------------------------------------------------------- hazards

def make_oil_slip(seed=31):
    rng = np.random.default_rng(seed)
    n = samples(0.8)
    t = secs(n)
    splat = 0.7 * unit(filt(noise(rng, n), bandpass(250, 3000))) * np.exp(-t / 0.06)
    slide_f = (700 * np.exp(-t / 0.35) + 120) * (1 + 0.12 * np.sin(TAU * 14 * t))
    slide = unit(osc(sweep_phase(slide_f), 820, "triangle")) * (1 - np.exp(-t / 0.03)) * np.exp(-t / 0.3)
    squelch = unit(filt(noise(rng, n), resonance(900, 3))) * (0.5 + 0.5 * np.sin(TAU * 18 * t)) * np.exp(-t / 0.25)
    return fade(splat + 0.6 * slide + 0.4 * squelch, 0.001, 0.05)


# --------------------------------------------------------------- surfaces

def make_gravel_loop(seed=41, seconds=2.0):
    rng = np.random.default_rng(seed)
    n = samples(seconds)
    grains = np.zeros(n)
    tg = secs(samples(0.004))
    for _ in range(int(700 * seconds)):
        g = noise(rng, len(tg)) * np.exp(-tg / rng.uniform(0.0004, 0.0015))
        np.add.at(grains, (rng.integers(n) + np.arange(len(tg))) % n, rng.exponential(0.5) * g)
    grains = filt(grains, bandpass(900, 9000), loop=True)
    rumble = filt(noise(rng, n), lowpass(220), loop=True)
    return filt(unit(grains) + 0.35 * unit(rumble), highpass(40), loop=True)


def make_grass_loop(seed=42, seconds=2.0):
    rng = np.random.default_rng(seed)
    n = samples(seconds)
    swish = filt(noise(rng, n), bandpass(500, 4500, 1), loop=True) * (0.65 + 0.35 * slow_mod(rng, n, 4))
    thrum = filt(noise(rng, n), lowpass(160), loop=True)
    ticks = np.zeros(n)
    tg = secs(samples(0.003))
    for _ in range(int(60 * seconds)):
        g = noise(rng, len(tg)) * np.exp(-tg / 0.0006)
        np.add.at(ticks, (rng.integers(n) + np.arange(len(tg))) % n, rng.uniform(0.2, 1) * g)
    ticks = filt(ticks, bandpass(2000, 7000), loop=True)
    return unit(swish) + 0.4 * unit(thrum) + 0.25 * unit(ticks)


def make_kerb_rumble_loop(seed=43, rate=24, seconds=1.0):
    """Rumble-strip thumps at `rate` per second; pitch it up with speed."""
    rng = np.random.default_rng(seed)
    period = int(round(SR / rate))
    count = int(round(seconds * SR / period))
    n = period * count
    tp = secs(period * 2)  # tails run into the next thump
    out = np.zeros(n)
    for i in range(count):
        thump = (np.sin(sweep_phase(70 + 30 * np.exp(-tp / 0.005))) * np.exp(-tp / 0.018)
                 + 0.5 * noise(rng, len(tp)) * np.exp(-tp / 0.006))
        np.add.at(out, (i * period + np.arange(len(tp))) % n, (1.0 if i % 2 else 0.85) * thump)
    return filt(out, bandpass(35, 2500), loop=True)


# ----------------------------------------------------------- race events

C5, E5, G4, G5, C6 = 523.25, 659.25, 392.0, 783.99, 1046.5


def make_finish_line(seed=51):
    """Fanfare sting for crossing the line at the end of the race."""
    rng = np.random.default_rng(seed)
    n = samples(2.6)
    buf = np.zeros(n)

    def voice(hz, dur, at, gain, vibrato=0.0):
        kw = dict(decay=0.3, sustain=0.5, release=0.25, vibrato=vibrato)
        place(buf, gain * (0.5 * note(hz, dur, "square", **kw) + 0.4 * note(hz * 1.003, dur, "saw", **kw)), at)

    for i, hz in enumerate([G4, C5, E5, G5]):  # pickup run
        voice(hz, 0.1, i * 0.11, 0.5)
    for hz in [C5, E5, G5, C6]:  # held chord
        voice(hz, 1.5, 0.46, 0.35, vibrato=0.006)
    place(buf, 0.5 * note(130.81, 1.5, "triangle", decay=0.4, sustain=0.5, release=0.25), 0.46)
    tt = secs(samples(0.6))
    place(buf, 0.6 * np.sin(sweep_phase(55 + 10 * np.exp(-tt / 0.05))) * np.exp(-tt / 0.4), 0.46)
    ts = secs(samples(0.4))
    for _ in range(10):  # sparkles
        hz = rng.choice([2093.0, 2637.0, 3136.0, 4186.0])
        place(buf, 0.12 * np.sin(TAU * hz * ts) * np.exp(-ts / 0.15), 0.46 + rng.uniform(0, 1.2))
    return fade(reverb(rng, filt(buf, lowpass(9000))), 0.001, 0.2)


def make_lap_complete(seed=52):
    rng = np.random.default_rng(seed)
    buf = np.zeros(samples(0.9))
    for at, hz in [(0, C6), (0.09, 1568.0)]:
        kw = dict(decay=0.25, sustain=0.0, release=0.2)
        place(buf, 0.7 * note(hz, 0.25, "triangle", **kw) + 0.2 * note(hz, 0.25, "square", **kw), at)
    return fade(reverb(rng, buf, decay=0.25, wet=0.15), 0.001, 0.1)


def make_countdown_beep():
    kw = dict(attack=0.002, decay=0.5, sustain=0.8, release=0.03)
    x = 0.6 * note(880, 0.16, "square", **kw) + 0.4 * note(880, 0.16, "triangle", **kw)
    return fade(filt(x, lowpass(6000)))


def make_countdown_go():
    kw = dict(attack=0.002, decay=0.4, sustain=0.7, release=0.15)
    x = 0.5 * note(1760, 0.5, "square", **kw) + 0.5 * note(880, 0.5, "square", **kw)
    return fade(filt(x, lowpass(7000)))


# --------------------------------------------------------------------- UI

def make_ui_click(seed=61):
    rng = np.random.default_rng(seed)
    t = secs(samples(0.05))
    x = np.sin(TAU * 2400 * t) * np.exp(-t / 0.006) + 0.3 * filt(noise(rng, len(t)), highpass(3000)) * np.exp(-t / 0.001)
    return fade(x, 0.0005, 0.005)


def two_note_blip(first, second):
    buf = np.zeros(samples(0.25))
    kw = dict(decay=0.08, sustain=0.0, release=0.05)
    for at, hz in [(0, first), (0.07, second)]:
        place(buf, 0.8 * note(hz, 0.06, "triangle", **kw) + 0.2 * note(hz, 0.06, "square", **kw), at)
    return fade(buf)


def make_ui_confirm():
    return two_note_blip(1318.5, 1975.5)


def make_ui_back():
    return two_note_blip(987.77, 659.25)


# ------------------------------------------------------------------- main

ENGINE_IDLE, ENGINE_TOP, ENGINE_RUNGS = 700, 6400, 14


def engine_ladder():
    """Engine loops at geometrically spaced RPMs, brighter as the revs rise."""
    out = []
    for k, rpm in enumerate(np.geomspace(ENGINE_IDLE, ENGINE_TOP, ENGINE_RUNGS)):
        brightness = 0.5 + 0.5 * np.log(rpm / ENGINE_IDLE) / np.log(ENGINE_TOP / ENGINE_IDLE)
        out.append((f"engine_{round(engine_rpm(rpm)):04d}_loop",
                    lambda rpm=rpm, b=brightness, k=k: make_engine_loop(rpm, b, k + 1), "rms", -12))
    return out


# name, generator, level mode, level in dBFS (peak for one-shots, RMS for loops)
SOUNDS = engine_ladder() + [
    ("tire_screech_loop", make_tire_screech_loop, "rms", -18),
    ("crash_heavy", make_crash_heavy, "peak", -1),
    ("crash_light", make_crash_light, "peak", -3),
    ("cone_hit", make_cone_hit, "peak", -4),
    ("tyre_barrier_hit", make_tyre_barrier_hit, "peak", -2),
    ("oil_slip", make_oil_slip, "peak", -4),
    ("gravel_loop", make_gravel_loop, "rms", -24),
    ("grass_loop", make_grass_loop, "rms", -26),
    ("kerb_rumble_loop", make_kerb_rumble_loop, "rms", -20),
    ("finish_line", make_finish_line, "peak", -1),
    ("lap_complete", make_lap_complete, "peak", -3),
    ("countdown_beep", make_countdown_beep, "peak", -4),
    ("countdown_go", make_countdown_go, "peak", -3),
    ("ui_click", make_ui_click, "peak", -8),
    ("ui_confirm", make_ui_confirm, "peak", -6),
    ("ui_back", make_ui_back, "peak", -6),
]


def save(name, x, mode, level_db):
    gain = 10 ** (level_db / 20)
    x = x * (gain / np.sqrt(np.mean(x ** 2)) if mode == "rms" else gain / np.max(np.abs(x)))
    peak = np.max(np.abs(x))
    if peak > 0.99:
        print(f"  warning: {name} peaked at {peak:.2f}, scaled down to avoid clipping")
        x *= 0.99 / peak
    if name.endswith("_loop"):
        # Vorbis smears the very start/end of a file, so start the loop at its
        # quietest moment where that error is smallest (any rotation of a
        # seamless loop is still seamless)
        energy = np.convolve(np.concatenate([x, x[:255]]) ** 2, np.ones(256), "valid")
        x = np.roll(x, -int(np.argmin(energy[:len(x)])) - 128)
    sf.write(OUT / f"{name}.ogg", x.astype(np.float32), SR, format="OGG", subtype="VORBIS")
    return len(x) / SR


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("engine_*_loop.ogg"):  # rung RPMs change when the ladder is retuned
        stale.unlink()
    for name, make, mode, level in SOUNDS:
        print(f"{name:20s} {save(name, make(), mode, level):5.2f}s")
    print(f"wrote {len(SOUNDS)} files to {OUT}")


if __name__ == "__main__":
    main()
