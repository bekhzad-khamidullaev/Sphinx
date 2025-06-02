# qrfikr/utils.py
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import ImageDraw # For adding text or logo (optional)

def generate_qr_code_image(data_string, box_size=10, border=2, fill_color="black", back_color="white"):
    """
    Generates a QR code PIL Image object.
    """
    qr = qrcode.QRCode(
        version=None, # None lets the library choose the smallest appropriate version
        error_correction=qrcode.constants.ERROR_CORRECT_M, # Medium error correction
        box_size=box_size,
        border=border,
    )
    qr.add_data(data_string)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fill_color, back_color=back_color)
    
    # Optional: Add a small logo or text (requires Pillow)
    # For example, adding a small text footer
    # draw = ImageDraw.Draw(img)
    # text = "Scan Me"
    # font_size = int(box_size * 1.5) # Adjust font size based on box_size
    # try:
    #     from PIL import ImageFont
    #     font = ImageFont.truetype("arial.ttf", font_size) # Ensure font is available
    # except IOError:
    #     font = ImageFont.load_default()
    
    # text_bbox = draw.textbbox((0, 0), text, font=font)
    # text_width = text_bbox[2] - text_bbox[0]
    # text_height = text_bbox[3] - text_bbox[1]

    # img_width, img_height = img.size
    # position = ((img_width - text_width) // 2, img_height - text_height - (border // 2 * box_size)) # Centered at bottom
    # draw.text(position, text, fill=fill_color, font=font)

    return img