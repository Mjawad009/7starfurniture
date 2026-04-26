from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO


def build_invoice_pdf(sale, item_rows):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, height - 50, "Furniture Showroom Invoice")
    c.setFont("Helvetica", 12)
    c.drawString(40, height - 80, f"Invoice ID: {sale.id}")
    c.drawString(40, height - 100, f"Sale Date: {sale.sale_date}")
    c.drawString(40, height - 120, f"Payment Method: {sale.payment_method}")

    y = height - 160
    c.drawString(40, y, "Product")
    c.drawString(240, y, "Qty")
    c.drawString(320, y, "Unit Price")
    c.drawString(420, y, "Line Total")
    y -= 20

    total = 0
    for item, qty in item_rows:
        line_total = item.sale_price * qty
        total += line_total
        c.drawString(40, y, item.name)
        c.drawString(240, y, str(qty))
        c.drawString(320, y, f"${item.sale_price:.2f}")
        c.drawString(420, y, f"${line_total:.2f}")
        y -= 20
        if y < 80:
            c.showPage()
            y = height - 50

    c.drawString(40, y - 20, f"Discount: ${sale.discount:.2f}")
    c.drawString(40, y - 40, f"Total amount: ${max(total - sale.discount, 0):.2f}")
    c.save()
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
