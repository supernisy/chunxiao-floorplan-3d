"""Render the CAD PDF page to a high-res PNG for human (multimodal) reading of
dimension numbers and layout confirmation. Text in this PDF is vector-outlined,
so we read dimensions visually rather than via text extraction.
"""
import os, fitz
SRC = os.path.join(os.path.dirname(__file__), "..", "assets", "chunxiao.pdf")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "plan.png")
doc = fitz.open(SRC)
page = doc[0]
mat = fitz.Matrix(2.2, 2.2)  # ~158 DPI
pix = page.get_pixmap(matrix=mat)
pix.save(OUT)
print("RENDER_DONE", OUT, pix.width, pix.height)
