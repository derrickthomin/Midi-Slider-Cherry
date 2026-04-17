# LumaFader 68

The LumaFader 68 is a compact MIDI controller featuring four long-throw faders, capable of controlling up to 68 parameters in your DAW or synthesizer (via mini TRS). It's ideal for both live performance and recording automation.

## Demo

[![LumaFader 68 Demo](https://img.youtube.com/vi/-r_8dHA1_Gs/0.jpg)](https://youtu.be/-r_8dHA1_Gs?si=00uZ8pCUi5EYb8bo)

*Click the image above to watch a demonstration on YouTube.*  

## Links

*   **Web Config Utility:** [Open Web Config](https://derrickthomin.github.io/Midi-Slider-Cherry/) — configure your LumaFader from the browser (Chrome/Edge, requires Web Serial)
*   **Project Writeup:** [www.djbajablast.com/post/lumafader68](https://www.djbajablast.com/post/lumafader68)
*   **Buy:** [Etsy - DJBB LumaFader 68](https://www.etsy.com/listing/1872693350/djbb-lumafader-68-midi-controller-rgb)

---

## What's New (April 2026)

- **Multi-channel output** -- send CC messages to multiple MIDI channels simultaneously using the `|` separator
- **Aftertouch support** -- channel pressure (aftertouch) messages now supported
- **Web Config Utility** -- configure settings directly from the browser via Web Serial (Chrome/Edge)

---

## Configuration

Use the web tool or Edit `settings.json` to customize CC mappings and MIDI channels. Learn mode is only available in the web tool. See manual for details on the json structure.

<img width="500" height="1182" alt="Web Settings Iterface" src="https://github.com/user-attachments/assets/b8ba807f-c97e-4158-9761-0b9c1cd95882" />


### Channel Inheritance
```

By default, all bank/row channels are empty (`""`), so everything uses `GLOBAL_CHANNEL`. 

### Keywords

| Keyword | Meaning | Valid In |
|---------|---------|----------|
| `""` (empty) | Inherit from parent | Bank, Row |
| `"GLOBAL"` | Use global channel directly | Bank, Row |
| `"BANK"` | Use bank channel | Row only |

### Multi-Channel Output

Output to multiple MIDI channels simultaneously using the `|` separator:

```json
{
    "GLOBAL_CHANNEL": "1|2|3|4",
    
    "CC_BANKS_1_CHANNEL": "",
    "CC_BANKS_1_ROW_CHANNELS": ["", "", "5|6", ""],
    
    "CC_BANKS_2_CHANNEL": "8|9",
    "CC_BANKS_2_ROW_CHANNELS": ["BANK", "BANK", "GLOBAL", "10"]
}
```

**In this example:**

| Bank | Slider(s) | Channel(s) |
|------|-----------|------------|
| 1 | a, b, d | Global (1,2,3,4) |
| 1 | c | 5, 6 |
| 2 | a, b | Bank (8,9) |
| 2 | c | Global (1,2,3,4) |
| 2 | d | 10 |

**Supported formats:**
- Single integer: `1` or `"1"`
- Multi-channel: `"1|2|3"`
- Empty/inherit: `""`
- Keywords: `"GLOBAL"`, `"BANK"`

> **Note:** For best results with pickup mode, avoid overlapping channels between different settings. If overlap occurs, pickup mode uses the first channel for crossing detection, which may cause value jumps on other channels.

> **Error handling:** Invalid values fall back gracefully (invalid row → bank, invalid bank → global, invalid global → channel 1). If the JSON file is malformed, factory defaults are used.

---

## Updating Firmware

### What You Need

- This repository (download it from this page)
- A USB-C data cable connected to the LumaFader

### Locate the Boot Button

The boot button is on the bottom PCB. See the image below for where it is located. I usually just stick a screwdriver through the hole in the case for the USB and use that to press the button. Alternaltivly you can take the top panel off with an m3 hex key.

<img width="450" height="1246" alt="Show Boot Button" src="https://github.com/user-attachments/assets/2fdeeb8c-3297-4982-aabe-627f1dcd7ce0" />

### Steps

1. **Enter boot mode:** Hold the **BOOT** button on the Pico, then plug in the USB cable (or tap RESET while holding BOOT). Release the button. A drive called **RPI-RP2** should appear on your computer.

2. **Flash nuke:** Drag `uf2 current/flash_nuke.uf2` onto the **RPI-RP2** drive. The device will reboot and reappear as **RPI-RP2** after a few seconds.

3. **Install CircuitPython:** Drag `uf2 current/adafruit-circuitpython-raspberry_pi_pico-en_US-8.2.6.uf2` onto the **RPI-RP2** drive. The device will reboot and reappear as a drive called **CIRCUITPY**.

4. **Copy source files:** Copy the entire contents of the `src/` folder onto the **CIRCUITPY** drive. This includes all `.py` files, `settings.json`, and the `lib/` folder. Overwrite if prompted.

5. **Done.** Unplug the LumaFader and plug it back in.
