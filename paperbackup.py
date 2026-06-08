#!/usr/bin/env python

#
# create a pdf with barcodes to backup text files on paper
# designed to backup ascii-armored key files and ciphertext
#

# Copyright 2017 by Intra2net AG, Germany
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import os
import re
import sys
import hashlib
import qrcode
import tempfile
from io import BytesIO
from datetime import datetime
from PIL import Image
from pyx import *
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import cm, inch
from pypdf import PdfReader, PdfWriter

# constants for the size and layout of the barcodes on page
max_bytes_in_barcode = 140
barcodes_per_page = 6
barcode_height = 8
barcode_x_positions = [1.5, 11, 1.5, 11, 1.5, 11]
barcode_y_positions = [18.7, 18.7, 10, 10, 1.2, 1.2]
text_x_offset = 0
text_y_offset = 8.2

plaintext_maxlinechars = 73

# the paperformat to use, activate the one you want
paperformat_obj = document.paperformat.A4
paperformat_str = "A4"
# paperformat_obj=document.paperformat.Letter
# paperformat_str="Letter"


def create_barcode(chunkdata):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=10,
        border=4,
    )
    qr.add_data(chunkdata)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img


def finish_page(pdf, canv, pageno):
    canv.text(10, 0.6, "Page %i" % (pageno+1))
    pdf.append(document.page(canv, paperformat=paperformat_obj,
                             fittosize=0, centered=0))

# main code

if len(sys.argv) != 2:
    raise RuntimeError('Usage {} FILENAME.asc'.format(sys.argv[0]))

input_path = sys.argv[1]
if not os.path.isfile(input_path):
    raise RuntimeError('File {} not found'.format(input_path))
just_filename = os.path.basename(input_path)

with open(input_path) as inputfile:
    ascdata = inputfile.read()

# only allow some harmless characters
# this is much more strict than neccessary, but good enough for key files
# you really need to forbid ^, NULL and anything that could upset enscript
allowedchars = re.compile(r"^[A-Za-z0-9/=+:., #@!()\n-]*")
allowedmatch = allowedchars.match(ascdata)
if allowedmatch.group() != ascdata:
    raise RuntimeError('Illegal char found at %d >%s<'
                       % (len(allowedmatch.group()),
                          ascdata[len(allowedmatch.group())]))

# split the ascdata into chunks of max_bytes_in_barcode size
# each chunk begins with ^<sequence number><space>
# this allows to easily put them back together in the correct order
barcode_blocks = []
chunkdata = "^1 "
for char in list(ascdata):
    if len(chunkdata)+1 > max_bytes_in_barcode:
        # chunk is full -> create barcode from it
        barcode_blocks.append(create_barcode(chunkdata))
        chunkdata = "^" + str(len(barcode_blocks)+1) + " "

    chunkdata += char

# handle the last, non filled chunk too
barcode_blocks.append(create_barcode(chunkdata))

# init PyX
unit.set(defaultunit="cm")
pdf = document.document()

# place barcodes on pages
pgno = 0   # page number
ppos = 0   # position id on page
c = canvas.canvas()
for bc in range(len(barcode_blocks)):
    # page full?
    if ppos >= barcodes_per_page:
        finish_page(pdf, c, pgno)
        c = canvas.canvas()
        pgno += 1
        ppos = 0

    c.text(barcode_x_positions[ppos] + text_x_offset,
           barcode_y_positions[ppos] + text_y_offset,
           "%s (%i/%i)" % (text.escapestring(just_filename),
                           bc+1, len(barcode_blocks)))
    c.insert(bitmap.bitmap(barcode_x_positions[ppos],
                           barcode_y_positions[ppos],
                           barcode_blocks[bc], height=barcode_height))
    ppos += 1

finish_page(pdf, c, pgno)
pgno += 1

# write barcode PDF to temporary file, read into BytesIO, then delete
with tempfile.NamedTemporaryFile(mode='w+b', suffix='.pdf', delete=False) as tmp:
    temp_path = tmp.name

pdf.writetofile(temp_path)

