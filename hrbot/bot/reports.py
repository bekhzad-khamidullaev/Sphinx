import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from hrbot.bot.stats import compute_avg_scores

async def generate_report(buffer: io.BytesIO):
    """Generate a PDF report of average scores."""
    scores = await compute_avg_scores()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "HR Evaluation Report")
    c.setFont("Helvetica", 12)
    y = height - 100
    for q, avg in scores.items():
        c.drawString(50, y, f"{q}: {avg:.2f}")
        y -= 20
        if y < 50:
            c.showPage()
            y = height - 50
    c.save()
    buffer.seek(0)
    return buffer