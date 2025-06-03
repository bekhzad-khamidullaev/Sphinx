import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import ImageDraw

def generate_qr_code_image(data_string, box_size=10, border=2, fill_color="black", back_color="white"):
    """
    Generates a QR code PIL Image object.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data_string)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fill_color, back_color=back_color)
    

    return img