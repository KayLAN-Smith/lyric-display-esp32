/*
 * Lyric Display - ESP32 + SSD1306 OLED
 *
 * Receives lyric text from a Windows PC over USB serial and displays
 * it on a 0.96" SSD1306 OLED (128x64, I2C).
 *
 * Display layout:
 *   ┌─────────────────────────┐
 *   │  Lyrics (word-wrapped,  │  top 48 px
 *   │  vertically scrollable) │
 *   ├─────────────────────────┤  separator line at y=49
 *   │ ▶  Artist – Song Title  │  status bar (y=51..63)
 *   └─────────────────────────┘
 *
 * Protocol (newline-delimited):
 *   PC -> ESP32:  CLR | TXT|<text> | PING | FONT|<1.0-3.0> | MODE|<LYR/EQ>
 *                 EQ|<levels>
 *                 STA|PLAY | STA|PAUSE | STA|STOP
 *                 META|<artist – title>
 *   ESP32 -> PC:  PONG | BTN|PRESS | BTN|LONG
 *
 * Hardware:
 *   - SSD1306 OLED: SDA=GPIO21, SCL=GPIO22, addr 0x3C
 *   - Button: GPIO4 with internal pull-up (active LOW)
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Fonts/FreeSans9pt7b.h>
#include <Fonts/FreeSans12pt7b.h>

// ── Display configuration ───────────────────────────────────────────
#define SCREEN_WIDTH    128
#define SCREEN_HEIGHT   64
#define OLED_RESET      -1
#define SCREEN_ADDRESS  0x3C
#define SDA_PIN         21
#define SCL_PIN         22

// ── Layout constants ────────────────────────────────────────────────
#define LYRICS_AREA_HEIGHT  53   // pixels for lyric text area
#define SEPARATOR_Y         53   // y of the horizontal divider line
#define STATUS_BAR_Y        54   // y where status bar content starts
#define ICON_X              2    // x position of play/pause icon
#define ICON_Y              (STATUS_BAR_Y + 2)  // y position of play/pause icon
#define META_TEXT_X          14  // x position where meta text starts
#define META_TEXT_Y         (STATUS_BAR_Y - 2)  // y position of meta text
#define META_AVAIL_WIDTH    (SCREEN_WIDTH - META_TEXT_X)  // 114 px

// ── Button configuration ────────────────────────────────────────────
#define BUTTON_PIN      4
#define DEBOUNCE_MS     50
#define LONG_PRESS_MS   700

// ── Serial configuration ────────────────────────────────────────────
#define BAUD_RATE       115200
#define SERIAL_BUF_SIZE 512

// ── Scrolling configuration ─────────────────────────────────────────
#define LYRIC_SCROLL_INTERVAL_MS  2000
#define LYRIC_SCROLL_STEP         16    // pixels per vertical scroll step
#define META_SCROLL_SPEED_MS      50    // ms per 1-pixel horizontal shift
#define META_SCROLL_GAP           30    // pixel gap before text repeats

// ── Connection timeout ──────────────────────────────────────────────
#define CONNECTION_TIMEOUT_MS 10000

// ── Playback state enum ─────────────────────────────────────────────
enum PlayState { STATE_STOPPED, STATE_PLAYING, STATE_PAUSED };

// ── Objects ─────────────────────────────────────────────────────────
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ── Lyric text state ────────────────────────────────────────────────
String currentText     = "";
float textScale        = 1.5f;    // Display text scale (1.0-3.0, supports 1.5/2.5)
uint8_t textSize       = 1;       // Adafruit GFX text size (1-3)
uint8_t customFontId   = 1;       // 0=none, 1=FreeSans9pt, 2=FreeSans12pt
bool useCustomFont     = true;
int  lyricScrollOffset = 0;
int  totalLyricHeight  = 0;
unsigned long lastLyricScrollTime = 0;

// ── Status bar state ────────────────────────────────────────────────
String       metaText      = "";       // "Artist – Title"
PlayState    playState     = STATE_STOPPED;
int          metaTextWidth = 0;        // pixel width of metaText
int          metaScrollX   = 0;        // current horizontal scroll offset
unsigned long lastMetaScrollTime = 0;
bool         metaNeedsScroll    = false;

// ── Button state ────────────────────────────────────────────────────
bool  lastButtonReading = HIGH;
bool  buttonState       = HIGH;
unsigned long lastDebounceTime = 0;
unsigned long buttonPressTime  = 0;
bool  buttonHeld      = false;
bool  longPressSent   = false;

// ── Connection state ────────────────────────────────────────────────
bool connected = false;
unsigned long lastActivityTime = 0;

// ── Serial buffer ───────────────────────────────────────────────────
char serialBuffer[SERIAL_BUF_SIZE];
int  bufferPos = 0;

// ── Render flag ─────────────────────────────────────────────────────
bool displayDirty = true;

// ── Display mode ────────────────────────────────────────────────────
enum DisplayMode { MODE_LYRICS, MODE_EQUALIZER };
DisplayMode displayMode = MODE_LYRICS;

// ── Equalizer animation state ───────────────────────────────────────
#define EQ_BARS 12
#define EQ_MAX_LEVELS 12
uint8_t eqHeights[EQ_BARS] = {0};
unsigned long lastEqUpdate = 0;
const unsigned long EQ_UPDATE_MS = 80;
unsigned long lastEqHostUpdate = 0;

// ═══════════════════════════════════════════════════════════════════
//  SETUP
// ═══════════════════════════════════════════════════════════════════
void setup() {
    Serial.begin(BAUD_RATE);

    Wire.begin(SDA_PIN, SCL_PIN);

    if (!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
        pinMode(2, OUTPUT);
        while (true) {
            digitalWrite(2, !digitalRead(2));
            delay(300);
        }
    }

    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextWrap(false);
    showStatus("Waiting for", "connection...");

    pinMode(BUTTON_PIN, INPUT_PULLUP);
    lastActivityTime = millis();
}

// ═══════════════════════════════════════════════════════════════════
//  LOOP
// ═══════════════════════════════════════════════════════════════════
void loop() {
    handleSerial();
    handleButton();

    bool needsRender = false;
    needsRender |= handleLyricScroll();
    needsRender |= handleEqualizerAnim();
    needsRender |= handleMetaScroll();

    if (needsRender || displayDirty) {
        renderDisplay();
        displayDirty = false;
    }

    handleConnectionTimeout();
}

// ═══════════════════════════════════════════════════════════════════
//  SERIAL HANDLING
// ═══════════════════════════════════════════════════════════════════
void handleSerial() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (bufferPos > 0) {
                serialBuffer[bufferPos] = '\0';
                processCommand(String(serialBuffer));
                bufferPos = 0;
            }
        } else if (bufferPos < SERIAL_BUF_SIZE - 1) {
            serialBuffer[bufferPos++] = c;
        }
    }
}

void processCommand(String cmd) {
    cmd.trim();
    if (cmd.length() == 0) return;

    lastActivityTime = millis();
    if (!connected) connected = true;

    if (cmd == "PING") {
        Serial.println("PONG");
    }
    else if (cmd == "CLR") {
        currentText = "";
        lyricScrollOffset = 0;
        totalLyricHeight = 0;
        displayDirty = true;
    }
    else if (cmd.startsWith("TXT|")) {
        String text = cmd.substring(4);
        if (text != currentText) {
            currentText = text;
            lyricScrollOffset = 0;
            lastLyricScrollTime = millis();
            displayDirty = true;
        }
    }
    else if (cmd.startsWith("FONT|")) {
        float size = cmd.substring(5).toFloat();
        if (size >= 1.0f && size <= 3.0f && size != textScale) {
            textScale = size;
            // 1.5x -> FreeSans9pt7b, 2.5x -> FreeSans12pt7b
            if (size > 1.4f && size < 1.6f) {
                useCustomFont = true;
                customFontId = 1;
            } else if (size > 2.4f && size < 2.6f) {
                useCustomFont = true;
                customFontId = 2;
            } else {
                useCustomFont = false;
                customFontId = 0;
                textSize = (uint8_t)(size + 0.5f);
            }
            lyricScrollOffset = 0;
            lastLyricScrollTime = millis();
            displayDirty = true;
        }
    }
    else if (cmd.startsWith("STA|")) {
        String state = cmd.substring(4);
        PlayState newState = STATE_STOPPED;
        if (state == "PLAY")       newState = STATE_PLAYING;
        else if (state == "PAUSE") newState = STATE_PAUSED;
        else                       newState = STATE_STOPPED;
        if (newState != playState) {
            playState = newState;
            displayDirty = true;
        }
    }
    else if (cmd.startsWith("META|")) {
        String text = cmd.substring(5);
        if (text != metaText) {
            metaText = text;
            metaTextWidth = text.length() * 6;  // textSize 1: 6px per char
            metaScrollX = 0;
            lastMetaScrollTime = millis();
            metaNeedsScroll = (metaTextWidth > META_AVAIL_WIDTH);
            displayDirty = true;
        }
    }
    else if (cmd.startsWith("MODE|")) {
        String mode = cmd.substring(5);
        DisplayMode nextMode = (mode == "EQ") ? MODE_EQUALIZER : MODE_LYRICS;
        if (nextMode != displayMode) {
            displayMode = nextMode;
            lyricScrollOffset = 0;
            lastLyricScrollTime = millis();
            displayDirty = true;
        }
    }
    else if (cmd.startsWith("EQ|")) {
        String payload = cmd.substring(3);
        int index = 0;
        int start = 0;
        while (start < payload.length() && index < EQ_BARS) {
            int comma = payload.indexOf(',', start);
            if (comma == -1) comma = payload.length();
            int value = payload.substring(start, comma).toInt();
            if (value < 0) value = 0;
            if (value > EQ_MAX_LEVELS) value = EQ_MAX_LEVELS;
            eqHeights[index++] = (uint8_t)value;
            start = comma + 1;
        }
        while (index < EQ_BARS) {
            eqHeights[index++] = 0;
        }
        lastEqHostUpdate = millis();
        // Auto-switch to EQ display when receiving EQ data
        if (displayMode != MODE_EQUALIZER) {
            displayMode = MODE_EQUALIZER;
        }
        displayDirty = true;
    }
}

// ═══════════════════════════════════════════════════════════════════
//  FULL DISPLAY RENDER
// ═══════════════════════════════════════════════════════════════════
void renderDisplay() {
    display.clearDisplay();

    // ── 1. Lyrics area (top) ────────────────────────────────────
    if (displayMode == MODE_EQUALIZER) {
        renderEqualizer();
    } else {
        if (currentText.length() > 0) {
            renderLyrics();
        }
    }

    // ── 1b. Clear any lyric/EQ overflow into status bar area ───
    display.fillRect(0, LYRICS_AREA_HEIGHT, SCREEN_WIDTH,
                     SCREEN_HEIGHT - LYRICS_AREA_HEIGHT, SSD1306_BLACK);

    // ── 2. Separator line ───────────────────────────────────────
    display.drawFastHLine(0, SEPARATOR_Y, SCREEN_WIDTH, SSD1306_WHITE);

    // ── 3. Status bar (bottom) ──────────────────────────────────
    renderStatusBar();

    display.display();
}

// ═══════════════════════════════════════════════════════════════════
//  LYRICS RENDERING  (word-wrap + vertical scroll)
// ═══════════════════════════════════════════════════════════════════
void renderLyrics() {
    // ── Word-wrap into lines ────────────────────────────────────
    #define MAX_WRAP_LINES 32
    String lines[MAX_WRAP_LINES];
    int lineCount = 0;

    if (useCustomFont) {
        const GFXfont *font;
        if (customFontId == 2) {
            font = &FreeSans12pt7b;
        } else {
            font = &FreeSans9pt7b;
        }
        display.setFont(font);
        display.setTextSize(1);
        // Use tight line heights matching the PC simulator
        int lineHeight = (customFontId == 2) ? 18 : 13;

        auto textWidth = [&](const String &text) {
            int16_t x1, y1;
            uint16_t w, h;
            display.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
            return (int)w;
        };

        String line = "";
        int len = currentText.length();
        int pos = 0;
        while (pos < len && lineCount < MAX_WRAP_LINES) {
            while (pos < len && currentText.charAt(pos) == ' ') pos++;
            if (pos >= len) break;
            int end = pos;
            while (end < len && currentText.charAt(end) != ' ') end++;
            String word = currentText.substring(pos, end);
            String candidate = line.length() ? line + " " + word : word;
            if (textWidth(candidate) <= SCREEN_WIDTH) {
                line = candidate;
            } else if (line.length() > 0) {
                lines[lineCount++] = line;
                line = word;
            } else {
                String chunk = "";
                for (int i = 0; i < word.length() && lineCount < MAX_WRAP_LINES; i++) {
                    String attempt = chunk + word.charAt(i);
                    if (textWidth(attempt) <= SCREEN_WIDTH || chunk.length() == 0) {
                        chunk = attempt;
                    } else {
                        lines[lineCount++] = chunk;
                        chunk = String(word.charAt(i));
                    }
                }
                line = chunk;
            }
            pos = end + 1;
        }
        if (line.length() > 0 && lineCount < MAX_WRAP_LINES) {
            lines[lineCount++] = line;
        }

        totalLyricHeight = lineCount * lineHeight;

        // ── Draw visible lines (clipped to lyrics area) ─────────────
        int startY = -lyricScrollOffset;
        for (int i = 0; i < lineCount; i++) {
            int y = startY + i * lineHeight;
            if (y + lineHeight > 0 && y < LYRICS_AREA_HEIGHT) {
                display.setCursor(0, y + lineHeight - 2);
                display.print(lines[i]);
            }
        }
    } else {
        display.setFont(nullptr);
        display.setTextSize(textSize);

        int charW = 6 * textSize;
        int charH = 8 * textSize;
        int charsPerLine = SCREEN_WIDTH / charW;
        if (charsPerLine < 1) charsPerLine = 1;

        int len = currentText.length();
        int pos = 0;

        while (pos < len && lineCount < MAX_WRAP_LINES) {
            int remaining = len - pos;
            if (remaining <= charsPerLine) {
                lines[lineCount++] = currentText.substring(pos);
                break;
            }

            int breakAt = pos + charsPerLine;
            int lastSpace = -1;
            for (int i = pos; i < breakAt && i < len; i++) {
                if (currentText.charAt(i) == ' ') {
                    lastSpace = i;
                }
            }

            if (lastSpace > pos) {
                lines[lineCount++] = currentText.substring(pos, lastSpace);
                pos = lastSpace + 1;
            } else {
                lines[lineCount++] = currentText.substring(pos, breakAt);
                pos = breakAt;
            }
        }

        totalLyricHeight = lineCount * charH;

        // ── Draw visible lines (clipped to lyrics area) ─────────────
        int startY = -lyricScrollOffset;
        for (int i = 0; i < lineCount; i++) {
            int y = startY + i * charH;
            if (y + charH > 0 && y < LYRICS_AREA_HEIGHT) {
                display.setCursor(0, y);
                display.print(lines[i]);
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
//  STATUS BAR RENDERING  (play/pause icon + scrolling meta text)
// ═══════════════════════════════════════════════════════════════════
void renderStatusBar() {
    // ── Draw play/pause/stop icon ───────────────────────────────
    switch (playState) {
        case STATE_PLAYING:
            // Show pause icon (press to pause) – compact 7px
            display.fillRect(ICON_X,     ICON_Y, 2, 7, SSD1306_WHITE);
            display.fillRect(ICON_X + 4, ICON_Y, 2, 7, SSD1306_WHITE);
            break;

        case STATE_PAUSED:
            // Show play icon (press to resume) – compact 7px
            display.fillTriangle(
                ICON_X,     ICON_Y,
                ICON_X,     ICON_Y + 7,
                ICON_X + 6, ICON_Y + 3,
                SSD1306_WHITE
            );
            break;

        case STATE_STOPPED:
            // Small square (stop) – compact 7px
            display.fillRect(ICON_X, ICON_Y, 7, 7, SSD1306_WHITE);
            break;
    }

    // ── Draw meta text (artist – title) with horizontal scroll ──
    if (metaText.length() == 0) return;

    display.setFont(nullptr);
    display.setTextSize(1);

    if (!metaNeedsScroll) {
        // Static: fits on screen
        display.setCursor(META_TEXT_X, META_TEXT_Y);
        display.print(metaText);
    } else {
        // Scrolling: draw the text shifted left by metaScrollX,
        // and clip to the available area using a manual approach.
        // We draw character by character, only if visible.
        int totalW = metaTextWidth + META_SCROLL_GAP;
        int textLen = metaText.length();

        for (int pass = 0; pass < 2; pass++) {
            int baseX = META_TEXT_X - metaScrollX + pass * totalW;
            for (int i = 0; i < textLen; i++) {
                int cx = baseX + i * 6;
                if (cx >= SCREEN_WIDTH) break;       // past right edge
                if (cx + 6 <= META_TEXT_X) continue;  // before left edge
                display.setCursor(cx, META_TEXT_Y);
                display.print(metaText.charAt(i));
            }
        }
    }
}

// ═══════════════════════════════════════════════════════════════════
//  EQUALIZER RENDERING
// ═══════════════════════════════════════════════════════════════════
void renderEqualizer() {
    int barWidth = SCREEN_WIDTH / EQ_BARS;
    int maxHeight = LYRICS_AREA_HEIGHT - 2;

    for (int i = 0; i < EQ_BARS; i++) {
        int levels = eqHeights[i];
        int barHeight = (levels * maxHeight) / EQ_MAX_LEVELS;
        int x = i * barWidth;
        int y = maxHeight - barHeight;
        display.fillRect(x + 1, y, barWidth - 2, barHeight, SSD1306_WHITE);
    }
}

// ═══════════════════════════════════════════════════════════════════
//  LYRIC VERTICAL SCROLLING
// ═══════════════════════════════════════════════════════════════════
bool handleLyricScroll() {
    if (displayMode != MODE_LYRICS) return false;
    if (totalLyricHeight <= LYRICS_AREA_HEIGHT) return false;
    if (currentText.length() == 0) return false;

    unsigned long now = millis();
    if (now - lastLyricScrollTime < LYRIC_SCROLL_INTERVAL_MS) return false;

    lastLyricScrollTime = now;

    int maxScroll = totalLyricHeight - LYRICS_AREA_HEIGHT;
    lyricScrollOffset += LYRIC_SCROLL_STEP;
    if (lyricScrollOffset > maxScroll) {
        lyricScrollOffset = 0;
    }

    return true;
}

bool handleEqualizerAnim() {
    if (displayMode != MODE_EQUALIZER) return false;
    if (playState != STATE_PLAYING) return false;
    if (millis() - lastEqHostUpdate < 250) return false;
    if (millis() - lastEqUpdate < EQ_UPDATE_MS) return false;
    lastEqUpdate = millis();

    for (int i = 0; i < EQ_BARS; i++) {
        int delta = random(-2, 3);
        int next = (int)eqHeights[i] + delta;
        if (next < 0) next = 0;
        if (next > EQ_MAX_LEVELS) next = EQ_MAX_LEVELS;
        eqHeights[i] = (uint8_t)next;
    }
    return true;
}

// ═══════════════════════════════════════════════════════════════════
//  META TEXT HORIZONTAL SCROLLING
// ═══════════════════════════════════════════════════════════════════
bool handleMetaScroll() {
    if (!metaNeedsScroll) return false;

    unsigned long now = millis();
    if (now - lastMetaScrollTime < META_SCROLL_SPEED_MS) return false;

    lastMetaScrollTime = now;

    int totalW = metaTextWidth + META_SCROLL_GAP;
    metaScrollX += 1;
    if (metaScrollX >= totalW) {
        metaScrollX = 0;
    }

    return true;
}

// ═══════════════════════════════════════════════════════════════════
//  BUTTON HANDLING  (debounce + short/long press)
// ═══════════════════════════════════════════════════════════════════
void handleButton() {
    bool reading = digitalRead(BUTTON_PIN);

    if (reading != lastButtonReading) {
        lastDebounceTime = millis();
    }

    if ((millis() - lastDebounceTime) > DEBOUNCE_MS) {
        if (reading != buttonState) {
            buttonState = reading;

            if (buttonState == LOW) {
                buttonPressTime = millis();
                buttonHeld    = true;
                longPressSent = false;
            } else {
                if (buttonHeld && !longPressSent) {
                    Serial.println("BTN|PRESS");
                }
                buttonHeld = false;
            }
        }
    }

    if (buttonHeld && !longPressSent && buttonState == LOW) {
        if (millis() - buttonPressTime >= LONG_PRESS_MS) {
            Serial.println("BTN|LONG");
            longPressSent = true;
        }
    }

    lastButtonReading = reading;
}

// ═══════════════════════════════════════════════════════════════════
//  CONNECTION TIMEOUT
// ═══════════════════════════════════════════════════════════════════
void handleConnectionTimeout() {
    if (!connected) return;

    if (millis() - lastActivityTime > CONNECTION_TIMEOUT_MS) {
        connected = false;
        currentText = "";
        lyricScrollOffset = 0;
        totalLyricHeight = 0;
        metaText = "";
        metaTextWidth = 0;
        metaScrollX = 0;
        metaNeedsScroll = false;
        playState = STATE_STOPPED;
        showStatus("Disconnected", "");
    }
}

// ═══════════════════════════════════════════════════════════════════
//  STATUS SCREEN  (used for connection messages only)
// ═══════════════════════════════════════════════════════════════════
void showStatus(const char* line1, const char* line2) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setCursor(0, 24);
    display.print(line1);
    if (line2 && strlen(line2) > 0) {
        display.setCursor(0, 36);
        display.print(line2);
    }
    display.display();
}