# read the temporary file into BytesIO
with open(temp_path, 'rb') as f:
    barcode_pdf_bytes = BytesIO(f.read())

# delete the temporary file
os.remove(temp_path)

# prepare plain text output
input_file_modification = datetime.fromtimestamp(os.path.getmtime(input_path)).strftime("%Y-%m-%d %H:%M:%S")

# split lines on plaintext_maxlinechars - ( checksum_size + separator size)
splitat=plaintext_maxlinechars - 8
splitlines=[]
for line in ascdata.splitlines():
    while len(line) > splitat:
        splitlines.append(line[:splitat])
        # add a ^ at the beginning of the broken line to mark the linebreak
        line="^"+line[splitat:]
    splitlines.append(line)

# add checksums to each line
chksumlines=[]
for line in splitlines:
    # remove the linebreak marks for checksumming
    if len(line) > 1 and line[0] == "^":
        sumon=line[1:]
    else:
        sumon=line

    # use the first 6 bytes of MD5 as checksum
    chksum = hashlib.md5(sumon.encode('utf-8')).hexdigest()[:6]

    # add the checksum right-justified to the line
    line+=" "*(splitat-len(line))
    line+=" |"+chksum

    chksumlines.append(line)

# we also want a checksum which the restored file should match
checksum = hashlib.sha256(bytes(ascdata, 'utf8')).hexdigest()

# add some documentation around the plaintest
outlines=[]
coldoc=" "*splitat
coldoc+=" | MD5"
outlines.append(coldoc)
outlines.extend(chksumlines)
outlines.append("")
outlines.append("")
outlines.append("sha256sum of input file:")
outlines.append("%s"%checksum)
outlines.append("")
outlines.append("")
outlines.append("--")
outlines.append("Created with paperbackup.py")
outlines.append("See https://github.com/intra2net/paperbackup/ for instructions")

# create plaintext PDF using reportlab instead of enscript
# convert paperformat string to reportlab pagesize
pagesize = A4 if paperformat_str == "A4" else letter

# prepare the canvas with Courier font for monospace output
text_pdf_bytes = BytesIO()
c = rl_canvas.Canvas(text_pdf_bytes, pagesize=pagesize)

# calculate font and margin sizes
font_name = "Courier"
font_size = 10
margin = 0.5 * inch
page_width, page_height = pagesize
line_height = font_size * 1.2
lines_per_page = int((page_height - 2 * margin) / line_height)

# write the header and content
header = "%s | %s | Page 1" % (just_filename, input_file_modification)
page_num = 1
line_num = 0
y_position = page_height - margin

# header on first page
c.setFont(font_name, font_size - 2)
c.drawString(margin, y_position, header)
y_position -= line_height * 1.5

# write all outline lines
c.setFont(font_name, font_size)
for line in outlines:
    if line_num >= lines_per_page:
        # new page
        c.showPage()
        page_num += 1
        header = "%s | %s | Page %d" % (just_filename, input_file_modification, page_num)
        c.setFont(font_name, font_size - 2)
        c.drawString(margin, page_height - margin, header)
        c.setFont(font_name, font_size)
        y_position = page_height - margin - line_height * 1.5
        line_num = 0
    
    c.drawString(margin, y_position, line)
    y_position -= line_height
    line_num += 1

c.save()

# merge the two PDFs (barcodes and text) using pypdf
writer = PdfWriter()

# seek to beginning of both BytesIO objects before reading
barcode_pdf_bytes.seek(0)
text_pdf_bytes.seek(0)

# read the barcode PDF from BytesIO
reader = PdfReader(barcode_pdf_bytes)
for page in reader.pages:
    writer.add_page(page)

# read the text PDF from BytesIO
reader = PdfReader(text_pdf_bytes)
for page in reader.pages:
    writer.add_page(page)

# write the combined PDF
with open(just_filename + ".pdf", "wb") as output_pdf:
    writer.write(output_pdf)

print("Please now verify that the output can be restored by calling:")
print("paperbackup-verify.sh {}.pdf".format(just_filename))
