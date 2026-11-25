# Test CI : l'OCR Windows lit bien un texte affiché
import asyncio
from PIL import Image, ImageDraw, ImageFont
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
from winrt.windows.storage.streams import DataWriter

img = Image.new("RGBA", (900, 120), (0, 0, 0, 255))
d = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 48)
except OSError:
    font = ImageFont.load_default()
d.text((20, 30), "Attends-moi dans la voiture", fill=(255, 255, 255, 255), font=font)
b, g, r, a = img.split()
bgra = Image.merge("RGBA", (b, g, r, a)).tobytes()
eng = OcrEngine.try_create_from_user_profile_languages()
print("langue OCR :", eng.recognizer_language.language_tag)
dw = DataWriter()
dw.write_bytes(bgra)
bmp = SoftwareBitmap.create_copy_from_buffer(dw.detach_buffer(), BitmapPixelFormat.BGRA8, img.width, img.height, BitmapAlphaMode.PREMULTIPLIED)
res = asyncio.new_event_loop().run_until_complete(eng.recognize_async(bmp))
txt = " ".join(l.text for l in res.lines)
print("lu :", txt)
assert "voiture" in txt.lower(), txt
print("OCR OK")
