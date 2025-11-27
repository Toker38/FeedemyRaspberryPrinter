"""
ESC/POS Command Constants
Thermal printer byte sequences
"""

# Control characters
ESC = b'\x1b'
GS = b'\x1d'
LF = b'\x0a'

# === Initialization ===
INIT = ESC + b'@'  # Reset printer

# === Text Formatting ===
BOLD_ON = ESC + b'E\x01'
BOLD_OFF = ESC + b'E\x00'

UNDERLINE_ON = ESC + b'-\x01'
UNDERLINE_OFF = ESC + b'-\x00'

# === Text Size ===
# GS ! n - where n = (width-1) * 16 + (height-1)
NORMAL = GS + b'!\x00'          # 1x1
DOUBLE_WIDTH = GS + b'!\x10'    # 2x1
DOUBLE_HEIGHT = GS + b'!\x01'   # 1x2
DOUBLE_BOTH = GS + b'!\x11'     # 2x2

# === Alignment ===
ALIGN_LEFT = ESC + b'a\x00'
ALIGN_CENTER = ESC + b'a\x01'
ALIGN_RIGHT = ESC + b'a\x02'

# === Paper Control ===
def feed_lines(n: int) -> bytes:
    """n satır boşluk bırak"""
    return ESC + b'd' + bytes([n])

FEED_ONE = feed_lines(1)
FEED_THREE = feed_lines(3)

# === Cut ===
CUT_FULL = GS + b'V\x00'     # Tam kesim
CUT_PARTIAL = GS + b'V\x01'  # Kısmi kesim (kağıt bağlı kalır)

# === Character Set ===
# ESC t n - Select character code table
CHARSET_PC437 = ESC + b't\x00'      # USA Standard Europe
CHARSET_PC850 = ESC + b't\x02'      # Multilingual
CHARSET_PC857 = ESC + b't\x12'      # Turkish
CHARSET_PC858 = ESC + b't\x13'      # Euro
CHARSET_UTF8 = ESC + b't\xff'       # UTF-8 (some printers)

# Default for Turkish
SELECT_CHARSET = CHARSET_PC857

# === International Character Set ===
# ESC R n - Select international character set
INTL_USA = ESC + b'R\x00'
INTL_FRANCE = ESC + b'R\x01'
INTL_GERMANY = ESC + b'R\x02'
INTL_UK = ESC + b'R\x03'
INTL_DENMARK = ESC + b'R\x04'
INTL_SWEDEN = ESC + b'R\x05'
INTL_ITALY = ESC + b'R\x06'
INTL_SPAIN = ESC + b'R\x07'

# === Line Spacing ===
LINE_SPACING_DEFAULT = ESC + b'2'           # Default spacing


def line_spacing_set(n: int) -> bytes:
    """Set line spacing to n dots"""
    return ESC + b'3' + bytes([n])

# === Helper Functions ===

def get_size_command(size: str) -> bytes:
    """Size string'den ESC/POS komutu al"""
    sizes = {
        "xs": NORMAL,
        "sm": NORMAL,
        "md": NORMAL,
        "lg": DOUBLE_WIDTH,
        "xl": DOUBLE_BOTH
    }
    return sizes.get(size, NORMAL)


def get_align_command(align: str) -> bytes:
    """Alignment string'den ESC/POS komutu al"""
    alignments = {
        "l": ALIGN_LEFT,
        "c": ALIGN_CENTER,
        "r": ALIGN_RIGHT,
        "left": ALIGN_LEFT,
        "center": ALIGN_CENTER,
        "right": ALIGN_RIGHT
    }
    return alignments.get(align, ALIGN_LEFT)


# === Turkish Character Mapping ===
# CP857 encoding için Türkçe karakterler
# Referans: https://en.wikipedia.org/wiki/Code_page_857
TURKISH_CHARS = {
    'ç': b'\x87',    # c with cedilla (lowercase) - 0x87
    'Ç': b'\x80',    # C with cedilla (uppercase) - 0x80
    'ğ': b'\xa7',    # g with breve (lowercase) - 0xA7
    'Ğ': b'\xa6',    # G with breve (uppercase) - 0xA6
    'ı': b'\x8d',    # dotless i (lowercase) - 0x8D
    'İ': b'\x98',    # I with dot (uppercase) - 0x98
    'ö': b'\x94',    # o with diaeresis (lowercase) - 0x94
    'Ö': b'\x99',    # O with diaeresis (uppercase) - 0x99
    'ş': b'\x9f',    # s with cedilla (lowercase) - 0x9F
    'Ş': b'\x9e',    # S with cedilla (uppercase) - 0x9E
    'ü': b'\x81',    # u with diaeresis (lowercase) - 0x81
    'Ü': b'\x9a',    # U with diaeresis (uppercase) - 0x9A
}


def encode_turkish(text: str) -> bytes:
    """
    Türkçe karakterleri CP857 byte'larına çevir
    Desteklenmeyen karakterler ASCII'ye düşürülür
    """
    result = bytearray()
    for char in text:
        if char in TURKISH_CHARS:
            result.extend(TURKISH_CHARS[char])
        else:
            try:
                result.extend(char.encode('cp857'))
            except UnicodeEncodeError:
                # Fallback: ASCII'ye çevir veya ? koy
                result.extend(char.encode('ascii', errors='replace'))
    return bytes(result)
