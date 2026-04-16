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

## Configuration

Edit `settings.json` to customize CC mappings and MIDI channels. The file includes a `_helptext` section with inline documentation.

### Channel Inheritance

Channels inherit from parent levels when left empty:

```
Row Channel → Bank Channel → Global Channel
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
- Bank 1, rows 0,1,3: Use global channels (1,2,3,4)
- Bank 1, row 2: Use channels 5,6
- Bank 2, rows 0,1: Use bank channels (8,9)
- Bank 2, row 2: Use global channels (1,2,3,4)
- Bank 2, row 3: Use channel 10

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

- This repository (download or clone it)
- A USB-C cable connected to the LumaFader

### Locate the Boot Button

Remove the top panel to access the boot button on the Raspberry Pi Pico.

![Boot button location](images/boot_button.png)

### Steps

1. **Enter boot mode:** Hold the **BOOT** button on the Pico, then plug in the USB cable (or tap RESET while holding BOOT). Release the button. A drive called **RPI-RP2** should appear on your computer.

2. **Flash nuke:** Drag `uf2 current/flash_nuke.uf2` onto the **RPI-RP2** drive. The device will reboot and reappear as **RPI-RP2** after a few seconds.

3. **Install CircuitPython:** Drag `uf2 current/adafruit-circuitpython-raspberry_pi_pico-en_US-8.2.6.uf2` onto the **RPI-RP2** drive. The device will reboot and reappear as a drive called **CIRCUITPY**.

4. **Copy source files:** Copy the entire contents of the `src/` folder onto the **CIRCUITPY** drive. This includes all `.py` files, `settings.json`, and the `lib/` folder. Overwrite if prompted.

5. **Done.** The device will restart automatically and run the new firmware.
